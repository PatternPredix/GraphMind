from __future__ import annotations

import random

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from .. import jsonl_formats
from ..auth import get_current_user, get_project_for_user
from ..database import get_db
from ..models import Document, EntityType, Relation, RelationType, Span, User
from ..schemas import ImportResult

router = APIRouter(prefix="/api/projects/{project_id}", tags=["import-export"])

PALETTE = [
    "#f87171", "#fb923c", "#fbbf24", "#a3e635", "#34d399",
    "#22d3ee", "#60a5fa", "#a78bfa", "#f472b6", "#94a3b8",
]


def _looks_like_jsonl(content: str) -> bool:
    """True if the first non-empty line looks like a JSON object (starts '{')."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped.startswith("{")
    return False


def _resolve_format(format: str, content: str, filename: str | None) -> str:
    """Map format='auto' to a concrete format by sniffing the file."""
    if format != "auto":
        return format
    name = (filename or "").lower()
    if name.endswith(".jsonl") or name.endswith(".json"):
        return "jsonl"
    if _looks_like_jsonl(content):
        return "jsonl"
    return "text_lines"


@router.post("/import", response_model=ImportResult)
async def import_file(
    project_id: int,
    file: UploadFile = File(...),
    format: str = Query("auto", pattern="^(auto|jsonl|text|text_lines)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Import documents (and annotations, for JSONL) from supported file formats.

    format=auto        detect JSONL vs. plain text from the file (default)
    format=jsonl       JSONL with entities/relations (or legacy span labels)
    format=text        one document per file
    format=text_lines  one document per line
    """
    get_project_for_user(project_id, user, db)
    raw = await file.read()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    resolved = _resolve_format(format, content, file.filename)

    warnings: list[str] = []
    if resolved == "jsonl":
        parsed, warnings = jsonl_formats.parse_jsonl(content)
    else:
        parsed = jsonl_formats.parse_plain_text(
            content, one_doc_per_line=(resolved == "text_lines")
        )
    if not parsed:
        if resolved == "jsonl" and not _looks_like_jsonl(content):
            detail = (
                "This file doesn't look like JSONL (no JSON objects found). "
                "If it's plain text, re-import with the "
                "\"Text — one doc per line\" format."
            )
        elif resolved != "jsonl" and _looks_like_jsonl(content):
            detail = (
                "This looks like a JSONL file. Re-import with the "
                "\"JSONL (entities + relations)\" format."
            )
        else:
            detail = "No documents found in the file (it appears to be empty)."
        raise HTTPException(status_code=400, detail=detail)

    entity_types = {
        et.name: et
        for et in db.query(EntityType).filter(EntityType.project_id == project_id)
    }
    relation_types = {
        rt.name: rt
        for rt in db.query(RelationType).filter(RelationType.project_id == project_id)
    }
    created_entity_types: list[str] = []
    created_relation_types: list[str] = []

    max_order = (
        db.query(func.coalesce(func.max(Document.order_index), 0))
        .filter(Document.project_id == project_id)
        .scalar()
    )

    n_spans = 0
    n_relations = 0
    for offset, pdoc in enumerate(parsed, start=1):
        doc = Document(
            project_id=project_id,
            text=pdoc.text,
            meta=pdoc.meta,
            order_index=max_order + offset,
        )
        db.add(doc)
        db.flush()

        span_by_source_id = {}
        for source_id, label, start, end in pdoc.entities:
            if label not in entity_types:
                et = EntityType(
                    project_id=project_id,
                    name=label,
                    color=random.choice(PALETTE),
                )
                db.add(et)
                db.flush()
                entity_types[label] = et
                created_entity_types.append(label)
            span = Span(
                document_id=doc.id,
                entity_type_id=entity_types[label].id,
                start_offset=start,
                end_offset=end,
                source="human",
                reviewed=True,
                created_by=user.id,
            )
            db.add(span)
            db.flush()
            if source_id is not None:
                span_by_source_id[source_id] = span
            n_spans += 1

        for from_id, to_id, rtype in pdoc.relations:
            from_span = span_by_source_id.get(from_id)
            to_span = span_by_source_id.get(to_id)
            if from_span is None or to_span is None:
                warnings.append(
                    f"document {offset}: relation references unknown entity id, skipped"
                )
                continue
            if rtype not in relation_types:
                rt = RelationType(
                    project_id=project_id,
                    name=rtype,
                    color=random.choice(PALETTE),
                )
                db.add(rt)
                db.flush()
                relation_types[rtype] = rt
                created_relation_types.append(rtype)
            db.add(
                Relation(
                    document_id=doc.id,
                    relation_type_id=relation_types[rtype].id,
                    from_span_id=from_span.id,
                    to_span_id=to_span.id,
                    source="human",
                    reviewed=True,
                    created_by=user.id,
                )
            )
            n_relations += 1

    db.commit()
    return ImportResult(
        imported_documents=len(parsed),
        imported_spans=n_spans,
        imported_relations=n_relations,
        created_entity_types=created_entity_types,
        created_relation_types=created_relation_types,
        warnings=warnings[:50],
    )


@router.get("/export", response_class=PlainTextResponse)
def export_project(
    project_id: int,
    format: str = Query("jsonl", pattern="^(jsonl|jsonl_legacy|conll)$"),
    only_confirmed: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    query = (
        db.query(Document)
        .options(
            selectinload(Document.spans).selectinload(Span.entity_type),
            selectinload(Document.relations).selectinload(Relation.relation_type),
        )
        .filter(Document.project_id == project_id)
    )
    if only_confirmed:
        query = query.filter(Document.is_confirmed.is_(True))
    docs = query.order_by(Document.order_index, Document.id).all()

    serializable = []
    for d in docs:
        serializable.append(
            {
                "id": d.id,
                "text": d.text,
                "meta": d.meta or {},
                "entities": [
                    {
                        "id": s.id,
                        "label": s.entity_type.name,
                        "start": s.start_offset,
                        "end": s.end_offset,
                    }
                    for s in sorted(d.spans, key=lambda s: s.start_offset)
                ],
                "relations": [
                    {
                        "id": r.id,
                        "from_id": r.from_span_id,
                        "to_id": r.to_span_id,
                        "type": r.relation_type.name,
                    }
                    for r in d.relations
                ],
            }
        )

    if format == "jsonl":
        body = jsonl_formats.export_jsonl(serializable)
        filename = "export.jsonl"
    elif format == "jsonl_legacy":
        body = jsonl_formats.export_legacy_jsonl(serializable)
        filename = "export_legacy.jsonl"
    else:
        body = jsonl_formats.export_conll(serializable)
        filename = "export.conll"

    return PlainTextResponse(
        body,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        media_type="application/octet-stream",
    )
