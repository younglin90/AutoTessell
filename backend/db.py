import enum
import uuid
from datetime import datetime, timezone


def _utcnow() -> datetime:
    """Return current UTC time as a timezone-naive datetime (avoids datetime.utcnow deprecation)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

from sqlalchemy import (
    Column, DateTime, Enum, ForeignKey, Integer, String, Text, create_engine,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"         # STL uploaded, awaiting payment
    PAID = "PAID"               # Payment confirmed, queued
    PROCESSING = "PROCESSING"   # Celery worker running
    DONE = "DONE"               # Mesh ready, download available
    FAILED = "FAILED"           # Mesh failed, refund issued
    REFUND_FAILED = "REFUND_FAILED"  # Mesh failed but Stripe refund also failed


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)  # Stripe customer or session id
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.PENDING)

    # S3 keys
    stl_s3_key = Column(String(512), nullable=True)
    mesh_s3_key = Column(String(512), nullable=True)

    # Stripe
    stripe_payment_intent_id = Column(String(255), nullable=True, unique=True)
    amount_cents = Column(Integer, nullable=True)

    # Meta
    stl_filename = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    celery_task_id = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)
