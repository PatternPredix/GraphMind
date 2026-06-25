"""Embedding-similarity rules for relation extraction.

A relation rule pairs two entity types (head, tail) with a relation type and a
natural-language description of the relation (e.g. "is the sibling of"). The
description is embedded once, when the rule is created, with a sentence-encoder
(a BERT-family bi-encoder — not an LLM) and the vector is cached on the rule.

Applying a rule scans documents for ordered entity pairs whose types match
(head, tail) and that lie within `max_distance` characters. The text spanning
each pair is embedded and compared (cosine similarity) against the cached
description vector; pairs scoring at or above the rule threshold get a relation
(source="rule", reviewed=False, confidence=similarity) for human review.
"""
import threading
from typing import Callable, Dict, List, Tuple

from sqlalchemy.orm import selectinload

from ..config import settings
from ..database import SessionLocal
from ..models import Document, Relation, RelationRule, Span
from .jobs import MissingDependencyError

# Loaded SentenceTransformer models, keyed by model name. Loading is expensive
# (and downloads on first use), so we keep encoders resident for the process.
_encoders: Dict[str, object] = {}
_encoder_lock = threading.Lock()


def _best_device() -> str:
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def get_encoder(model_name: str):
    """Return a cached SentenceTransformer, loading it on first use."""
    with _encoder_lock:
        if model_name not in _encoders:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError:
                raise MissingDependencyError(
                    "sentence-transformers is not installed on the server. Install "
                    "ML dependencies with: pip install -r requirements-ml.txt"
                )
            _encoders[model_name] = SentenceTransformer(model_name, device=_best_device())
        return _encoders[model_name]


def embed_texts(model_name: str, texts: List[str]) -> "list":
    """Return L2-normalized embeddings for `texts` as a numpy array."""
    encoder = get_encoder(model_name)
    return encoder.encode(
        texts, normalize_embeddings=True, convert_to_numpy=True, batch_size=64
    )


def compute_description_embedding(description: str) -> Tuple[List[float], str]:
    """Embed a rule description once. Returns (vector, model_name)."""
    model_name = settings.EMBEDDING_MODEL
    vector = embed_texts(model_name, [description])[0]
    return vector.tolist(), model_name


def pair_snippet(text: str, span_a: "Span", span_b: "Span") -> str:
    """Text spanning both entities (covers the entities and everything between)."""
    start = min(span_a.start_offset, span_b.start_offset)
    end = max(span_a.end_offset, span_b.end_offset)
    return text[start:end]


def cosine_to_matrix(query_vec, matrix) -> "list":
    """Cosine similarity of a 1-D query against rows of `matrix` (both assumed
    L2-normalized, so this is a plain dot product)."""
    import numpy as np

    return np.asarray(matrix) @ np.asarray(query_vec)


def _ordered_pairs(spans, head_type: int, tail_type: int, max_distance: int):
    """Yield (head_span, tail_span) pairs matching the rule's entity types."""
    ordered = sorted(spans, key=lambda s: s.start_offset)
    for i, s1 in enumerate(ordered):
        for s2 in ordered[i + 1 :]:
            if s2.start_offset - s1.end_offset > max_distance:
                break
            if s1.entity_type_id == head_type and s2.entity_type_id == tail_type:
                yield (s1, s2)
            # For asymmetric rules also consider the reverse ordering.
            if (
                head_type != tail_type
                and s1.entity_type_id == tail_type
                and s2.entity_type_id == head_type
            ):
                yield (s2, s1)


def run_relation_rules_job(project_id: int, update: Callable) -> None:
    import numpy as np

    update(status="annotating", progress=0.0, message="Loading relation rules")
    db = SessionLocal()
    try:
        rules = (
            db.query(RelationRule).filter(RelationRule.project_id == project_id).all()
        )
        rule_specs = [
            {
                "relation_type_id": r.relation_type_id,
                "head": r.head_entity_type_id,
                "tail": r.tail_entity_type_id,
                "threshold": r.threshold,
                "max_distance": r.max_distance,
                "embedding": np.asarray(r.embedding, dtype="float32"),
            }
            for r in rules
            if r.embedding
        ]
        model_name = rules[0].embedding_model if rules else settings.EMBEDDING_MODEL
        doc_ids = [
            d.id
            for d in db.query(Document.id)
            .filter(Document.project_id == project_id)
            .all()
        ]
    finally:
        db.close()

    if not rule_specs:
        update(status="failed", message="No relation rules with embeddings defined.")
        return

    # Warm the encoder up front so a missing dependency fails fast.
    get_encoder(model_name)

    total_docs = len(doc_ids)
    created = 0
    affected_docs = 0
    BATCH = 100
    for batch_start in range(0, total_docs, BATCH):
        batch_ids = doc_ids[batch_start : batch_start + BATCH]
        db = SessionLocal()
        try:
            docs = (
                db.query(Document)
                .options(selectinload(Document.spans), selectinload(Document.relations))
                .filter(Document.id.in_(batch_ids))
                .all()
            )
            # Collect candidate pairs across the batch, dedup snippet texts.
            candidates: List[dict] = []
            snippet_index: Dict[str, int] = {}
            snippets: List[str] = []
            for doc in docs:
                usable = [s for s in doc.spans if s.source == "human" or s.reviewed]
                existing_rel = {
                    (r.from_span_id, r.to_span_id, r.relation_type_id)
                    for r in doc.relations
                }
                for spec in rule_specs:
                    for head, tail in _ordered_pairs(
                        usable, spec["head"], spec["tail"], spec["max_distance"]
                    ):
                        key = (head.id, tail.id, spec["relation_type_id"])
                        if key in existing_rel:
                            continue
                        snippet = pair_snippet(doc.text, head, tail)
                        if snippet not in snippet_index:
                            snippet_index[snippet] = len(snippets)
                            snippets.append(snippet)
                        candidates.append(
                            {
                                "doc_id": doc.id,
                                "from_id": head.id,
                                "to_id": tail.id,
                                "spec": spec,
                                "snippet_idx": snippet_index[snippet],
                            }
                        )

            if candidates:
                matrix = embed_texts(model_name, snippets)  # (n_snippets, dim)
                docs_touched = set()
                for cand in candidates:
                    spec = cand["spec"]
                    sim = float(np.dot(matrix[cand["snippet_idx"]], spec["embedding"]))
                    if sim >= spec["threshold"]:
                        db.add(
                            Relation(
                                document_id=cand["doc_id"],
                                relation_type_id=spec["relation_type_id"],
                                from_span_id=cand["from_id"],
                                to_span_id=cand["to_id"],
                                source="rule",
                                confidence=round(sim, 4),
                                reviewed=False,
                            )
                        )
                        created += 1
                        docs_touched.add(cand["doc_id"])
                affected_docs += len(docs_touched)
                db.commit()
        finally:
            db.close()
        done = batch_start + len(batch_ids)
        update(
            progress=done / max(1, total_docs),
            annotated=affected_docs,
            message=f"Scanned {done}/{total_docs} documents, "
            f"proposed {created} relations",
        )

    update(
        status="completed",
        progress=1.0,
        annotated=affected_docs,
        metrics={
            "rules_applied": len(rule_specs),
            "relations_created": created,
            "documents_affected": affected_docs,
            "embedding_model": model_name,
        },
        message=f"Done. Proposed {created} relations across {affected_docs} "
        "documents — review them under the 'Needs review' filter.",
    )
