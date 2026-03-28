"""
GET    /api/v1/jobs          — List recent jobs for a user (newest first, capped at 20)
GET    /api/v1/jobs/{job_id} — Poll single job status
DELETE /api/v1/jobs/{job_id} — Remove a terminal job and its stored assets
"""

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from db import Job, JobStatus, get_db

log = logging.getLogger(__name__)

router = APIRouter()


class JobListItem(BaseModel):
    job_id: str
    status: str
    stl_filename: str | None = None
    target_cells: int = 500_000
    mesh_purpose: str = "cfd"
    has_pro_params: bool = False
    created_at: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    error_message: str | None = None
    download_ready: bool = False
    amount_cents: int = 0
    # Input parameters (echo back for display)
    stl_filename: str | None = None
    target_cells: int = 500_000
    mesh_purpose: str = "cfd"
    mesh_params_json: str | None = None
    # Result stats (filled on DONE)
    result_num_cells: int | None = None
    result_tier: str | None = None


@router.get("/jobs", response_model=list[JobListItem])
def list_jobs(
    user_id: str,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Job)
        .filter(Job.user_id == user_id)
        .order_by(Job.created_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return [
        JobListItem(
            job_id=str(j.id),
            status=j.status.value,
            stl_filename=j.stl_filename,
            target_cells=j.target_cells or 500_000,
            mesh_purpose=j.mesh_purpose or "cfd",
            has_pro_params=bool(j.mesh_params_json),
            created_at=j.created_at.isoformat() if j.created_at else "",
        )
        for j in rows
    ]


def _delete_job_files(job: Job) -> None:
    """Best-effort removal of STL and mesh assets for a deleted job."""
    if settings.dev_mode:
        base = Path(settings.dev_storage_path)
        for subdir in ("stl", "meshes"):
            target = base / subdir / str(job.id)
            if target.exists():
                try:
                    shutil.rmtree(target)
                except Exception as exc:
                    log.warning("Could not remove %s: %s", target, exc)
    else:
        # S3 cleanup — graceful no-op if boto3 not configured
        try:
            import boto3

            s3 = boto3.client(
                "s3",
                region_name=settings.s3_region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
            )
            keys_to_delete = []
            if job.stl_s3_key:
                keys_to_delete.append({"Key": job.stl_s3_key})
            if job.mesh_s3_key:
                keys_to_delete.append({"Key": job.mesh_s3_key})
            if keys_to_delete:
                s3.delete_objects(
                    Bucket=settings.s3_bucket,
                    Delete={"Objects": keys_to_delete, "Quiet": True},
                )
        except Exception as exc:
            log.warning("S3 cleanup failed for job %s: %s", job.id, exc)


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(
    job_id: str,
    user_id: str,
    db: Session = Depends(get_db),
):
    """
    Remove a job record (and its S3/local assets) for the requesting user.

    Only terminal jobs (DONE, FAILED, REFUND_FAILED) can be deleted.
    Returns 204 on success, 404 if not found, 409 if still in progress.
    """
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == user_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    terminal = {JobStatus.DONE, JobStatus.FAILED, JobStatus.REFUND_FAILED}
    if job.status not in terminal:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete an active job (status: {job.status.value}). Wait for it to finish.",
        )

    db.delete(job)
    db.commit()

    _delete_job_files(job)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: str,
    user_id: str,    # In production: extract from JWT/session
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == user_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=str(job.id),
        status=job.status.value,
        error_message=job.error_message,
        download_ready=job.status == JobStatus.DONE,
        amount_cents=job.amount_cents or 0,
        stl_filename=job.stl_filename,
        target_cells=job.target_cells or 500_000,
        mesh_purpose=job.mesh_purpose or "cfd",
        mesh_params_json=job.mesh_params_json,
        result_num_cells=job.result_num_cells,
        result_tier=job.result_tier,
    )
