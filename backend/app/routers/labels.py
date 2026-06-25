from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_project_for_user
from ..database import get_db
from ..models import EntityType, RelationType, User
from ..schemas import (
    EntityTypeCreate,
    EntityTypeOut,
    RelationTypeCreate,
    RelationTypeOut,
)

router = APIRouter(prefix="/api/projects/{project_id}", tags=["labels"])


@router.get("/entity-types", response_model=list[EntityTypeOut])
def list_entity_types(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    return (
        db.query(EntityType)
        .filter(EntityType.project_id == project_id)
        .order_by(EntityType.id)
        .all()
    )


@router.post("/entity-types", response_model=EntityTypeOut)
def create_entity_type(
    project_id: int,
    payload: EntityTypeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    if (
        db.query(EntityType)
        .filter(EntityType.project_id == project_id, EntityType.name == payload.name)
        .first()
    ):
        raise HTTPException(status_code=409, detail="Entity type already exists")
    et = EntityType(project_id=project_id, **payload.model_dump())
    db.add(et)
    db.commit()
    db.refresh(et)
    return et


@router.patch("/entity-types/{type_id}", response_model=EntityTypeOut)
def update_entity_type(
    project_id: int,
    type_id: int,
    payload: EntityTypeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    et = db.get(EntityType, type_id)
    if et is None or et.project_id != project_id:
        raise HTTPException(status_code=404, detail="Entity type not found")
    et.name, et.color, et.hotkey = payload.name, payload.color, payload.hotkey
    db.commit()
    db.refresh(et)
    return et


@router.delete("/entity-types/{type_id}")
def delete_entity_type(
    project_id: int,
    type_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    et = db.get(EntityType, type_id)
    if et is None or et.project_id != project_id:
        raise HTTPException(status_code=404, detail="Entity type not found")
    db.delete(et)
    db.commit()
    return {"deleted": type_id}


@router.get("/relation-types", response_model=list[RelationTypeOut])
def list_relation_types(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    return (
        db.query(RelationType)
        .filter(RelationType.project_id == project_id)
        .order_by(RelationType.id)
        .all()
    )


@router.post("/relation-types", response_model=RelationTypeOut)
def create_relation_type(
    project_id: int,
    payload: RelationTypeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    if (
        db.query(RelationType)
        .filter(RelationType.project_id == project_id, RelationType.name == payload.name)
        .first()
    ):
        raise HTTPException(status_code=409, detail="Relation type already exists")
    rt = RelationType(project_id=project_id, **payload.model_dump())
    db.add(rt)
    db.commit()
    db.refresh(rt)
    return rt


@router.patch("/relation-types/{type_id}", response_model=RelationTypeOut)
def update_relation_type(
    project_id: int,
    type_id: int,
    payload: RelationTypeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    rt = db.get(RelationType, type_id)
    if rt is None or rt.project_id != project_id:
        raise HTTPException(status_code=404, detail="Relation type not found")
    rt.name, rt.color = payload.name, payload.color
    db.commit()
    db.refresh(rt)
    return rt


@router.delete("/relation-types/{type_id}")
def delete_relation_type(
    project_id: int,
    type_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    get_project_for_user(project_id, user, db)
    rt = db.get(RelationType, type_id)
    if rt is None or rt.project_id != project_id:
        raise HTTPException(status_code=404, detail="Relation type not found")
    db.delete(rt)
    db.commit()
    return {"deleted": type_id}
