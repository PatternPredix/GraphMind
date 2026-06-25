from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_project_for_user
from ..config import settings
from ..database import get_db
from ..models import (
    Document,
    Project,
    ProjectMember,
    Relation,
    Span,
    User,
)
from ..schemas import (
    MemberAdd,
    MemberOut,
    ProjectCreate,
    ProjectOut,
    ProjectStats,
    ProjectUpdate,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectOut)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = Project(
        name=payload.name,
        description=payload.description,
        guideline=payload.guideline,
        owner_id=user.id,
        auto_annotate_threshold=payload.auto_annotate_threshold
        or settings.DEFAULT_AUTO_ANNOTATE_THRESHOLD,
    )
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="admin"))
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Project)
    if not user.is_admin:
        query = query.join(ProjectMember).filter(ProjectMember.user_id == user.id)
    return query.order_by(Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return get_project_for_user(project_id, user, db)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project_for_user(project_id, user, db, require_admin=True)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_project_for_user(project_id, user, db, require_admin=True)
    db.delete(project)
    db.commit()
    return {"deleted": project_id}


@router.get("/{project_id}/stats", response_model=ProjectStats)
def project_stats(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    doc_filter = Document.project_id == project_id
    total_docs = db.query(func.count(Document.id)).filter(doc_filter).scalar()
    confirmed = (
        db.query(func.count(Document.id))
        .filter(doc_filter, Document.is_confirmed.is_(True))
        .scalar()
    )
    total_spans = (
        db.query(func.count(Span.id)).join(Document).filter(doc_filter).scalar()
    )
    total_relations = (
        db.query(func.count(Relation.id)).join(Document).filter(doc_filter).scalar()
    )
    unreviewed_spans = (
        db.query(func.count(Span.id))
        .join(Document)
        .filter(doc_filter, Span.reviewed.is_(False))
        .scalar()
    )
    unreviewed_relations = (
        db.query(func.count(Relation.id))
        .join(Document)
        .filter(doc_filter, Relation.reviewed.is_(False))
        .scalar()
    )
    return ProjectStats(
        total_documents=total_docs,
        confirmed_documents=confirmed,
        total_spans=total_spans,
        total_relations=total_relations,
        unreviewed_model_spans=unreviewed_spans,
        unreviewed_model_relations=unreviewed_relations,
    )


@router.get("/{project_id}/members", response_model=list[MemberOut])
def list_members(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    members = (
        db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    )
    return [
        MemberOut(id=m.id, user_id=m.user_id, username=m.user.username, role=m.role)
        for m in members
    ]


@router.post("/{project_id}/members", response_model=MemberOut)
def add_member(
    project_id: int,
    payload: MemberAdd,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db, require_admin=True)
    target = db.query(User).filter(User.username == payload.username).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    exists = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == target.id)
        .first()
    )
    if exists:
        raise HTTPException(status_code=409, detail="Already a member")
    member = ProjectMember(project_id=project_id, user_id=target.id, role=payload.role)
    db.add(member)
    db.commit()
    db.refresh(member)
    return MemberOut(
        id=member.id, user_id=target.id, username=target.username, role=member.role
    )


@router.delete("/{project_id}/members/{member_id}")
def remove_member(
    project_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db, require_admin=True)
    member = db.get(ProjectMember, member_id)
    if member is None or member.project_id != project_id:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(member)
    db.commit()
    return {"deleted": member_id}
