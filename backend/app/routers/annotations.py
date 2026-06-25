from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_project_for_user
from ..database import get_db
from ..models import Document, EntityType, Relation, RelationType, Span, User
from ..schemas import (
    RelationCreate,
    RelationOut,
    RelationUpdate,
    SpanCreate,
    SpanOut,
    SpanUpdate,
)

router = APIRouter(prefix="/api/projects/{project_id}/documents/{document_id}", tags=["annotations"])


def _get_doc(project_id: int, document_id: int, db: Session) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


# ---------- Spans ----------

@router.post("/spans", response_model=SpanOut)
def create_span(
    project_id: int,
    document_id: int,
    payload: SpanCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    doc = _get_doc(project_id, document_id, db)
    et = db.get(EntityType, payload.entity_type_id)
    if et is None or et.project_id != project_id:
        raise HTTPException(status_code=400, detail="Invalid entity type")
    if not (0 <= payload.start_offset < payload.end_offset <= len(doc.text)):
        raise HTTPException(status_code=400, detail="Span offsets out of bounds")
    duplicate = (
        db.query(Span)
        .filter(
            Span.document_id == document_id,
            Span.start_offset == payload.start_offset,
            Span.end_offset == payload.end_offset,
            Span.entity_type_id == payload.entity_type_id,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Identical span already exists")
    span = Span(
        document_id=document_id,
        entity_type_id=payload.entity_type_id,
        start_offset=payload.start_offset,
        end_offset=payload.end_offset,
        source="human",
        reviewed=True,
        created_by=user.id,
    )
    db.add(span)
    db.commit()
    db.refresh(span)
    return span


@router.patch("/spans/{span_id}", response_model=SpanOut)
def update_span(
    project_id: int,
    document_id: int,
    span_id: int,
    payload: SpanUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    _get_doc(project_id, document_id, db)
    span = db.get(Span, span_id)
    if span is None or span.document_id != document_id:
        raise HTTPException(status_code=404, detail="Span not found")
    if payload.entity_type_id is not None:
        et = db.get(EntityType, payload.entity_type_id)
        if et is None or et.project_id != project_id:
            raise HTTPException(status_code=400, detail="Invalid entity type")
        span.entity_type_id = payload.entity_type_id
    if payload.reviewed is not None:
        span.reviewed = payload.reviewed
    db.commit()
    db.refresh(span)
    return span


@router.delete("/spans/{span_id}")
def delete_span(
    project_id: int,
    document_id: int,
    span_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    _get_doc(project_id, document_id, db)
    span = db.get(Span, span_id)
    if span is None or span.document_id != document_id:
        raise HTTPException(status_code=404, detail="Span not found")
    # Remove relations attached to this span first.
    db.query(Relation).filter(
        Relation.document_id == document_id,
        (Relation.from_span_id == span_id) | (Relation.to_span_id == span_id),
    ).delete(synchronize_session=False)
    db.delete(span)
    db.commit()
    return {"deleted": span_id}


# ---------- Relations ----------

@router.post("/relations", response_model=RelationOut)
def create_relation(
    project_id: int,
    document_id: int,
    payload: RelationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    _get_doc(project_id, document_id, db)
    rt = db.get(RelationType, payload.relation_type_id)
    if rt is None or rt.project_id != project_id:
        raise HTTPException(status_code=400, detail="Invalid relation type")
    if payload.from_span_id == payload.to_span_id:
        raise HTTPException(status_code=400, detail="Relation must connect two different spans")
    from_span = db.get(Span, payload.from_span_id)
    to_span = db.get(Span, payload.to_span_id)
    for s in (from_span, to_span):
        if s is None or s.document_id != document_id:
            raise HTTPException(status_code=400, detail="Span not in this document")
    duplicate = (
        db.query(Relation)
        .filter(
            Relation.document_id == document_id,
            Relation.from_span_id == payload.from_span_id,
            Relation.to_span_id == payload.to_span_id,
            Relation.relation_type_id == payload.relation_type_id,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Identical relation already exists")
    relation = Relation(
        document_id=document_id,
        relation_type_id=payload.relation_type_id,
        from_span_id=payload.from_span_id,
        to_span_id=payload.to_span_id,
        source="human",
        reviewed=True,
        created_by=user.id,
    )
    db.add(relation)
    db.commit()
    db.refresh(relation)
    return relation


@router.patch("/relations/{relation_id}", response_model=RelationOut)
def update_relation(
    project_id: int,
    document_id: int,
    relation_id: int,
    payload: RelationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    _get_doc(project_id, document_id, db)
    relation = db.get(Relation, relation_id)
    if relation is None or relation.document_id != document_id:
        raise HTTPException(status_code=404, detail="Relation not found")
    if payload.relation_type_id is not None:
        rt = db.get(RelationType, payload.relation_type_id)
        if rt is None or rt.project_id != project_id:
            raise HTTPException(status_code=400, detail="Invalid relation type")
        relation.relation_type_id = payload.relation_type_id
    if payload.reviewed is not None:
        relation.reviewed = payload.reviewed
    db.commit()
    db.refresh(relation)
    return relation


@router.delete("/relations/{relation_id}")
def delete_relation(
    project_id: int,
    document_id: int,
    relation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    _get_doc(project_id, document_id, db)
    relation = db.get(Relation, relation_id)
    if relation is None or relation.document_id != document_id:
        raise HTTPException(status_code=404, detail="Relation not found")
    db.delete(relation)
    db.commit()
    return {"deleted": relation_id}


# ---------- Review of model annotations ----------

@router.post("/review")
def review_document(
    project_id: int,
    document_id: int,
    action: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Accept or reject all unreviewed model annotations in a document.

    action=accept_all marks them reviewed; action=reject_all deletes them.
    """
    get_project_for_user(project_id, user, db)
    _get_doc(project_id, document_id, db)
    if action == "accept_all":
        n_spans = (
            db.query(Span)
            .filter(Span.document_id == document_id, Span.reviewed.is_(False))
            .update({"reviewed": True}, synchronize_session=False)
        )
        n_rels = (
            db.query(Relation)
            .filter(Relation.document_id == document_id, Relation.reviewed.is_(False))
            .update({"reviewed": True}, synchronize_session=False)
        )
    elif action == "reject_all":
        unreviewed_span_ids = [
            s.id
            for s in db.query(Span.id)
            .filter(Span.document_id == document_id, Span.reviewed.is_(False))
            .all()
        ]
        n_rels = db.query(Relation).filter(
            Relation.document_id == document_id,
            Relation.reviewed.is_(False)
            | Relation.from_span_id.in_(unreviewed_span_ids)
            | Relation.to_span_id.in_(unreviewed_span_ids),
        ).delete(synchronize_session=False)
        n_spans = (
            db.query(Span)
            .filter(Span.document_id == document_id, Span.reviewed.is_(False))
            .delete(synchronize_session=False)
        )
    else:
        raise HTTPException(status_code=400, detail="action must be accept_all or reject_all")
    db.commit()
    return {"spans": n_spans, "relations": n_rels, "action": action}
