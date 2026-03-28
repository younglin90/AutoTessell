"""
Unit tests for api/jobs.py pure functions.

Focus:
  _delete_job_files S3 prod-mode path  — never exercised by integration tests
                                          (which always run with dev_mode=True)
  _delete_job_files dev-mode path      — local shutil.rmtree removal
"""

import sys
from unittest.mock import MagicMock, patch

from api.jobs import _delete_job_files


def _make_job(stl_key=None, mesh_key=None):
    job = MagicMock()
    job.id = "test-job-id"
    job.stl_s3_key = stl_key
    job.mesh_s3_key = mesh_key
    return job


class TestDeleteJobFilesProdMode:
    """_delete_job_files S3 cleanup path (settings.dev_mode = False).

    Integration tests always run in dev_mode=True, so the S3 path is never
    exercised there.  These unit tests patch `api.jobs.settings` and boto3 to
    cover every branch of the else-block.
    """

    def _call_prod(self, job, mock_s3=None):
        """Invoke _delete_job_files with dev_mode=False and a controlled boto3 stub.

        Returns the mock_s3 instance so callers can assert on its calls.
        """
        if mock_s3 is None:
            mock_s3 = MagicMock()
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        mock_settings = MagicMock()
        mock_settings.dev_mode = False
        mock_settings.s3_region = "us-east-1"
        mock_settings.aws_access_key_id = "key"
        mock_settings.aws_secret_access_key = "secret"
        mock_settings.s3_bucket = "test-bucket"

        with patch("api.jobs.settings", mock_settings), \
             patch.dict(sys.modules, {"boto3": mock_boto3}):
            _delete_job_files(job)

        return mock_s3

    def test_both_keys_present_calls_delete_objects(self):
        """Both stl_s3_key and mesh_s3_key → delete_objects with two entries."""
        job = _make_job("stl/j/file.stl", "meshes/j/mesh.zip")
        mock_s3 = self._call_prod(job)

        mock_s3.delete_objects.assert_called_once()
        objects = mock_s3.delete_objects.call_args[1]["Delete"]["Objects"]
        keys = {o["Key"] for o in objects}
        assert keys == {"stl/j/file.stl", "meshes/j/mesh.zip"}

    def test_only_stl_key_deletes_one_object(self):
        """Only stl_s3_key set → delete_objects with one entry."""
        job = _make_job("stl/j/file.stl", None)
        mock_s3 = self._call_prod(job)

        mock_s3.delete_objects.assert_called_once()
        objects = mock_s3.delete_objects.call_args[1]["Delete"]["Objects"]
        assert len(objects) == 1
        assert objects[0]["Key"] == "stl/j/file.stl"

    def test_only_mesh_key_deletes_one_object(self):
        """Only mesh_s3_key set → delete_objects with one entry."""
        job = _make_job(None, "meshes/j/mesh.zip")
        mock_s3 = self._call_prod(job)

        mock_s3.delete_objects.assert_called_once()
        objects = mock_s3.delete_objects.call_args[1]["Delete"]["Objects"]
        assert len(objects) == 1
        assert objects[0]["Key"] == "meshes/j/mesh.zip"

    def test_no_keys_skips_delete_objects_call(self):
        """Neither key set → delete_objects never called (avoids empty S3 call)."""
        job = _make_job(None, None)
        mock_s3 = self._call_prod(job)

        mock_s3.delete_objects.assert_not_called()

    def test_s3_exception_is_swallowed(self):
        """S3 failures during cleanup must not propagate — best-effort removal."""
        mock_s3 = MagicMock()
        mock_s3.delete_objects.side_effect = Exception("S3 unavailable")

        job = _make_job("stl/j/file.stl", "meshes/j/mesh.zip")
        # Should not raise despite S3 error
        self._call_prod(job, mock_s3)


# ---------------------------------------------------------------------------
# dev-mode path: local shutil.rmtree removal
# ---------------------------------------------------------------------------

class TestDeleteJobFilesDevMode:
    """_delete_job_files dev-mode path — removes stl/ and meshes/ subdirs locally."""

    def _call_dev(self, job, storage_root, dirs_to_create=()):
        for subdir in dirs_to_create:
            d = storage_root / subdir / job.id
            d.mkdir(parents=True, exist_ok=True)
            (d / "dummy.file").write_text("data")

        mock_settings = MagicMock()
        mock_settings.dev_mode = True
        mock_settings.dev_storage_path = str(storage_root)

        with patch("api.jobs.settings", mock_settings):
            _delete_job_files(job)

    def test_stl_dir_removed_when_exists(self, tmp_path):
        """stl/{job_id}/ must be removed when it exists."""
        job = _make_job()
        self._call_dev(job, tmp_path, dirs_to_create=["stl"])
        assert not (tmp_path / "stl" / job.id).exists()

    def test_meshes_dir_removed_when_exists(self, tmp_path):
        """meshes/{job_id}/ must be removed when it exists."""
        job = _make_job()
        self._call_dev(job, tmp_path, dirs_to_create=["meshes"])
        assert not (tmp_path / "meshes" / job.id).exists()

    def test_nonexistent_dirs_skipped_silently(self, tmp_path):
        """If neither stl nor meshes dir exists, must complete without raising."""
        job = _make_job()
        self._call_dev(job, tmp_path)   # no dirs created

    def test_rmtree_failure_is_swallowed(self, tmp_path):
        """shutil.rmtree errors must be swallowed — best-effort cleanup."""
        job = _make_job()
        (tmp_path / "stl" / job.id).mkdir(parents=True)

        mock_settings = MagicMock()
        mock_settings.dev_mode = True
        mock_settings.dev_storage_path = str(tmp_path)

        with patch("api.jobs.settings", mock_settings), \
             patch("api.jobs.shutil.rmtree", side_effect=PermissionError("locked")):
            _delete_job_files(job)   # must not raise
