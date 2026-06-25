"""spaCy-based NER auto-annotation.

Trains a spaCy NER pipeline on all human-annotated documents in the project,
then annotates every document that has no entity spans yet. Model-created
spans are stored with source="model" and reviewed=False so annotators can
review them before they count as ground truth.
"""
import os
import random
from typing import Callable, List, Tuple

from sqlalchemy.orm import selectinload

from ..config import settings
from ..database import SessionLocal
from ..models import Document, EntityType, Span
from .jobs import MissingDependencyError

MIN_TRAIN_DOCS = 5
EVAL_FRACTION = 0.1


def run_ner_job(project_id: int, update: Callable) -> None:
    try:
        import spacy
        from spacy.training import Example
        from spacy.util import minibatch
    except ImportError:
        raise MissingDependencyError(
            "spaCy is not installed on the server. Install ML dependencies with: "
            "pip install -r requirements-ml.txt"
        )

    update(status="training", progress=0.0, message="Collecting training data")
    db = SessionLocal()
    try:
        entity_types = {
            et.id: et.name
            for et in db.query(EntityType).filter(EntityType.project_id == project_id)
        }
        train_docs: List[Tuple[str, List[Tuple[int, int, str]]]] = []
        annotate_doc_ids: List[int] = []

        docs = (
            db.query(Document)
            .options(selectinload(Document.spans))
            .filter(Document.project_id == project_id)
            .all()
        )
        for doc in docs:
            human_spans = [
                s for s in doc.spans if s.source == "human" or s.reviewed
            ]
            if human_spans:
                entities = [
                    (s.start_offset, s.end_offset, entity_types[s.entity_type_id])
                    for s in human_spans
                    if s.entity_type_id in entity_types
                ]
                train_docs.append((doc.text, _drop_overlaps(entities)))
            elif not doc.spans:
                annotate_doc_ids.append(doc.id)
    finally:
        db.close()

    if len(train_docs) < MIN_TRAIN_DOCS:
        update(
            status="failed",
            message=f"Need at least {MIN_TRAIN_DOCS} annotated documents to train "
            f"(found {len(train_docs)}).",
        )
        return

    random.Random(42).shuffle(train_docs)
    n_eval = max(1, int(len(train_docs) * EVAL_FRACTION)) if len(train_docs) >= 10 else 0
    eval_docs = train_docs[:n_eval]
    train_docs = train_docs[n_eval:]

    nlp = (
        spacy.blank(settings.NER_BASE_MODEL.split(":", 1)[1])
        if settings.NER_BASE_MODEL.startswith("blank:")
        else spacy.load(settings.NER_BASE_MODEL)
    )
    if "ner" not in nlp.pipe_names:
        ner = nlp.add_pipe("ner")
    else:
        ner = nlp.get_pipe("ner")
    for _, entities in train_docs + eval_docs:
        for _, _, label in entities:
            ner.add_label(label)

    examples = []
    skipped = 0
    for text, entities in train_docs:
        try:
            example = Example.from_dict(nlp.make_doc(text), {"entities": entities})
            examples.append(example)
        except ValueError:
            skipped += 1  # overlapping/misaligned spans that spaCy rejects

    update(message=f"Training spaCy NER on {len(examples)} documents")
    other_pipes = [p for p in nlp.pipe_names if p != "ner"]
    iterations = settings.NER_TRAINING_ITERATIONS
    with nlp.disable_pipes(*other_pipes):
        optimizer = nlp.initialize(lambda: examples)
        rng = random.Random(0)
        for i in range(iterations):
            rng.shuffle(examples)
            losses = {}
            for batch in minibatch(examples, size=8):
                nlp.update(batch, sgd=optimizer, drop=0.2, losses=losses)
            update(
                progress=0.7 * (i + 1) / iterations,
                message=f"Training: iteration {i + 1}/{iterations}, "
                f"loss {losses.get('ner', 0):.2f}",
            )

    metrics = {"training_documents": len(examples), "skipped_documents": skipped}
    if eval_docs:
        metrics.update(_evaluate(nlp, eval_docs, Example))

    model_dir = os.path.join(settings.MODELS_DIR, f"project_{project_id}", "ner")
    os.makedirs(model_dir, exist_ok=True)
    nlp.to_disk(model_dir)
    metrics["model_path"] = model_dir

    # ---- Annotate unannotated documents ----
    update(status="annotating", progress=0.7, metrics=metrics,
           message=f"Annotating {len(annotate_doc_ids)} documents")
    name_to_type_id = {v: k for k, v in entity_types.items()}
    annotated = 0
    BATCH = 200
    for batch_start in range(0, len(annotate_doc_ids), BATCH):
        batch_ids = annotate_doc_ids[batch_start : batch_start + BATCH]
        db = SessionLocal()
        try:
            batch_docs = db.query(Document).filter(Document.id.in_(batch_ids)).all()
            texts = [(d.text, d.id) for d in batch_docs]
            for spacy_doc, doc_id in nlp.pipe(texts, as_tuples=True, batch_size=32):
                made_any = False
                for ent in spacy_doc.ents:
                    type_id = name_to_type_id.get(ent.label_)
                    if type_id is None:
                        continue
                    db.add(
                        Span(
                            document_id=doc_id,
                            entity_type_id=type_id,
                            start_offset=ent.start_char,
                            end_offset=ent.end_char,
                            source="model",
                            reviewed=False,
                        )
                    )
                    made_any = True
                if made_any:
                    annotated += 1
            db.commit()
        finally:
            db.close()
        done = batch_start + len(batch_ids)
        update(
            progress=0.7 + 0.3 * done / max(1, len(annotate_doc_ids)),
            annotated=annotated,
            message=f"Annotated {done}/{len(annotate_doc_ids)} documents",
        )

    update(
        status="completed",
        progress=1.0,
        annotated=annotated,
        metrics=metrics,
        message=f"Done. Model suggested entities in {annotated} documents — "
        "review them under the 'Needs review' filter.",
    )


def _drop_overlaps(entities: List[Tuple[int, int, str]]) -> List[Tuple[int, int, str]]:
    """spaCy NER requires non-overlapping entities; keep longest-first."""
    result: List[Tuple[int, int, str]] = []
    for ent in sorted(entities, key=lambda e: (e[0] - e[1])):  # longest first
        if all(ent[1] <= r[0] or ent[0] >= r[1] for r in result):
            result.append(ent)
    return sorted(result)


def _evaluate(nlp, eval_docs, Example) -> dict:
    examples = []
    for text, entities in eval_docs:
        try:
            examples.append(Example.from_dict(nlp.make_doc(text), {"entities": entities}))
        except ValueError:
            continue
    if not examples:
        return {}
    scores = nlp.evaluate(examples)
    return {
        "precision": round(scores.get("ents_p", 0.0), 4),
        "recall": round(scores.get("ents_r", 0.0), 4),
        "f1": round(scores.get("ents_f", 0.0), 4),
        "eval_documents": len(examples),
    }
