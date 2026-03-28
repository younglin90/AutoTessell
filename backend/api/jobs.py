"""
GET /api/v1/jobs/{job_id}  — Poll job status
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import Job, JobStatus, get_db

router = APIRouter()


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    error_message: str | None = None
    download_ready: bool = False
    amount_cents: int = 0
    # Input parameters (echo back for display)
    target_cells: int = 500_000
    mesh_purpose: str = "cfd"
    mesh_params_json: str | None = None
    # Result stats (filled on DONE)
    result_num_cells: int | None = None
    result_tier: str | None = None


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
        target_cells=job.target_cells or 500_000,
        mesh_purpose=job.mesh_purpose or "cfd",
        mesh_params_json=job.mesh_params_json,
        result_num_cells=job.result_num_cells,
        result_tier=job.result_tier,
    )
