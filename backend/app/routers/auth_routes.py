from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..auth import create_access_token, get_current_user, hash_password, verify_password
from ..config import settings
from ..database import get_db
from ..models import Project, ProjectMember, User
from ..schemas import PasswordReset, Token, UserCreate, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    """First user ever registered becomes admin. After that, open registration
    must be enabled (ALLOW_OPEN_REGISTRATION) or an admin must create users."""
    user_count = db.query(User).count()
    if user_count > 0 and not settings.ALLOW_OPEN_REGISTRATION:
        raise HTTPException(
            status_code=403,
            detail="Registration is closed. Ask an administrator to create your account.",
        )
    return _create_user(payload, db, is_admin=(user_count == 0))


@router.post("/users", response_model=UserOut)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if not current.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return _create_user(payload, db, is_admin=payload.is_admin)


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return db.query(User).order_by(User.username).all()


@router.get("/setup-status")
def setup_status(db: Session = Depends(get_db)):
    """Whether the seeded default admin/admin credentials are still in effect.

    The login screen uses this to show a first-run hint; it stops being true
    once the admin password is changed.
    """
    admin = db.query(User).filter(User.username == "admin").first()
    default_active = bool(admin and verify_password("admin", admin.hashed_password))
    return {"default_admin_active": default_active}


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form.username).first()
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return Token(access_token=create_access_token(user), user=UserOut.model_validate(user))


@router.patch("/users/{user_id}/password", response_model=UserOut)
def set_user_password(
    user_id: int,
    payload: PasswordReset,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Admin-only: set any user's password (including the admin's own)."""
    if not current.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Admin-only: remove a user account.

    Refuses to delete your own account, and refuses to delete a user who still
    owns projects (those must be reassigned/deleted first). Project memberships
    are removed explicitly so no orphan rows remain.
    """
    if not current.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    if user_id == current.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    owned = db.query(Project).filter(Project.owner_id == user_id).count()
    if owned:
        raise HTTPException(
            status_code=409,
            detail=f"This user owns {owned} project(s). Reassign or delete those projects first.",
        )
    db.query(ProjectMember).filter(ProjectMember.user_id == user_id).delete()
    db.delete(user)
    db.commit()
    return {"deleted": user_id}


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)):
    return current


def _create_user(payload: UserCreate, db: Session, is_admin: bool) -> User:
    existing = (
        db.query(User)
        .filter((User.username == payload.username) | (User.email == payload.email))
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Username or email already in use")
    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
