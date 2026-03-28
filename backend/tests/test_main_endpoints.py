"""
Unit tests for main.py inline route handlers.

The integration tests cover these via a real FastAPI TestClient, but unit tests
let us target the logic in isolation without spinning up a full app.

Covers:
  health()       — db_ok=True → 200; db_ok=False → 503
  public_config() — returns correct settings values
"""

import pytest
from fastapi.responses import JSONResponse
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# health()
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """health() — SQLAlchemy session probe, status and HTTP code."""

    def test_returns_200_when_db_healthy(self):
        """When the DB SELECT 1 succeeds, status_code must be 200."""
        from main import health

        mock_session = MagicMock()
        mock_session_local = MagicMock()
        mock_session_local.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=False)

        mock_settings = MagicMock()
        mock_settings.dev_mode = False

        with patch("db.SessionLocal", mock_session_local), \
             patch("main.settings", mock_settings):
            response = health()

        assert response.status_code == 200

    def test_body_db_true_when_healthy(self):
        """Body must include {"db": true, "status": "ok"} when query succeeds."""
        import json
        from main import health

        mock_session = MagicMock()
        mock_session_local = MagicMock()
        mock_session_local.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=False)

        mock_settings = MagicMock()
        mock_settings.dev_mode = True

        with patch("db.SessionLocal", mock_session_local), \
             patch("main.settings", mock_settings):
            response = health()

        body = json.loads(response.body)
        assert body["db"] is True
        assert body["status"] == "ok"

    def test_returns_503_when_db_down(self):
        """When the DB query raises, status_code must be 503."""
        from main import health

        mock_session_local = MagicMock()
        mock_session_local.return_value.__enter__ = MagicMock(
            side_effect=Exception("connection refused")
        )
        mock_session_local.return_value.__exit__ = MagicMock(return_value=False)

        mock_settings = MagicMock()
        mock_settings.dev_mode = False

        with patch("db.SessionLocal", mock_session_local), \
             patch("main.settings", mock_settings):
            response = health()

        assert response.status_code == 503

    def test_body_db_false_when_down(self):
        """Body must include {"db": false, "status": "degraded"} when query fails."""
        import json
        from main import health

        mock_session_local = MagicMock()
        mock_session_local.return_value.__enter__ = MagicMock(
            side_effect=RuntimeError("timeout")
        )
        mock_session_local.return_value.__exit__ = MagicMock(return_value=False)

        mock_settings = MagicMock()
        mock_settings.dev_mode = False

        with patch("db.SessionLocal", mock_session_local), \
             patch("main.settings", mock_settings):
            response = health()

        body = json.loads(response.body)
        assert body["db"] is False
        assert body["status"] == "degraded"

    def test_body_includes_dev_mode_flag(self):
        """Body must include dev_mode from settings."""
        import json
        from main import health

        mock_session = MagicMock()
        mock_session_local = MagicMock()
        mock_session_local.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=False)

        mock_settings = MagicMock()
        mock_settings.dev_mode = True

        with patch("db.SessionLocal", mock_session_local), \
             patch("main.settings", mock_settings):
            response = health()

        body = json.loads(response.body)
        assert body["dev_mode"] is True


# ---------------------------------------------------------------------------
# public_config()
# ---------------------------------------------------------------------------

class TestPublicConfig:
    """public_config() — returns correct settings values without auth."""

    def _call(self, mesh_price_cents=500, max_stl_size_bytes=50 * 1024 * 1024,
               max_jobs_per_user=2, dev_mode=False):
        from main import public_config

        mock_settings = MagicMock()
        mock_settings.mesh_price_cents = mesh_price_cents
        mock_settings.max_stl_size_bytes = max_stl_size_bytes
        mock_settings.max_jobs_per_user = max_jobs_per_user
        mock_settings.dev_mode = dev_mode

        with patch("main.settings", mock_settings):
            return public_config()

    def test_returns_mesh_price_cents(self):
        result = self._call(mesh_price_cents=999)
        assert result["mesh_price_cents"] == 999

    def test_returns_max_stl_size_mb(self):
        """max_stl_size_mb must be the byte value ÷ (1024*1024)."""
        result = self._call(max_stl_size_bytes=100 * 1024 * 1024)
        assert result["max_stl_size_mb"] == 100

    def test_returns_max_jobs_per_user(self):
        result = self._call(max_jobs_per_user=5)
        assert result["max_jobs_per_user"] == 5

    def test_returns_dev_mode_true(self):
        result = self._call(dev_mode=True)
        assert result["dev_mode"] is True

    def test_returns_dev_mode_false(self):
        result = self._call(dev_mode=False)
        assert result["dev_mode"] is False

    def test_max_stl_size_mb_is_integer_division(self):
        """Partial megabytes must be truncated (integer division)."""
        result = self._call(max_stl_size_bytes=50 * 1024 * 1024 + 512)
        assert result["max_stl_size_mb"] == 50
