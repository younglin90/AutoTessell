"""
Unit tests for api/upload.py pure-function helpers.

Focus:
  _run_mesh_background  — dev-mode fire-and-forget wrapper (exceptions swallowed)
  _upload_to_s3         — prod S3 put_object path (never exercised in integration
                          tests, which always run with dev_mode=True)
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from api.upload import _run_mesh_background, _upload_to_s3


# ---------------------------------------------------------------------------
# _run_mesh_background
# ---------------------------------------------------------------------------

class TestRunMeshBackground:
    """Dev-mode background wrapper — calls run_mesh.apply, swallows exceptions."""

    def test_calls_run_mesh_apply_with_job_id(self):
        """run_mesh.apply must be called with kwargs={"job_id": <job_id>}."""
        with patch("worker.tasks.run_mesh") as mock_task:
            _run_mesh_background("job-bg-001")

        mock_task.apply.assert_called_once_with(kwargs={"job_id": "job-bg-001"})

    def test_exception_from_run_mesh_is_swallowed(self):
        """Exceptions from run_mesh.apply must be caught; background task must not propagate."""
        with patch("worker.tasks.run_mesh") as mock_task:
            mock_task.apply.side_effect = RuntimeError("pipeline exploded")
            # Must not raise — errors are logged, not re-raised
            _run_mesh_background("job-crash-001")

    def test_returns_none_on_success(self):
        """Return value is always None (fire-and-forget)."""
        with patch("worker.tasks.run_mesh"):
            result = _run_mesh_background("job-ok-001")
        assert result is None


# ---------------------------------------------------------------------------
# _upload_to_s3
# ---------------------------------------------------------------------------

class TestUploadToS3:
    """Prod S3 upload path — boto3 put_object with correct bucket/key/content."""

    def _call(self, content: bytes, key: str, mock_s3=None):
        if mock_s3 is None:
            mock_s3 = MagicMock()
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        mock_settings = MagicMock()
        mock_settings.s3_region = "us-east-1"
        mock_settings.aws_access_key_id = "key"
        mock_settings.aws_secret_access_key = "secret"
        mock_settings.s3_bucket = "test-bucket"

        with patch("api.upload.settings", mock_settings), \
             patch.dict(sys.modules, {"boto3": mock_boto3}):
            _upload_to_s3(content, key)

        return mock_s3

    def test_put_object_called_with_correct_params(self):
        """put_object must receive the correct Bucket, Key, and Body."""
        mock_s3 = self._call(b"stl content", "stl/job-1/input.stl")

        mock_s3.put_object.assert_called_once_with(
            Bucket="test-bucket", Key="stl/job-1/input.stl", Body=b"stl content"
        )

    def test_s3_exception_propagates(self):
        """S3 errors during upload must propagate — no silent swallowing."""
        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = Exception("S3 unavailable")

        with pytest.raises(Exception, match="S3 unavailable"):
            self._call(b"data", "stl/job-2/input.stl", mock_s3)

    def test_boto3_client_called_with_s3_service(self):
        """boto3.client must be called with 's3' as the first argument."""
        mock_s3 = MagicMock()
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        mock_settings = MagicMock()
        mock_settings.s3_region = "us-west-2"
        mock_settings.aws_access_key_id = "key-upload"
        mock_settings.aws_secret_access_key = "secret-upload"
        mock_settings.s3_bucket = "upload-bucket"

        with patch("api.upload.settings", mock_settings), \
             patch.dict(sys.modules, {"boto3": mock_boto3}):
            _upload_to_s3(b"content", "stl/job-x/input.stl")

        call_args = mock_boto3.client.call_args
        assert call_args[0][0] == "s3"
        assert call_args[1]["region_name"] == "us-west-2"
        assert call_args[1]["aws_access_key_id"] == "key-upload"
        assert call_args[1]["aws_secret_access_key"] == "secret-upload"
