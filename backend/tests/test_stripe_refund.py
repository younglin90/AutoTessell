"""Unit tests for Stripe refund logic in MeshTask failure path."""

from unittest.mock import MagicMock, patch

import pytest

from worker.tasks import _mark_failed_and_refund
from db import JobStatus


def _make_job(job_id="test-job-id", pi_id="pi_test123"):
    job = MagicMock()
    job.id = job_id
    job.status = JobStatus.PROCESSING
    job.stripe_payment_intent_id = pi_id
    return job


class TestMarkFailedAndRefund:
    def test_issues_refund_on_failure(self):
        job = _make_job()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = job

        with patch("worker.tasks.SessionLocal", return_value=db):
            with patch("worker.tasks.stripe") as mock_stripe:
                _mark_failed_and_refund("test-job-id", "mesh exploded")

        assert job.status == JobStatus.FAILED
        assert "mesh exploded" in job.error_message
        mock_stripe.Refund.create.assert_called_once_with(payment_intent="pi_test123")

    def test_stripe_refund_failure_marks_refund_failed(self):
        import stripe as real_stripe
        job = _make_job()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = job

        with patch("worker.tasks.SessionLocal", return_value=db):
            with patch("worker.tasks.stripe") as mock_stripe:
                mock_stripe.Refund.create.side_effect = real_stripe.StripeError("network error")
                mock_stripe.StripeError = real_stripe.StripeError
                _mark_failed_and_refund("test-job-id", "mesh failed")

        assert job.status == JobStatus.REFUND_FAILED

    def test_no_refund_when_no_payment_intent(self):
        job = _make_job(pi_id=None)
        job.stripe_payment_intent_id = None
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = job

        with patch("worker.tasks.SessionLocal", return_value=db):
            with patch("worker.tasks.stripe") as mock_stripe:
                _mark_failed_and_refund("test-job-id", "no pi")

        mock_stripe.Refund.create.assert_not_called()

    def test_job_not_found_does_not_raise(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with patch("worker.tasks.SessionLocal", return_value=db):
            with patch("worker.tasks.stripe"):
                _mark_failed_and_refund("nonexistent-job", "error")  # should not raise
