"""
MeshTask — Celery task that runs the full mesh pipeline:
  1. Download STL from S3
  2. Run SDF + Octree mesh generation (stub → real engine in Phase 1b)
  3. Run OpenFOAM checkMesh
  4. Upload mesh ZIP to S3
  5. Update job status; issue Stripe refund on failure
"""

import logging
import tempfile
import zipfile
from pathlib import Path

import boto3
import stripe
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.orm import Session

from config import settings
from db import Job, JobStatus, SessionLocal
from mesh.generator import MeshGenerationError, generate_mesh
from worker.celery_app import celery_app

logger = logging.getLogger(__name__)

stripe.api_key = settings.stripe_secret_key


class MeshTask(Task):
    """Base task class with DB session lifecycle management."""

    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        job_id = kwargs.get("job_id") or (args[0] if args else None)
        if job_id:
            _mark_failed_and_refund(job_id, str(exc))


@celery_app.task(
    bind=True,
    base=MeshTask,
    name="worker.tasks.run_mesh",
    max_retries=0,
)
def run_mesh(self, job_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.status = JobStatus.PROCESSING
        job.celery_task_id = self.request.id
        db.commit()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # 1. Download STL
            stl_path = tmpdir / "input.stl"
            _download_s3(job.stl_s3_key, stl_path)

            # 2. Generate mesh (snappyHexMesh → fallback pytetwild+gmshToFoam)
            mesh_dir = tmpdir / "case"
            try:
                stats = generate_mesh(stl_path, mesh_dir)
            except MeshGenerationError as e:
                raise RuntimeError(str(e)) from e

            if not stats.get("passed", True):
                raise RuntimeError(
                    f"checkMesh FAILED — max_skewness={stats.get('max_skewness')}, "
                    f"max_non_orthogonality={stats.get('max_non_orthogonality')}"
                )

            # 3. Zip and upload
            zip_path = tmpdir / "mesh.zip"
            _zip_mesh(mesh_dir, zip_path)
            mesh_s3_key = f"meshes/{job_id}/mesh.zip"
            _upload_s3(zip_path, mesh_s3_key)

            # 4. Mark done
            job.status = JobStatus.DONE
            job.mesh_s3_key = mesh_s3_key
            db.commit()

            return {
                "job_id": job_id,
                "tier": stats.get("tier"),
                "num_cells": stats.get("num_cells"),
                "max_skewness": stats.get("max_skewness"),
            }

    except SoftTimeLimitExceeded:
        logger.warning("Job %s hit soft time limit — failing with refund", job_id)
        _mark_failed_and_refund(job_id, "Mesh generation timed out (9 min)")
        raise

    except Exception as exc:
        logger.exception("Job %s failed: %s", job_id, exc)
        _mark_failed_and_refund(job_id, str(exc))
        raise

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _download_s3(s3_key: str, dest: Path) -> None:
    s3 = boto3.client(
        "s3",
        region_name=settings.s3_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    s3.download_file(settings.s3_bucket, s3_key, str(dest))


def _upload_s3(src: Path, s3_key: str) -> None:
    s3 = boto3.client(
        "s3",
        region_name=settings.s3_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    s3.upload_file(str(src), settings.s3_bucket, s3_key)



def _zip_mesh(mesh_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in mesh_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(mesh_dir))


def _mark_failed_and_refund(job_id: str, error: str) -> None:
    db: Session = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return
        job.status = JobStatus.FAILED
        job.error_message = error[:1000]
        db.commit()

        if job.stripe_payment_intent_id:
            try:
                stripe.Refund.create(payment_intent=job.stripe_payment_intent_id)
                logger.info("Stripe refund issued for job %s", job_id)
            except stripe.StripeError as e:
                logger.error("Stripe refund FAILED for job %s: %s", job_id, e)
                job.status = JobStatus.REFUND_FAILED
                db.commit()
    finally:
        db.close()
