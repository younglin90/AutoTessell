"""
Unit tests for the stripe_webhook route handler (api/payment.py).

These cover the branches not reached by helper unit tests or integration tests:
  1. except Exception (non-SignatureVerificationError) from construct_event → 400
  2. payment_intent.succeeded with no job_id in metadata → _on_payment_succeeded not called
  3. payment_intent.payment_failed with no job_id in metadata → _on_payment_failed not called
  4. valid event returns {"status": "ok"}
  5. SignatureVerificationError → 400 (unit-test complement to integration coverage)
"""

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Proper exception classes for the stripe stub.
# MagicMock() alone is not a valid `except`-clause target; Python requires a
# BaseException subclass.  We define them here and inject via patch so the
# except-clauses in the route handler resolve correctly.
# ---------------------------------------------------------------------------

class _FakeSignatureVerificationError(Exception):
    pass


class _FakeStripeError(Exception):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stripe_stub():
    """Return a stripe module stub with real exception classes."""
    stub = MagicMock()
    stub.SignatureVerificationError = _FakeSignatureVerificationError
    stub.StripeError = _FakeStripeError
    stub.Webhook = MagicMock()
    return stub


def _make_request(body: bytes = b"{}") -> MagicMock:
    """Return a mock FastAPI Request with a fixed body."""
    req = MagicMock()
    req.body = AsyncMock(return_value=body)
    req.headers = {"stripe-signature": "t=1234,v1=fake"}
    return req


def _make_event(event_type: str, metadata: dict) -> dict:
    return {
        "type": event_type,
        "data": {
            "object": {
                "id": "pi_test",
                "metadata": metadata,
            }
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStripeWebhookRouteHandler:
    """stripe_webhook async route handler — branches not covered elsewhere."""

    async def test_generic_exception_from_construct_event_returns_400(self):
        """Non-SignatureVerificationError from construct_event → HTTPException 400."""
        from api.payment import stripe_webhook

        stripe_stub = _make_stripe_stub()
        stripe_stub.Webhook.construct_event.side_effect = ValueError("malformed payload")

        with patch("api.payment.stripe", stripe_stub):
            with pytest.raises(HTTPException) as exc_info:
                await stripe_webhook(_make_request(), MagicMock())

        assert exc_info.value.status_code == 400
        assert "malformed payload" in exc_info.value.detail

    async def test_signature_error_raises_400_with_fixed_message(self):
        """SignatureVerificationError → 400 with 'Invalid Stripe signature' detail."""
        from api.payment import stripe_webhook

        stripe_stub = _make_stripe_stub()
        stripe_stub.Webhook.construct_event.side_effect = _FakeSignatureVerificationError("bad sig")

        with patch("api.payment.stripe", stripe_stub):
            with pytest.raises(HTTPException) as exc_info:
                await stripe_webhook(_make_request(), MagicMock())

        assert exc_info.value.status_code == 400
        assert "Invalid Stripe signature" in exc_info.value.detail

    async def test_succeeded_with_no_job_id_skips_on_succeeded(self):
        """payment_intent.succeeded with no job_id in metadata → _on_payment_succeeded not called."""
        from api.payment import stripe_webhook

        stripe_stub = _make_stripe_stub()
        stripe_stub.Webhook.construct_event.return_value = _make_event(
            "payment_intent.succeeded", {}
        )

        with patch("api.payment.stripe", stripe_stub), \
             patch("api.payment._on_payment_succeeded") as mock_fn:
            await stripe_webhook(_make_request(), MagicMock())

        mock_fn.assert_not_called()

    async def test_failed_with_no_job_id_skips_on_failed(self):
        """payment_intent.payment_failed with no job_id in metadata → _on_payment_failed not called."""
        from api.payment import stripe_webhook

        stripe_stub = _make_stripe_stub()
        stripe_stub.Webhook.construct_event.return_value = _make_event(
            "payment_intent.payment_failed", {}
        )

        with patch("api.payment.stripe", stripe_stub), \
             patch("api.payment._on_payment_failed") as mock_fn:
            await stripe_webhook(_make_request(), MagicMock())

        mock_fn.assert_not_called()

    async def test_succeeded_with_job_id_calls_on_succeeded(self):
        """payment_intent.succeeded with job_id → _on_payment_succeeded called with db and ids."""
        from api.payment import stripe_webhook

        stripe_stub = _make_stripe_stub()
        stripe_stub.Webhook.construct_event.return_value = _make_event(
            "payment_intent.succeeded", {"job_id": "job-xyz"}
        )

        db = MagicMock()

        with patch("api.payment.stripe", stripe_stub), \
             patch("api.payment._on_payment_succeeded") as mock_fn:
            await stripe_webhook(_make_request(), db)

        mock_fn.assert_called_once_with(db, "job-xyz", "pi_test")

    async def test_failed_with_job_id_calls_on_failed(self):
        """payment_intent.payment_failed with job_id → _on_payment_failed called with db and id."""
        from api.payment import stripe_webhook

        stripe_stub = _make_stripe_stub()
        stripe_stub.Webhook.construct_event.return_value = _make_event(
            "payment_intent.payment_failed", {"job_id": "job-abc"}
        )

        db = MagicMock()

        with patch("api.payment.stripe", stripe_stub), \
             patch("api.payment._on_payment_failed") as mock_fn:
            await stripe_webhook(_make_request(), db)

        mock_fn.assert_called_once_with(db, "job-abc")

    async def test_valid_event_returns_status_ok(self):
        """Any valid event must return {'status': 'ok'}."""
        from api.payment import stripe_webhook

        stripe_stub = _make_stripe_stub()
        stripe_stub.Webhook.construct_event.return_value = _make_event(
            "some.other.event", {}
        )

        with patch("api.payment.stripe", stripe_stub):
            result = await stripe_webhook(_make_request(), MagicMock())

        assert result == {"status": "ok"}
