"""Keyword (gazetteer) rules for NER — pure Python, no ML dependency.

A keyword rule maps a literal keyword to an entity type. Applying the rules
scans every document and creates an entity span for each occurrence that does
not already exist (idempotent). Rule spans are stored with source="rule" and
reviewed=True, so they count as ground truth for training and export while
remaining distinguishable from manual annotations.
"""
from typing import Callable, Dict, List, Tuple

from sqlalchemy.orm import selectinload

from .database import SessionLocal
from .models import Document, EntityKeywordRule, Span

_WORD_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
)


def find_matches(
    text: str, keyword: str, case_sensitive: bool, whole_word: bool
) -> List[Tuple[int, int]]:
    """Return [start, end) offsets of every occurrence of `keyword` in `text`."""
    if not keyword:
        return []
    haystack = text if case_sensitive else text.lower()
    needle = keyword if case_sensitive else keyword.lower()
    matches: List[Tuple[int, int]] = []
    start = 0
    klen = len(needle)
    while True:
        idx = haystack.find(needle, start)
        if idx == -1:
            break
        end = idx + klen
        if not whole_word or _is_whole_word(text, idx, end):
            matches.append((idx, end))
        start = idx + 1  # allow overlapping matches; dedup happens on insert
    return matches


def _is_whole_word(text: str, start: int, end: int) -> bool:
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    return before not in _WORD_CHARS and after not in _WORD_CHARS


def run_keyword_rules_job(project_id: int, update: Callable) -> None:
    update(status="annotating", progress=0.0, message="Loading keyword rules")
    db = SessionLocal()
    try:
        rules = (
            db.query(EntityKeywordRule)
            .filter(EntityKeywordRule.project_id == project_id)
            .all()
        )
        rule_specs = [
            (r.keyword, r.case_sensitive, r.whole_word, r.entity_type_id) for r in rules
        ]
        doc_ids = [
            d.id
            for d in db.query(Document.id)
            .filter(Document.project_id == project_id)
            .all()
        ]
    finally:
        db.close()

    if not rule_specs:
        update(status="failed", message="No keyword rules defined.")
        return

    total_docs = len(doc_ids)
    created = 0
    affected_docs = 0
    BATCH = 200
    for batch_start in range(0, total_docs, BATCH):
        batch_ids = doc_ids[batch_start : batch_start + BATCH]
        db = SessionLocal()
        try:
            docs = (
                db.query(Document)
                .options(selectinload(Document.spans))
                .filter(Document.id.in_(batch_ids))
                .all()
            )
            for doc in docs:
                existing: Dict[Tuple[int, int, int], bool] = {
                    (s.start_offset, s.end_offset, s.entity_type_id): True
                    for s in doc.spans
                }
                doc_added = 0
                for keyword, case_sensitive, whole_word, type_id in rule_specs:
                    for start, end in find_matches(
                        doc.text, keyword, case_sensitive, whole_word
                    ):
                        key = (start, end, type_id)
                        if key in existing:
                            continue
                        existing[key] = True
                        db.add(
                            Span(
                                document_id=doc.id,
                                entity_type_id=type_id,
                                start_offset=start,
                                end_offset=end,
                                source="rule",
                                reviewed=True,
                            )
                        )
                        created += 1
                        doc_added += 1
                if doc_added:
                    affected_docs += 1
            db.commit()
        finally:
            db.close()
        done = batch_start + len(batch_ids)
        update(
            progress=done / max(1, total_docs),
            annotated=affected_docs,
            message=f"Scanned {done}/{total_docs} documents, "
            f"created {created} entity spans",
        )

    update(
        status="completed",
        progress=1.0,
        annotated=affected_docs,
        metrics={
            "rules_applied": len(rule_specs),
            "spans_created": created,
            "documents_affected": affected_docs,
        },
        message=f"Done. Created {created} entity spans across {affected_docs} "
        f"documents from {len(rule_specs)} keyword rule(s).",
    )
