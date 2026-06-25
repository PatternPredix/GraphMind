from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_project_for_user
from ..config import settings
from ..database import get_db
from ..ml.jobs import MissingDependencyError, submit_job
from ..models import (
    Document,
    EntityKeywordRule,
    EntityType,
    RelationRule,
    RelationType,
    TrainingJob,
    User,
)
from ..schemas import (
    KeywordRuleCreate,
    KeywordRuleOut,
    RelationRuleCreate,
    RelationRuleOut,
    TrainingJobOut,
)

router = APIRouter(prefix="/api/projects/{project_id}/rules", tags=["rules"])


def _entity_type(project_id: int, type_id: int, db: Session) -> EntityType:
    et = db.get(EntityType, type_id)
    if et is None or et.project_id != project_id:
        raise HTTPException(status_code=400, detail=f"Invalid entity type {type_id}")
    return et


# ---------- Keyword (gazetteer) rules ----------

@router.get("/keyword", response_model=list[KeywordRuleOut])
def list_keyword_rules(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    return (
        db.query(EntityKeywordRule)
        .filter(EntityKeywordRule.project_id == project_id)
        .order_by(EntityKeywordRule.id)
        .all()
    )


@router.post("/keyword", response_model=KeywordRuleOut)
def create_keyword_rule(
    project_id: int,
    payload: KeywordRuleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    _entity_type(project_id, payload.entity_type_id, db)
    existing = (
        db.query(EntityKeywordRule)
        .filter(
            EntityKeywordRule.project_id == project_id,
            EntityKeywordRule.entity_type_id == payload.entity_type_id,
            EntityKeywordRule.keyword == payload.keyword,
            EntityKeywordRule.case_sensitive == payload.case_sensitive,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Identical keyword rule already exists")
    rule = EntityKeywordRule(
        project_id=project_id,
        entity_type_id=payload.entity_type_id,
        keyword=payload.keyword,
        case_sensitive=payload.case_sensitive,
        whole_word=payload.whole_word,
        created_by=user.id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/keyword/{rule_id}")
def delete_keyword_rule(
    project_id: int,
    rule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    rule = db.get(EntityKeywordRule, rule_id)
    if rule is None or rule.project_id != project_id:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return {"deleted": rule_id}


@router.post("/keyword/apply", response_model=TrainingJobOut)
def apply_keyword_rules(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Apply all keyword rules across the whole corpus as a background job."""
    get_project_for_user(project_id, user, db)
    if (
        db.query(EntityKeywordRule.id)
        .filter(EntityKeywordRule.project_id == project_id)
        .first()
        is None
    ):
        raise HTTPException(status_code=400, detail="No keyword rules to apply")
    return _start_rule_job(project_id, "ner_rules", db, user)


# ---------- Embedding-similarity relation rules ----------

@router.get("/relation", response_model=list[RelationRuleOut])
def list_relation_rules(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    rules = (
        db.query(RelationRule)
        .filter(RelationRule.project_id == project_id)
        .order_by(RelationRule.id)
        .all()
    )
    return [_relation_rule_out(r) for r in rules]


@router.post("/relation", response_model=RelationRuleOut)
def create_relation_rule(
    project_id: int,
    payload: RelationRuleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    rt = db.get(RelationType, payload.relation_type_id)
    if rt is None or rt.project_id != project_id:
        raise HTTPException(status_code=400, detail="Invalid relation type")
    _entity_type(project_id, payload.head_entity_type_id, db)
    _entity_type(project_id, payload.tail_entity_type_id, db)

    # Embed the description once, now, and cache it on the rule.
    from ..ml.relation_rules import compute_description_embedding

    try:
        vector, model_name = compute_description_embedding(payload.description)
    except MissingDependencyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    rule = RelationRule(
        project_id=project_id,
        relation_type_id=payload.relation_type_id,
        head_entity_type_id=payload.head_entity_type_id,
        tail_entity_type_id=payload.tail_entity_type_id,
        description=payload.description,
        embedding=vector,
        embedding_model=model_name,
        threshold=payload.threshold
        if payload.threshold is not None
        else settings.DEFAULT_RELATION_RULE_THRESHOLD,
        max_distance=payload.max_distance,
        created_by=user.id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _relation_rule_out(rule)


@router.delete("/relation/{rule_id}")
def delete_relation_rule(
    project_id: int,
    rule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    rule = db.get(RelationRule, rule_id)
    if rule is None or rule.project_id != project_id:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return {"deleted": rule_id}


@router.post("/relation/apply", response_model=TrainingJobOut)
def apply_relation_rules(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    if (
        db.query(RelationRule.id)
        .filter(RelationRule.project_id == project_id)
        .first()
        is None
    ):
        raise HTTPException(status_code=400, detail="No relation rules to apply")
    return _start_rule_job(project_id, "re_rules", db, user)


# ---------- Shared helpers ----------

def _relation_rule_out(rule: RelationRule) -> RelationRuleOut:
    return RelationRuleOut(
        id=rule.id,
        relation_type_id=rule.relation_type_id,
        head_entity_type_id=rule.head_entity_type_id,
        tail_entity_type_id=rule.tail_entity_type_id,
        description=rule.description,
        embedding_model=rule.embedding_model,
        threshold=rule.threshold,
        max_distance=rule.max_distance,
        has_embedding=bool(rule.embedding),
    )


def _start_rule_job(project_id: int, task: str, db: Session, user: User) -> TrainingJob:
    running = (
        db.query(TrainingJob)
        .filter(
            TrainingJob.project_id == project_id,
            TrainingJob.task == task,
            TrainingJob.status.in_(["queued", "training", "annotating"]),
        )
        .first()
    )
    if running:
        raise HTTPException(status_code=409, detail="A matching job is already running")
    has_docs = (
        db.query(Document.id).filter(Document.project_id == project_id).first() is not None
    )
    if not has_docs:
        raise HTTPException(status_code=400, detail="No documents to annotate")
    job = TrainingJob(
        project_id=project_id,
        task=task,
        status="queued",
        message="Waiting for worker",
        created_by=user.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    submit_job(job.id)
    return job
