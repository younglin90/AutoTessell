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


# ---------------------------------------------------------------------------
# Terminal-status guard (added batch 2)
# ---------------------------------------------------------------------------

class TestTerminalStatusGuard:
    """_mark_failed_and_refund must not overwrite a terminal status or re-issue refund."""

    @pytest.mark.parametrize("terminal_status", [
        JobStatus.DONE,
        JobStatus.FAILED,
        JobStatus.REFUND_FAILED,
    ])
    def test_skips_when_already_terminal(self, terminal_status):
        job = _make_job()
        job.status = terminal_status
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = job

        with patch("worker.tasks.SessionLocal", return_value=db):
            with patch("worker.tasks.stripe") as mock_stripe:
                _mark_failed_and_refund("test-job-id", "late error")

        # Status must NOT be changed
        assert job.status == terminal_status
        # No refund should be attempted
        mock_stripe.Refund.create.assert_not_called()

    def test_processing_status_is_not_skipped(self):
        """PROCESSING is not terminal — _mark_failed_and_refund should proceed."""
        job = _make_job()
        job.status = JobStatus.PROCESSING
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = job

        with patch("worker.tasks.SessionLocal", return_value=db):
            with patch("worker.tasks.stripe") as mock_stripe:
                _mark_failed_and_refund("test-job-id", "processing error")

        assert job.status == JobStatus.FAILED
        mock_stripe.Refund.create.assert_called_once()

    def test_paid_status_is_not_skipped(self):
        """PAID is not terminal — refund should be issued."""
        job = _make_job()
        job.status = JobStatus.PAID
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = job

        with patch("worker.tasks.SessionLocal", return_value=db):
            with patch("worker.tasks.stripe") as mock_stripe:
                _mark_failed_and_refund("test-job-id", "enqueue failure")

        assert job.status == JobStatus.FAILED
        mock_stripe.Refund.create.assert_called_once()


# ---------------------------------------------------------------------------
# Error message truncation (added batch 3)
# ---------------------------------------------------------------------------

class TestErrorMessageTruncation:
    def test_long_error_truncated_to_1000_chars(self):
        """error_message must be capped at 1000 chars to avoid DB overflow."""
        job = _make_job()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = job

        long_error = "x" * 2000

        with patch("worker.tasks.SessionLocal", return_value=db):
            with patch("worker.tasks.stripe"):
                _mark_failed_and_refund("test-job-id", long_error)

        assert job.error_message == "x" * 1000

    def test_short_error_stored_as_is(self):
        """Short error messages should not be altered."""
        job = _make_job()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = job

        with patch("worker.tasks.SessionLocal", return_value=db):
            with patch("worker.tasks.stripe"):
                _mark_failed_and_refund("test-job-id", "short error")

        assert job.error_message == "short error"

    def test_exactly_1000_chars_stored_unchanged(self):
        """Exactly 1000-char error should pass through without truncation."""
        job = _make_job()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = job

        exact_error = "e" * 1000

        with patch("worker.tasks.SessionLocal", return_value=db):
            with patch("worker.tasks.stripe"):
                _mark_failed_and_refund("test-job-id", exact_error)

        assert job.error_message == exact_error
