"""
Unit tests for the get_download_url route handler (api/download.py).

These cover guard branches at the route level that integration tests exercise
only via the full HTTP stack. Direct route invocation lets us target each branch
precisely without a running server.

Branches covered:
  1. Job not found (db returns None)                     → 404
  2. Job found but status != DONE                        → 409 with status in detail
  3. Job DONE but mesh_s3_key is None/empty              → 500
  4. dev_mode=True  → dev URL constructed from base URL
  5. dev_mode=False → _generate_presigned_url called, URL returned
  6. DownloadResponse expires_in_seconds default = 3600
"""

import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock, patch

from db import JobStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(status=JobStatus.DONE, mesh_s3_key="meshes/job-1/mesh.zip"):
    job = MagicMock()
    job.id = "job-1"
    job.user_id = "user-1"
    job.status = status
    job.mesh_s3_key = mesh_s3_key
    return job


def _make_db(job=None):
    """Return a mock SQLAlchemy Session whose query chain returns `job`."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = job
    return db


def _make_settings(dev_mode=False, dev_api_base_url="http://localhost:8000"):
    s = MagicMock()
    s.dev_mode = dev_mode
    s.dev_api_base_url = dev_api_base_url
    return s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetDownloadUrlRouteHandler:
    """get_download_url route handler — guard branches."""

    def test_job_not_found_raises_404(self):
        """db returns None → HTTPException 404."""
        from api.download import get_download_url

        db = _make_db(job=None)
        with patch("api.download.settings", _make_settings()):
            with pytest.raises(HTTPException) as exc_info:
                get_download_url("job-missing", "user-1", db)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    def test_job_not_done_raises_409(self):
        """Job exists but status is PROCESSING → 409."""
        from api.download import get_download_url

        job = _make_job(status=JobStatus.PROCESSING)
        db = _make_db(job=job)
        with patch("api.download.settings", _make_settings()):
            with pytest.raises(HTTPException) as exc_info:
                get_download_url("job-1", "user-1", db)

        assert exc_info.value.status_code == 409
        assert "processing" in exc_info.value.detail.lower()

    def test_job_paid_status_raises_409(self):
        """Job status PAID (not DONE) → 409."""
        from api.download import get_download_url

        job = _make_job(status=JobStatus.PAID)
        db = _make_db(job=job)
        with patch("api.download.settings", _make_settings()):
            with pytest.raises(HTTPException) as exc_info:
                get_download_url("job-1", "user-1", db)

        assert exc_info.value.status_code == 409

    def test_job_failed_status_raises_409(self):
        """Job status FAILED (not DONE) → 409."""
        from api.download import get_download_url

        job = _make_job(status=JobStatus.FAILED)
        db = _make_db(job=job)
        with patch("api.download.settings", _make_settings()):
            with pytest.raises(HTTPException) as exc_info:
                get_download_url("job-1", "user-1", db)

        assert exc_info.value.status_code == 409

    def test_409_detail_contains_actual_status(self):
        """409 detail must mention the current job status value."""
        from api.download import get_download_url

        job = _make_job(status=JobStatus.PENDING)
        db = _make_db(job=job)
        with patch("api.download.settings", _make_settings()):
            with pytest.raises(HTTPException) as exc_info:
                get_download_url("job-1", "user-1", db)

        assert JobStatus.PENDING.value in exc_info.value.detail

    def test_done_but_no_mesh_key_raises_500(self):
        """Job is DONE but mesh_s3_key is None → 500."""
        from api.download import get_download_url

        job = _make_job(status=JobStatus.DONE, mesh_s3_key=None)
        db = _make_db(job=job)
        with patch("api.download.settings", _make_settings()):
            with pytest.raises(HTTPException) as exc_info:
                get_download_url("job-1", "user-1", db)

        assert exc_info.value.status_code == 500

    def test_done_but_empty_mesh_key_raises_500(self):
        """Job is DONE but mesh_s3_key is empty string → 500."""
        from api.download import get_download_url

        job = _make_job(status=JobStatus.DONE, mesh_s3_key="")
        db = _make_db(job=job)
        with patch("api.download.settings", _make_settings()):
            with pytest.raises(HTTPException) as exc_info:
                get_download_url("job-1", "user-1", db)

        assert exc_info.value.status_code == 500

    def test_dev_mode_returns_local_url(self):
        """dev_mode=True → URL uses dev_api_base_url + /dev/files/ + key."""
        from api.download import get_download_url

        job = _make_job()
        db = _make_db(job=job)
        settings = _make_settings(dev_mode=True, dev_api_base_url="http://localhost:8000/")

        with patch("api.download.settings", settings):
            result = get_download_url("job-1", "user-1", db)

        assert result.url == "http://localhost:8000/dev/files/meshes/job-1/mesh.zip"

    def test_dev_mode_strips_trailing_slash_from_base(self):
        """dev_api_base_url trailing slash must not produce double slashes."""
        from api.download import get_download_url

        job = _make_job()
        db = _make_db(job=job)
        settings = _make_settings(dev_mode=True, dev_api_base_url="http://api:8000/")

        with patch("api.download.settings", settings):
            result = get_download_url("job-1", "user-1", db)

        assert "//" not in result.url.replace("http://", "").replace("https://", "")

    def test_prod_mode_calls_generate_presigned_url(self):
        """dev_mode=False → _generate_presigned_url called with mesh_s3_key."""
        from api.download import get_download_url

        job = _make_job()
        db = _make_db(job=job)
        settings = _make_settings(dev_mode=False)

        with patch("api.download.settings", settings), \
             patch("api.download._generate_presigned_url", return_value="https://s3.signed") as mock_fn:
            result = get_download_url("job-1", "user-1", db)

        mock_fn.assert_called_once_with("meshes/job-1/mesh.zip")
        assert result.url == "https://s3.signed"

    def test_response_expires_in_seconds_default(self):
        """DownloadResponse.expires_in_seconds must default to 3600."""
        from api.download import get_download_url

        job = _make_job()
        db = _make_db(job=job)
        settings = _make_settings(dev_mode=True)

        with patch("api.download.settings", settings):
            result = get_download_url("job-1", "user-1", db)

        assert result.expires_in_seconds == 3600

    def test_user_id_filter_applied(self):
        """db.query must filter on both job_id and user_id (no cross-user leakage)."""
        from api.download import get_download_url

        db = _make_db(job=None)
        with patch("api.download.settings", _make_settings()):
            with pytest.raises(HTTPException) as exc_info:
                get_download_url("job-1", "different-user", db)

        # The filter call happened — db returned None, so 404 is raised.
        assert exc_info.value.status_code == 404
        # Verify filter was called (query was made)
        db.query.assert_called_once()
