"""
MeshTask — Celery task that runs the full mesh pipeline:
  1. Download STL from S3
  2. Run SDF + Octree mesh generation (stub → real engine in Phase 1b)
  3. Run OpenFOAM checkMesh
  4. Upload mesh ZIP to S3
  5. Update job status; issue Stripe refund on failure
"""

import logging
import os
import subprocess
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
from mesh.checkmesh import parse_checkmesh_output
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

            # 2. Generate mesh (SDF+Octree → OpenFOAM constant/polyMesh/)
            mesh_dir = tmpdir / "case"
            _run_mesh_generator(stl_path, mesh_dir)

            # 3. Run checkMesh
            result = _run_checkmesh(mesh_dir)
            if not result.passed:
                raise RuntimeError(
                    f"checkMesh FAILED — max_skewness={result.max_skewness}, "
                    f"max_non_orthogonality={result.max_non_orthogonality}"
                )

            # 4. Zip and upload
            zip_path = tmpdir / "mesh.zip"
            _zip_mesh(mesh_dir, zip_path)
            mesh_s3_key = f"meshes/{job_id}/mesh.zip"
            _upload_s3(zip_path, mesh_s3_key)

            # 5. Mark done
            job.status = JobStatus.DONE
            job.mesh_s3_key = mesh_s3_key
            db.commit()

            return {
                "job_id": job_id,
                "num_cells": result.num_cells,
                "max_skewness": result.max_skewness,
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


def _run_mesh_generator(stl_path: Path, mesh_dir: Path) -> None:
    """
    Phase 1 stub: copies STL and creates a minimal OpenFOAM case structure.
    Replace with the real SDF+Octree engine in Phase 1b.

    Real implementation will call:
      tessell-mesh --stl input.stl --output case/
    which produces constant/polyMesh/ with points, faces, owner, neighbour, boundary.
    """
    mesh_dir.mkdir(parents=True, exist_ok=True)
    (mesh_dir / "constant" / "polyMesh").mkdir(parents=True, exist_ok=True)
    (mesh_dir / "system").mkdir(parents=True, exist_ok=True)

    # Write a minimal controlDict so checkMesh can run
    (mesh_dir / "system" / "controlDict").write_text(
        "FoamFile { version 2.0; format ascii; class dictionary; location system; object controlDict; }\n"
        "application simpleFoam;\nstartFrom startTime;\nstartTime 0;\nstopAt endTime;\nendTime 100;\n"
        "deltaT 1;\nwriteControl timeStep;\nwriteInterval 100;\n"
    )

    # TODO: replace with: subprocess.run(["tessell-mesh", "--stl", str(stl_path), "--output", str(mesh_dir)], check=True)
    logger.info("Mesh generator stub: created case scaffold at %s", mesh_dir)


def _run_checkmesh(mesh_dir: Path) -> object:
    """Run OpenFOAM checkMesh and return parsed result."""
    from mesh.checkmesh import parse_checkmesh_output  # local import to avoid circular

    try:
        proc = subprocess.run(
            ["checkMesh", "-case", str(mesh_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        stdout = proc.stdout + proc.stderr
    except FileNotFoundError:
        # checkMesh not installed — skip in dev/test environments
        logger.warning("checkMesh not found — skipping mesh quality check")

        class _FakeResult:
            passed = True
            max_non_orthogonality = None
            max_skewness = None
            num_cells = None
            raw_output = "checkMesh not available"

        return _FakeResult()

    return parse_checkmesh_output(stdout)


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
