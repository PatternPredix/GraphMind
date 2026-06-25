import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import hash_password
from .database import Base, SessionLocal, engine
from .ml.jobs import recover_stale_jobs
from .models import User
from .routers import (
    annotations,
    auth_routes,
    auto_annotate,
    documents,
    import_export,
    labels,
    projects,
    rules,
)

from . import models  # noqa: F401 — register all tables on the metadata

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="GraphMind",
    description="NER & RE annotation for knowledge graphs",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(projects.router)
app.include_router(labels.router)
app.include_router(documents.router)
app.include_router(annotations.router)
app.include_router(import_export.router)
app.include_router(auto_annotate.router)
app.include_router(rules.router)


def seed_default_admin():
    """Create a default admin/admin account when the database has no users.

    This bootstraps a fresh install so an administrator can sign in immediately.
    The credentials are intentionally weak — change the password right after the
    first login via the Admin page.
    """
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(
                User(
                    username="admin",
                    email="admin@graphmind.local",
                    hashed_password=hash_password("admin"),
                    is_admin=True,
                )
            )
            db.commit()
    finally:
        db.close()


@app.on_event("startup")
def startup():
    seed_default_admin()
    recover_stale_jobs()


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve the built frontend (frontend/dist) in production, if present.
_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(_static_dir, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        candidate = os.path.join(_static_dir, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_static_dir, "index.html"))
