"""In-process background job queue for auto-annotation.

Jobs run one at a time in a single worker thread so model training cannot
starve the API of CPU. Job state lives in the training_jobs table, so the
frontend can poll progress and history survives restarts (jobs that were
running when the server stopped are marked failed on startup).
"""
import datetime
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor

from ..database import SessionLocal
from ..models import TrainingJob

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ml-job")


def submit_job(job_id: int) -> None:
    _executor.submit(_run_job, job_id)


def recover_stale_jobs() -> None:
    """Mark jobs left in a running state by a previous process as failed."""
    db = SessionLocal()
    try:
        stale = (
            db.query(TrainingJob)
            .filter(TrainingJob.status.in_(["queued", "training", "annotating"]))
            .all()
        )
        for job in stale:
            job.status = "failed"
            job.message = "Interrupted by server restart"
            job.finished_at = datetime.datetime.utcnow()
        db.commit()
    finally:
        db.close()


def _run_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(TrainingJob, job_id)
        if job is None:
            return
        task = job.task
        project_id = job.project_id
        db.close()

        def update(status=None, progress=None, message=None, metrics=None, annotated=None):
            s = SessionLocal()
            try:
                j = s.get(TrainingJob, job_id)
                if j is None:
                    return
                if status is not None:
                    j.status = status
                if progress is not None:
                    j.progress = progress
                if message is not None:
                    j.message = message
                if metrics is not None:
                    j.metrics = metrics
                if annotated is not None:
                    j.annotated_count = annotated
                if status in ("completed", "failed"):
                    j.finished_at = datetime.datetime.utcnow()
                s.commit()
            finally:
                s.close()

        try:
            if task == "ner":
                from .ner_trainer import run_ner_job

                run_ner_job(project_id, update)
            elif task == "re":
                from .re_trainer import run_re_job

                run_re_job(project_id, update)
            elif task == "ner_rules":
                from ..rules_engine import run_keyword_rules_job

                run_keyword_rules_job(project_id, update)
            elif task == "re_rules":
                from .relation_rules import run_relation_rules_job

                run_relation_rules_job(project_id, update)
            else:
                update(status="failed", message=f"Unknown task: {task}")
                return
        except MissingDependencyError as exc:
            update(status="failed", message=str(exc))
        except Exception as exc:  # noqa: BLE001 — job boundary, report everything
            logger.exception("Auto-annotation job %s failed", job_id)
            update(
                status="failed",
                message=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-1500:]}",
            )
    finally:
        try:
            db.close()
        except Exception:
            pass


class MissingDependencyError(RuntimeError):
    """Raised when an optional ML dependency is not installed."""
