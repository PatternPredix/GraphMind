"""Transformer-based relation extraction auto-annotation.

Builds a sentence-classification dataset from human-annotated relations:
each candidate entity pair is rendered as text with entity markers
([E1]...[/E1], [E2]...[/E2]) and labeled with its relation type, or
"no_relation" for pairs the annotator left unlinked (negative sampling).
A BERT-family model (default DistilBERT, configurable to BERT/SpanBERT via
RE_BASE_MODEL) is fine-tuned and then proposes relations for documents that
have entities but no human relations. GPU is used automatically if present.
"""
import os
import random
from typing import Callable, Dict, List, Tuple

from sqlalchemy.orm import selectinload

from ..config import settings
from ..database import SessionLocal
from ..models import Document, Relation, RelationType, Span
from .jobs import MissingDependencyError

NO_RELATION = "no_relation"
MAX_PAIR_DISTANCE = 400  # max chars between the two entities of a candidate pair
CONTEXT_WINDOW = 150  # chars of context kept on each side of the pair
NEGATIVE_RATIO = 3  # negatives per positive during training
MIN_TRAIN_RELATIONS = 10
EPOCHS = 4
BATCH_SIZE = 16
PREDICT_CONFIDENCE_THRESHOLD = 0.70


def run_re_job(project_id: int, update: Callable) -> None:
    try:
        import numpy as np
        import torch
        from torch.utils.data import DataLoader, Dataset
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
        )
    except ImportError:
        raise MissingDependencyError(
            "PyTorch/transformers are not installed on the server. Install ML "
            "dependencies with: pip install -r requirements-ml.txt"
        )

    if torch.cuda.is_available():
        device = "cuda"  # NVIDIA GPU (Windows/Linux)
    elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        device = "mps"  # Apple Silicon GPU (M-series Macs)
    else:
        device = "cpu"
    update(status="training", progress=0.0,
           message=f"Collecting training pairs (device: {device})")

    db = SessionLocal()
    try:
        relation_types = {
            rt.id: rt.name
            for rt in db.query(RelationType).filter(RelationType.project_id == project_id)
        }
        docs = (
            db.query(Document)
            .options(selectinload(Document.spans), selectinload(Document.relations))
            .filter(Document.project_id == project_id)
            .all()
        )
        train_texts: List[str] = []
        train_labels: List[str] = []
        predict_candidates: List[Tuple[int, int, int, str]] = []
        # (doc_id, from_span_id, to_span_id, marked_text)

        rng = random.Random(42)
        for doc in docs:
            spans = sorted(doc.spans, key=lambda s: s.start_offset)
            usable = [s for s in spans if s.source == "human" or s.reviewed]
            human_relations = [r for r in doc.relations if r.source == "human" or r.reviewed]
            related: Dict[Tuple[int, int], str] = {
                (r.from_span_id, r.to_span_id): relation_types.get(r.relation_type_id, "")
                for r in human_relations
            }

            pairs = _candidate_pairs(usable)
            if human_relations:
                negatives = []
                for a, b in pairs:
                    label = related.get((a.id, b.id))
                    marked = _mark_pair(doc.text, a, b)
                    if label:
                        train_texts.append(marked)
                        train_labels.append(label)
                    else:
                        negatives.append(marked)
                n_pos_doc = sum(1 for a, b in pairs if (a.id, b.id) in related)
                rng.shuffle(negatives)
                for marked in negatives[: max(1, n_pos_doc * NEGATIVE_RATIO)]:
                    train_texts.append(marked)
                    train_labels.append(NO_RELATION)
            elif len(usable) >= 2:
                for a, b in pairs:
                    predict_candidates.append(
                        (doc.id, a.id, b.id, _mark_pair(doc.text, a, b))
                    )
    finally:
        db.close()

    n_positive = sum(1 for label in train_labels if label != NO_RELATION)
    if n_positive < MIN_TRAIN_RELATIONS:
        update(
            status="failed",
            message=f"Need at least {MIN_TRAIN_RELATIONS} human-annotated relations "
            f"to train (found {n_positive}).",
        )
        return

    labels = sorted(set(train_labels) | {NO_RELATION})
    label2id = {label: i for i, label in enumerate(labels)}
    id2label = {i: label for label, i in label2id.items()}

    update(message=f"Fine-tuning {settings.RE_BASE_MODEL} on "
           f"{len(train_texts)} pairs ({n_positive} positive) using {device}")

    tokenizer = AutoTokenizer.from_pretrained(settings.RE_BASE_MODEL)
    tokenizer.add_special_tokens(
        {"additional_special_tokens": ["[E1]", "[/E1]", "[E2]", "[/E2]"]}
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        settings.RE_BASE_MODEL,
        num_labels=len(labels),
        id2label=id2label,
        label2id=label2id,
    )
    model.resize_token_embeddings(len(tokenizer))
    model.to(device)

    class PairDataset(Dataset):
        def __init__(self, texts, labels=None):
            self.encodings = tokenizer(
                texts, truncation=True, padding=True, max_length=256, return_tensors="pt"
            )
            self.labels = labels

        def __len__(self):
            return self.encodings["input_ids"].shape[0]

        def __getitem__(self, idx):
            item = {k: v[idx] for k, v in self.encodings.items()}
            if self.labels is not None:
                item["labels"] = torch.tensor(label2id[self.labels[idx]])
            return item

    dataset = PairDataset(train_texts, train_labels)
    loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-5)

    model.train()
    total_steps = EPOCHS * max(1, len(loader))
    step = 0
    for epoch in range(EPOCHS):
        epoch_loss = 0.0
        for batch in loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            outputs = model(**batch)
            loss = outputs.loss
            loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            epoch_loss += loss.item()
            step += 1
            if step % 10 == 0:
                update(progress=0.7 * step / total_steps)
        update(
            progress=0.7 * (epoch + 1) / EPOCHS,
            message=f"Epoch {epoch + 1}/{EPOCHS}, loss {epoch_loss / max(1, len(loader)):.4f}",
        )

    model_dir = os.path.join(settings.MODELS_DIR, f"project_{project_id}", "re")
    os.makedirs(model_dir, exist_ok=True)
    model.save_pretrained(model_dir)
    tokenizer.save_pretrained(model_dir)

    metrics = {
        "training_pairs": len(train_texts),
        "positive_pairs": n_positive,
        "labels": [label for label in labels if label != NO_RELATION],
        "device": device,
        "base_model": settings.RE_BASE_MODEL,
        "model_path": model_dir,
    }

    # ---- Predict relations for unannotated documents ----
    update(status="annotating", progress=0.7, metrics=metrics,
           message=f"Scoring {len(predict_candidates)} candidate pairs")
    name_to_type_id = {v: k for k, v in relation_types.items()}
    model.eval()
    annotated_docs = set()
    created = 0
    BATCH = 64
    softmax = torch.nn.Softmax(dim=-1)
    for start in range(0, len(predict_candidates), BATCH):
        chunk = predict_candidates[start : start + BATCH]
        enc = tokenizer(
            [c[3] for c in chunk],
            truncation=True,
            padding=True,
            max_length=256,
            return_tensors="pt",
        ).to(device)
        with torch.no_grad():
            probs = softmax(model(**enc).logits).cpu().numpy()
        best = np.argmax(probs, axis=-1)

        db = SessionLocal()
        try:
            for (doc_id, from_id, to_id, _), label_idx, prob_row in zip(chunk, best, probs):
                label = id2label[int(label_idx)]
                confidence = float(prob_row[label_idx])
                if label == NO_RELATION or confidence < PREDICT_CONFIDENCE_THRESHOLD:
                    continue
                type_id = name_to_type_id.get(label)
                if type_id is None:
                    continue
                db.add(
                    Relation(
                        document_id=doc_id,
                        relation_type_id=type_id,
                        from_span_id=from_id,
                        to_span_id=to_id,
                        source="model",
                        confidence=round(confidence, 4),
                        reviewed=False,
                    )
                )
                annotated_docs.add(doc_id)
                created += 1
            db.commit()
        finally:
            db.close()
        done = start + len(chunk)
        update(
            progress=0.7 + 0.3 * done / max(1, len(predict_candidates)),
            annotated=len(annotated_docs),
            message=f"Scored {done}/{len(predict_candidates)} pairs, "
            f"created {created} relations",
        )

    update(
        status="completed",
        progress=1.0,
        annotated=len(annotated_docs),
        metrics=metrics,
        message=f"Done. Proposed {created} relations across {len(annotated_docs)} "
        "documents — review them under the 'Needs review' filter.",
    )


def _candidate_pairs(spans) -> List[Tuple]:
    """Ordered span pairs within MAX_PAIR_DISTANCE characters of each other."""
    pairs = []
    for i, a in enumerate(spans):
        for b in spans[i + 1 :]:
            if b.start_offset - a.end_offset > MAX_PAIR_DISTANCE:
                break
            pairs.append((a, b))
            pairs.append((b, a))
    return pairs


def _mark_pair(text: str, from_span, to_span) -> str:
    """Insert [E1]/[E2] markers around the pair, clipped to a context window."""
    first, second = sorted([from_span, to_span], key=lambda s: s.start_offset)
    tag_first = "E1" if first is from_span else "E2"
    tag_second = "E1" if second is from_span else "E2"
    window_start = max(0, first.start_offset - CONTEXT_WINDOW)
    window_end = min(len(text), second.end_offset + CONTEXT_WINDOW)
    return (
        text[window_start : first.start_offset]
        + f"[{tag_first}] "
        + text[first.start_offset : first.end_offset]
        + f" [/{tag_first}]"
        + text[first.end_offset : second.start_offset]
        + f"[{tag_second}] "
        + text[second.start_offset : second.end_offset]
        + f" [/{tag_second}]"
        + text[second.end_offset : window_end]
    )
