from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_project_for_user
from ..database import get_db
from ..ml.jobs import submit_job
from ..models import (
    Document,
    EntityType,
    Relation,
    RelationType,
    Span,
    TrainingJob,
    User,
)
from ..schemas import (
    AutoAnnotateEligibility,
    AutoAnnotateRequest,
    TrainingJobOut,
    TypeProgress,
)

router = APIRouter(prefix="/api/projects/{project_id}", tags=["auto-annotate"])


def _eligibility(project, task: str, db: Session) -> AutoAnnotateEligibility:
    threshold = project.auto_annotate_threshold
    types: list[TypeProgress] = []
    if task == "ner":
        rows = (
            db.query(EntityType.id, EntityType.name, func.count(Span.id))
            .outerjoin(
                Span,
                (Span.entity_type_id == EntityType.id) & (Span.source == "human"),
            )
            .filter(EntityType.project_id == project.id)
            .group_by(EntityType.id, EntityType.name)
            .all()
        )
    elif task == "re":
        rows = (
            db.query(RelationType.id, RelationType.name, func.count(Relation.id))
            .outerjoin(
                Relation,
                (Relation.relation_type_id == RelationType.id)
                & (Relation.source == "human"),
            )
            .filter(RelationType.project_id == project.id)
            .group_by(RelationType.id, RelationType.name)
            .all()
        )
    else:
        raise HTTPException(status_code=400, detail="task must be 'ner' or 're'")

    for type_id, name, count in rows:
        types.append(
            TypeProgress(
                id=type_id,
                name=name,
                count=count,
                threshold=threshold,
                eligible=count >= threshold,
            )
        )
    eligible = any(t.eligible for t in types)
    reason = ""
    if not types:
        reason = "No label types defined yet."
    elif not eligible:
        unit = "spans" if task == "ner" else "relations"
        reason = (
            f"Auto-annotate unlocks once at least one type has {threshold} "
            f"human-annotated {unit}."
        )
    return AutoAnnotateEligibility(
        task=task, eligible=eligible, threshold=threshold, types=types, reason=reason
    )


@router.get("/auto-annotate/eligibility", response_model=AutoAnnotateEligibility)
def eligibility(
    project_id: int,
    task: str = "ner",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project_for_user(project_id, user, db)
    return _eligibility(project, task, db)


@router.post("/auto-annotate", response_model=TrainingJobOut)
def start_auto_annotate(
    project_id: int,
    payload: AutoAnnotateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project_for_user(project_id, user, db)
    info = _eligibility(project, payload.task, db)
    if not info.eligible:
        raise HTTPException(status_code=400, detail=info.reason or "Not enough annotations yet")
    running = (
        db.query(TrainingJob)
        .filter(
            TrainingJob.project_id == project_id,
            TrainingJob.task == payload.task,
            TrainingJob.status.in_(["queued", "training", "annotating"]),
        )
        .first()
    )
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"A {payload.task.upper()} auto-annotation job is already running",
        )
    if payload.task == "re":
        has_relationless_docs = (
            db.query(Document.id)
            .filter(Document.project_id == project_id)
            .filter(~Document.relations.any())
            .filter(Document.spans.any())
            .first()
        )
        if has_relationless_docs is None:
            raise HTTPException(
                status_code=400,
                detail="No documents with entities but without relations to annotate.",
            )
    job = TrainingJob(
        project_id=project_id,
        task=payload.task,
        status="queued",
        message="Waiting for worker",
        created_by=user.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    submit_job(job.id)
    return job


@router.get("/jobs", response_model=list[TrainingJobOut])
def list_jobs(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    return (
        db.query(TrainingJob)
        .filter(TrainingJob.project_id == project_id)
        .order_by(TrainingJob.created_at.desc())
        .limit(50)
        .all()
    )


@router.get("/jobs/{job_id}", response_model=TrainingJobOut)
def get_job(
    project_id: int,
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    job = db.get(TrainingJob, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
