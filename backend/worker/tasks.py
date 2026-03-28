"""
MeshTask — Celery task that runs the full mesh pipeline:
  1. Download STL from S3
  2. Run 5-tier mesh pipeline (tessell → netgen → snappyHexMesh → pytetwild+MMG)
  3. checkMesh quality validation
  4. Upload polyMesh ZIP to S3
  5. Update job status; issue Stripe refund on failure
"""

import logging
import tempfile
import zipfile
from pathlib import Path

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
    """Base task class — on_failure는 사용하지 않음.
    실패/환불 처리는 run_mesh 내부 except 블록에서 직접 수행.
    on_failure에서 중복 호출하면 동일 job에 Stripe refund가 두 번 시도될 수 있음.
    """

    abstract = True


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

            mesh_s3_key = f"meshes/{job_id}/mesh.zip"

            stl_path = tmpdir / "input.stl"
            _download_s3(job.stl_s3_key, stl_path)
            mesh_dir = tmpdir / "case"

            from mesh.params import MeshParams
            mp = None
            if job.mesh_params_json:
                try:
                    mp = MeshParams.from_json(job.mesh_params_json).validated()
                except Exception:
                    logger.warning("mesh_params_json 파싱 실패 — 기본값 사용")

            if settings.dev_mode:
                from mesh.dev_pipeline import generate_mesh_dev
                stats = generate_mesh_dev(
                    stl_path, mesh_dir,
                    target_cells=job.target_cells or 500_000,
                    mesh_purpose=job.mesh_purpose or "cfd",
                    params=mp,
                )
            else:
                # 2. Generate mesh (snappyHexMesh → fallback pytetwild+gmshToFoam)
                stats = generate_mesh(
                    stl_path, mesh_dir,
                    target_cells=job.target_cells or 500_000,
                    mesh_purpose=job.mesh_purpose or "cfd",
                    params=mp,
                )  # MeshGenerationError는 RuntimeError 서브클래스

            if not stats.get("passed", True):
                raise RuntimeError(
                    f"checkMesh FAILED — max_skewness={stats.get('max_skewness')}, "
                    f"max_non_orthogonality={stats.get('max_non_orthogonality')}"
                )

            # 3. Zip and upload
            zip_path = tmpdir / "mesh.zip"
            _zip_mesh(mesh_dir, zip_path)
            _upload_s3(zip_path, mesh_s3_key)

            # 4. Mark done
            job.status = JobStatus.DONE
            job.mesh_s3_key = mesh_s3_key
            job.result_num_cells = stats.get("num_cells")
            job.result_tier = stats.get("tier")
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

def _s3_client():
    import boto3  # lazy import — not needed in test environments without AWS deps
    return boto3.client(
        "s3",
        region_name=settings.s3_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


def _download_s3(s3_key: str, dest: Path) -> None:
    if settings.dev_mode:
        import shutil
        shutil.copy2(s3_key, dest)
    else:
        _s3_client().download_file(settings.s3_bucket, s3_key, str(dest))


def _upload_s3(src: Path, s3_key: str) -> None:
    if settings.dev_mode:
        import shutil
        dest = Path(settings.dev_storage_path) / s3_key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    else:
        _s3_client().upload_file(str(src), settings.s3_bucket, s3_key)



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
