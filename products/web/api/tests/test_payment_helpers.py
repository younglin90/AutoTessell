"""
Unit tests for api/payment.py pure-function helpers.

Focus:
  _on_payment_succeeded — job-not-found guard, non-PENDING guard, PI mismatch guard,
                          PI stored-if-missing, PAID marking + enqueue, Celery
                          enqueue failure triggers _mark_failed_and_refund
  _on_payment_failed    — PENDING → FAILED, non-PENDING unchanged, job-not-found guard
"""

from unittest.mock import MagicMock, patch

import pytest

from api.payment import _on_payment_failed, _on_payment_succeeded
from db import JobStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(job=None):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = job
    return db


def _make_job(status=JobStatus.PENDING, pi_id="pi_existing"):
    job = MagicMock()
    job.id = "job-pay-test"
    job.status = status
    job.stripe_payment_intent_id = pi_id
    return job


# ---------------------------------------------------------------------------
# TestOnPaymentSucceeded
# ---------------------------------------------------------------------------

class TestOnPaymentSucceeded:
    def test_job_not_found_returns_silently(self):
        """If job not found, must return without committing or raising."""
        db = _make_db(None)
        _on_payment_succeeded(db, "nonexistent-job", "pi_abc")
        db.commit.assert_not_called()

    @pytest.mark.parametrize("status", [
        JobStatus.PAID, JobStatus.PROCESSING, JobStatus.DONE,
    ])
    def test_non_pending_status_returns_silently(self, status):
        """Already-advanced status must not be overwritten (prevents double-enqueue)."""
        job = _make_job(status=status)
        db = _make_db(job)
        _on_payment_succeeded(db, job.id, "pi_new")
        assert job.status == status   # unchanged
        db.commit.assert_not_called()

    def test_pi_mismatch_returns_silently(self):
        """PI ID from event that differs from stored ID must be rejected."""
        job = _make_job(pi_id="pi_stored_123")
        db = _make_db(job)
        _on_payment_succeeded(db, job.id, "pi_different_456")
        assert job.status == JobStatus.PENDING   # unchanged
        db.commit.assert_not_called()

    def test_marks_paid_and_commits(self):
        """Happy path: PENDING job + matching PI → status set to PAID, db committed."""
        job = _make_job(pi_id="pi_match")
        db = _make_db(job)
        with patch("api.payment.run_mesh"):
            _on_payment_succeeded(db, job.id, "pi_match")
        assert job.status == JobStatus.PAID
        db.commit.assert_called()

    def test_pi_id_stored_if_missing_on_job(self):
        """If job.stripe_payment_intent_id is None, it must be filled from the event."""
        job = _make_job(pi_id=None)
        db = _make_db(job)
        with patch("api.payment.run_mesh"):
            _on_payment_succeeded(db, job.id, "pi_from_event")
        assert job.stripe_payment_intent_id == "pi_from_event"

    def test_run_mesh_apply_async_called_with_job_id(self):
        """After marking PAID, run_mesh.apply_async must be called with job_id."""
        job = _make_job(pi_id="pi_abc")
        db = _make_db(job)
        with patch("api.payment.run_mesh") as mock_task:
            _on_payment_succeeded(db, job.id, "pi_abc")
        mock_task.apply_async.assert_called_once_with(kwargs={"job_id": str(job.id)})

    def test_celery_enqueue_failure_calls_mark_failed_and_refund(self):
        """If Celery broker is unavailable, must call _mark_failed_and_refund with job_id."""
        job = _make_job(pi_id="pi_abc")
        db = _make_db(job)
        with patch("api.payment.run_mesh") as mock_task, \
             patch("worker.tasks._mark_failed_and_refund") as mock_refund:
            mock_task.apply_async.side_effect = Exception("broker unavailable")
            _on_payment_succeeded(db, job.id, "pi_abc")
        mock_refund.assert_called_once()
        assert mock_refund.call_args[0][0] == str(job.id)

    def test_pi_matching_none_stored_none_event_does_not_mismatch(self):
        """Both stored and event PI are the same value — no mismatch, proceeds normally."""
        job = _make_job(pi_id="pi_same")
        db = _make_db(job)
        with patch("api.payment.run_mesh"):
            _on_payment_succeeded(db, job.id, "pi_same")
        assert job.status == JobStatus.PAID


# ---------------------------------------------------------------------------
# TestOnPaymentFailed
# ---------------------------------------------------------------------------

class TestOnPaymentFailed:
    def test_pending_job_marked_failed(self):
        """PENDING job must be marked FAILED with error_message='Payment failed'."""
        job = _make_job(status=JobStatus.PENDING)
        db = _make_db(job)
        _on_payment_failed(db, job.id)
        assert job.status == JobStatus.FAILED
        assert job.error_message == "Payment failed"
        db.commit.assert_called_once()

    def test_non_pending_job_not_changed(self):
        """Non-PENDING status (e.g. PAID) must not be overwritten."""
        job = _make_job(status=JobStatus.PAID)
        db = _make_db(job)
        _on_payment_failed(db, job.id)
        assert job.status == JobStatus.PAID   # unchanged
        db.commit.assert_not_called()

    def test_job_not_found_does_not_raise(self):
        """If job not found, must return silently without raising."""
        db = _make_db(None)
        _on_payment_failed(db, "nonexistent-job")   # must not raise
