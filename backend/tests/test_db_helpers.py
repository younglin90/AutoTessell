"""
Unit tests for db.py helper functions.

Covers:
  _utcnow — must return timezone-naive UTC datetime (avoids datetime.utcnow deprecation)
"""

from datetime import datetime, timezone


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
