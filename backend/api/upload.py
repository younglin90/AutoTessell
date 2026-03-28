"""
POST /api/v1/upload
  - Validates STL (size, structure)
  - DEV_MODE: stores locally, auto-enqueues mesh task, skips Stripe
  - PROD: uploads to S3, creates Stripe PaymentIntent
"""

import logging
import uuid
from pathlib import Path

import stripe
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from config import settings
from db import Job, JobStatus, get_db
from mesh.validator import STLValidationError, validate_stl

stripe.api_key = settings.stripe_secret_key

router = APIRouter()


class UploadResponse(BaseModel):
    job_id: str
    client_secret: str
    amount_cents: int


def _run_mesh_background(job_id: str) -> None:
    """Run mesh task in background for dev mode (errors are logged, not raised)."""
    from worker.tasks import run_mesh
    try:
        run_mesh.apply(kwargs={"job_id": job_id})
    except Exception as e:
        logger.error("Dev mesh task failed for job %s: %s", job_id, e)


@router.post("/upload", response_model=UploadResponse)
async def upload_stl(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    user_id: str,
    target_cells: int = 500_000,
    mesh_purpose: str = "cfd",      # "cfd" | "fea"
    mesh_params: str = "",          # JSON-encoded MeshParams (pro mode, optional)
    db: Session = Depends(get_db),
):
    # 0a. Validate mesh_purpose
    if mesh_purpose not in ("cfd", "fea"):
        raise HTTPException(status_code=400, detail=f"Invalid mesh_purpose '{mesh_purpose}' — must be 'cfd' or 'fea'")

    # 0b. Validate target_cells range
    if not (1_000 <= target_cells <= 10_000_000):
        raise HTTPException(status_code=400, detail="target_cells must be between 1,000 and 10,000,000")

    # 0c. Validate pro params JSON if provided
    if mesh_params:
        try:
            from mesh.params import MeshParams
            import json as _json
            MeshParams.from_json(mesh_params).validated()  # raises on bad JSON
        except (ValueError, TypeError, _json.JSONDecodeError) as e:
            raise HTTPException(status_code=400, detail=f"Invalid mesh_params: {e}")

    # 1. Read and validate STL before charging the user
    content = await file.read()
    try:
        validate_stl(content, max_size=settings.max_stl_size_bytes)
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

    job_id = str(uuid.uuid4())
    filename = file.filename or "input.stl"

    if settings.dev_mode:
        # Store locally, skip S3 and Stripe
        stl_dir = Path(settings.dev_storage_path) / "stl" / job_id
        stl_dir.mkdir(parents=True, exist_ok=True)
        stl_path = stl_dir / filename
        stl_path.write_bytes(content)
        stl_key = str(stl_path)

        job = Job(
            id=job_id,
            user_id=user_id,
            status=JobStatus.PAID,
            stl_s3_key=stl_key,
            stl_filename=filename,
            stripe_payment_intent_id=None,
            amount_cents=0,
            target_cells=target_cells,
            mesh_purpose=mesh_purpose,
            mesh_params_json=mesh_params or None,
        )
        db.add(job)
        db.commit()

        # Run in background after response is sent
        background_tasks.add_task(_run_mesh_background, job_id)

        return UploadResponse(job_id=job_id, client_secret="dev_mode", amount_cents=0)

    # 3. Upload STL to S3
    stl_key = f"stl/{job_id}/{filename}"
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
        stl_filename=filename,
        stripe_payment_intent_id=intent.id,
        amount_cents=settings.mesh_price_cents,
        target_cells=target_cells,
        mesh_purpose=mesh_purpose,
        mesh_params_json=mesh_params or None,
    )
    db.add(job)
    db.commit()

    return UploadResponse(
        job_id=job_id,
        client_secret=intent.client_secret,
        amount_cents=settings.mesh_price_cents,
    )


def _upload_to_s3(content: bytes, key: str) -> None:
    import boto3
    s3 = boto3.client(
        "s3",
        region_name=settings.s3_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=content)
