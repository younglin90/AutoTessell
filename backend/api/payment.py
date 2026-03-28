"""
POST /api/v1/webhook  — Stripe webhook handler
  - payment_intent.succeeded → enqueue MeshTask
  - payment_intent.payment_failed → mark FAILED (no refund needed, never charged)
"""

import hashlib
import hmac
import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from config import settings
from db import Job, JobStatus, get_db
from worker.tasks import run_mesh

logger = logging.getLogger(__name__)
stripe.api_key = settings.stripe_secret_key

router = APIRouter()


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "payment_intent.succeeded":
        intent = event["data"]["object"]
        job_id = intent["metadata"].get("job_id")
        if job_id:
            _on_payment_succeeded(db, job_id, intent["id"])

    elif event["type"] == "payment_intent.payment_failed":
        intent = event["data"]["object"]
        job_id = intent["metadata"].get("job_id")
        if job_id:
            _on_payment_failed(db, job_id)

    return {"status": "ok"}


def _on_payment_succeeded(db: Session, job_id: str, payment_intent_id: str) -> None:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        logger.error("Stripe webhook: job %s not found", job_id)
        return
    if job.status != JobStatus.PENDING:
        logger.warning("Stripe webhook: job %s already in status %s — skipping", job_id, job.status)
        return

    job.status = JobStatus.PAID
    db.commit()

    # Enqueue Celery task
    run_mesh.apply_async(kwargs={"job_id": str(job_id)})
    logger.info("Job %s enqueued for mesh generation", job_id)


def _on_payment_failed(db: Session, job_id: str) -> None:
    job = db.query(Job).filter(Job.id == job_id).first()
    if job and job.status == JobStatus.PENDING:
        job.status = JobStatus.FAILED
        job.error_message = "Payment failed"
        db.commit()
