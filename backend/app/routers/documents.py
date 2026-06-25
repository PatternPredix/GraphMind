from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, exists, func, or_, tuple_
from sqlalchemy.orm import Session, selectinload

from ..auth import get_current_user, get_project_for_user
from ..database import get_db
from ..models import Document, Relation, Span, User
from ..schemas import (
    BulkDelete,
    ConfirmRequest,
    DocumentCreate,
    DocumentDetail,
    DocumentPage,
    DocumentSummary,
    RelationOut,
    SpanOut,
)

router = APIRouter(prefix="/api/projects/{project_id}/documents", tags=["documents"])

SNIPPET_LEN = 160


def _apply_filter(query, doc_filter: str):
    if doc_filter == "confirmed":
        return query.filter(Document.is_confirmed.is_(True))
    if doc_filter == "unconfirmed":
        return query.filter(Document.is_confirmed.is_(False))
    if doc_filter == "unreviewed":
        has_unreviewed_span = exists().where(
            and_(Span.document_id == Document.id, Span.reviewed.is_(False))
        )
        has_unreviewed_rel = exists().where(
            and_(Relation.document_id == Document.id, Relation.reviewed.is_(False))
        )
        return query.filter(or_(has_unreviewed_span, has_unreviewed_rel))
    return query


@router.get("", response_model=DocumentPage)
def list_documents(
    project_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    search: str = "",
    doc_filter: str = Query("all", alias="filter"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    query = db.query(Document).filter(Document.project_id == project_id)
    query = _apply_filter(query, doc_filter)
    if search:
        query = query.filter(Document.text.ilike(f"%{search}%"))
    total = query.count()
    docs = (
        query.options(selectinload(Document.spans), selectinload(Document.relations))
        .order_by(Document.order_index, Document.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        DocumentSummary(
            id=d.id,
            snippet=d.text[:SNIPPET_LEN] + ("…" if len(d.text) > SNIPPET_LEN else ""),
            is_confirmed=d.is_confirmed,
            span_count=len(d.spans),
            relation_count=len(d.relations),
            has_unreviewed=any(not s.reviewed for s in d.spans)
            or any(not r.reviewed for r in d.relations),
        )
        for d in docs
    ]
    return DocumentPage(total=total, page=page, page_size=page_size, items=items)


@router.post("", response_model=DocumentDetail)
def create_document(
    project_id: int,
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    max_order = (
        db.query(func.coalesce(func.max(Document.order_index), 0))
        .filter(Document.project_id == project_id)
        .scalar()
    )
    doc = Document(
        project_id=project_id,
        text=payload.text,
        meta=payload.meta,
        order_index=max_order + 1,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _document_detail(doc, project_id, "all", db)


def _get_doc(project_id: int, document_id: int, db: Session) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _document_detail(
    doc: Document, project_id: int, doc_filter: str, db: Session
) -> DocumentDetail:
    base = db.query(Document).filter(Document.project_id == project_id)
    base = _apply_filter(base, doc_filter)
    key = tuple_(Document.order_index, Document.id)
    current_key = (doc.order_index, doc.id)

    prev_doc = (
        base.filter(key < current_key)
        .order_by(Document.order_index.desc(), Document.id.desc())
        .with_entities(Document.id)
        .first()
    )
    next_doc = (
        base.filter(key > current_key)
        .order_by(Document.order_index, Document.id)
        .with_entities(Document.id)
        .first()
    )
    position = base.filter(key <= current_key).count()
    total = base.count()
    return DocumentDetail(
        id=doc.id,
        text=doc.text,
        meta=doc.meta or {},
        is_confirmed=doc.is_confirmed,
        spans=[SpanOut.model_validate(s) for s in doc.spans],
        relations=[RelationOut.model_validate(r) for r in doc.relations],
        prev_id=prev_doc[0] if prev_doc else None,
        next_id=next_doc[0] if next_doc else None,
        position=position,
        total=total,
    )


@router.get("/first", response_model=Optional[DocumentDetail])
def first_document(
    project_id: int,
    doc_filter: str = Query("all", alias="filter"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """First document under the given filter — entry point for annotation."""
    get_project_for_user(project_id, user, db)
    base = db.query(Document).filter(Document.project_id == project_id)
    base = _apply_filter(base, doc_filter)
    doc = base.order_by(Document.order_index, Document.id).first()
    if doc is None:
        return None
    return _document_detail(doc, project_id, doc_filter, db)


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    project_id: int,
    document_id: int,
    doc_filter: str = Query("all", alias="filter"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    doc = _get_doc(project_id, document_id, db)
    return _document_detail(doc, project_id, doc_filter, db)


@router.delete("/{document_id}")
def delete_document(
    project_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    doc = _get_doc(project_id, document_id, db)
    db.delete(doc)
    db.commit()
    return {"deleted": [document_id]}


@router.post("/bulk-delete")
def bulk_delete(
    project_id: int,
    payload: BulkDelete,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    docs = (
        db.query(Document)
        .filter(Document.project_id == project_id, Document.id.in_(payload.document_ids))
        .all()
    )
    deleted = [d.id for d in docs]
    for d in docs:
        db.delete(d)
    db.commit()
    return {"deleted": deleted}


@router.post("/{document_id}/confirm", response_model=DocumentDetail)
def confirm_document(
    project_id: int,
    document_id: int,
    payload: ConfirmRequest,
    doc_filter: str = Query("all", alias="filter"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    doc = _get_doc(project_id, document_id, db)
    doc.is_confirmed = payload.is_confirmed
    doc.confirmed_by = user.id if payload.is_confirmed else None
    db.commit()
    db.refresh(doc)
    return _document_detail(doc, project_id, doc_filter, db)
