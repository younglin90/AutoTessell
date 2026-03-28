"""
POST /api/v1/upload
  - Validates STL (size, structure)
  - Uploads to S3
  - Creates Job record (PENDING)
  - Returns job_id + Stripe PaymentIntent client_secret
"""

import uuid

import boto3
import stripe
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from db import Job, JobStatus, get_db
from mesh.validator import STLValidationError, validate_stl

stripe.api_key = settings.stripe_secret_key

router = APIRouter()


class UploadResponse(BaseModel):
    job_id: str
    client_secret: str
    amount_cents: int


@router.post("/upload", response_model=UploadResponse)
async def upload_stl(
    file: UploadFile,
    user_id: str,         # In production: extract from JWT/session
    db: Session = Depends(get_db),
):
    # 1. Read and validate STL before charging the user
    content = await file.read()
    try:
        validate_stl(content)
    except STLValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Enforce per-user concurrent job limit
    active_count = (
        db.query(Job)
        .filter(
            Job.user_id == user_id,
            Job.status.in_([JobStatus.PENDING, JobStatus.PAID, JobStatus.PROCESSING]),
        )
        .count()
    )
    if active_count >= settings.max_jobs_per_user:
        raise HTTPException(
            status_code=429,
            detail=f"You already have {settings.max_jobs_per_user} active jobs. Wait for them to finish.",
        )

    # 3. Upload STL to S3
    job_id = str(uuid.uuid4())
    stl_key = f"stl/{job_id}/{file.filename or 'input.stl'}"
    _upload_to_s3(content, stl_key)

    # 4. Create Stripe PaymentIntent
    intent = stripe.PaymentIntent.create(
        amount=settings.mesh_price_cents,
        currency="usd",
        metadata={"job_id": job_id, "user_id": user_id},
    )

    # 5. Create Job record
    job = Job(
        id=job_id,
        user_id=user_id,
        status=JobStatus.PENDING,
        stl_s3_key=stl_key,
        stl_filename=file.filename,
        stripe_payment_intent_id=intent.id,
        amount_cents=settings.mesh_price_cents,
    )
    db.add(job)
    db.commit()

    return UploadResponse(
        job_id=job_id,
        client_secret=intent.client_secret,
        amount_cents=settings.mesh_price_cents,
    )


def _upload_to_s3(content: bytes, key: str) -> None:
    s3 = boto3.client(
        "s3",
        region_name=settings.s3_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=content)
