"""
GET /api/v1/jobs/{job_id}/download  — Signed S3 URL (prod) or local file URL (dev)
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from db import Job, JobStatus, get_db

router = APIRouter()


class DownloadResponse(BaseModel):
    url: str
    expires_in_seconds: int = 3600


@router.get("/jobs/{job_id}/download", response_model=DownloadResponse)
def get_download_url(
    job_id: str,
    user_id: str,    # In production: extract from JWT/session
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == user_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.DONE:
        raise HTTPException(status_code=409, detail=f"Mesh not ready (status: {job.status.value})")
    if not job.mesh_s3_key:
        raise HTTPException(status_code=500, detail="Mesh key missing — contact support")

    if settings.dev_mode:
        base = settings.dev_api_base_url.rstrip("/")
        url = f"{base}/dev/files/{job.mesh_s3_key}"
    else:
        url = _generate_presigned_url(job.mesh_s3_key)

    return DownloadResponse(url=url)


def _generate_presigned_url(s3_key: str, expires: int = 3600) -> str:
    import boto3
    s3 = boto3.client(
        "s3",
        region_name=settings.s3_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": s3_key},
        ExpiresIn=expires,
    )
