"""
Unit tests for db.py helper functions.

Covers:
  _utcnow    — must return timezone-naive UTC datetime (avoids datetime.utcnow deprecation)
  get_db     — yields a session and closes it (including on exception)
"""

from datetime import datetime, timezone
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# _utcnow
# ---------------------------------------------------------------------------

class TestUtcNow:
    """db._utcnow must return a timezone-naive UTC datetime."""

    def test_returns_datetime_instance(self):
        """_utcnow must return a datetime object."""
        from db import _utcnow
        assert isinstance(_utcnow(), datetime)

    def test_timezone_naive(self):
        """Result must be timezone-naive (tzinfo is None) to avoid SQLAlchemy warnings."""
        from db import _utcnow
        result = _utcnow()
        assert result.tzinfo is None

    def test_recent_timestamp(self):
        """Returned timestamp must be within 2 seconds of the current UTC time."""
        from db import _utcnow
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        result = _utcnow()
        after = datetime.now(timezone.utc).replace(tzinfo=None)
        assert before <= result <= after

    def test_successive_calls_are_non_decreasing(self):
        """Two successive calls must return non-decreasing timestamps."""
        from db import _utcnow
        t1 = _utcnow()
        t2 = _utcnow()
        assert t2 >= t1


# ---------------------------------------------------------------------------
# get_db
# ---------------------------------------------------------------------------

class TestGetDb:
    """db.get_db — yields a session then closes it via finally."""

    def _run_generator(self, gen):
        """Exhaust the generator and return the yielded session."""
        session = next(gen)
        try:
            next(gen)
        except StopIteration:
            pass
        return session

    def test_yields_session_local_instance(self):
        """get_db must yield the object returned by SessionLocal()."""
        from db import get_db

        mock_session = MagicMock()
        mock_session_local = MagicMock(return_value=mock_session)

        with patch("db.SessionLocal", mock_session_local):
            gen = get_db()
            yielded = next(gen)

        assert yielded is mock_session

    def test_close_called_after_yield(self):
        """session.close() must be called when the generator is exhausted normally."""
        from db import get_db

        mock_session = MagicMock()
        mock_session_local = MagicMock(return_value=mock_session)

        with patch("db.SessionLocal", mock_session_local):
            gen = get_db()
            next(gen)
            try:
                next(gen)
            except StopIteration:
                pass

        mock_session.close.assert_called_once()

    def test_close_called_even_on_exception(self):
        """session.close() must be called even if consumer raises (finally block)."""
        from db import get_db

        mock_session = MagicMock()
        mock_session_local = MagicMock(return_value=mock_session)

        with patch("db.SessionLocal", mock_session_local):
            gen = get_db()
            next(gen)
            try:
                gen.throw(RuntimeError("consumer failure"))
            except RuntimeError:
                pass

        mock_session.close.assert_called_once()
