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


# ---------------------------------------------------------------------------
# list_jobs — response building
# ---------------------------------------------------------------------------

from datetime import datetime


def _make_list_job(**kwargs):
    """Return a mock Job with sensible defaults for list_jobs tests."""
    from db import JobStatus
    job = MagicMock()
    job.id = kwargs.get("id", "job-abc")
    job.status = kwargs.get("status", JobStatus.DONE)
    job.stl_filename = kwargs.get("stl_filename", "model.stl")
    job.target_cells = kwargs.get("target_cells", 500_000)
    job.mesh_purpose = kwargs.get("mesh_purpose", "cfd")
    job.mesh_params_json = kwargs.get("mesh_params_json", None)
    job.created_at = kwargs.get("created_at", datetime(2026, 1, 1, 12, 0, 0))
    return job


class TestListJobsResponseBuilding:
    """list_jobs — pure response-building logic, not the DB query itself."""

    def _call(self, jobs, limit=20):
        from api.jobs import list_jobs
        from db import JobStatus

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = jobs

        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        return list_jobs(user_id="u1", limit=limit, db=mock_db)

    def test_job_id_stringified(self):
        """job.id must be converted to str in the response."""
        j = _make_list_job(id="job-123")
        result = self._call([j])
        assert result[0].job_id == "job-123"

    def test_status_value_used(self):
        """job.status.value must be the string representation in the response."""
        from db import JobStatus
        j = _make_list_job(status=JobStatus.DONE)
        result = self._call([j])
        assert result[0].status == JobStatus.DONE.value

    def test_target_cells_none_defaults_to_500k(self):
        """job.target_cells=None must fall back to 500_000."""
        j = _make_list_job(target_cells=None)
        result = self._call([j])
        assert result[0].target_cells == 500_000

    def test_mesh_purpose_none_defaults_to_cfd(self):
        """job.mesh_purpose=None must fall back to 'cfd'."""
        j = _make_list_job(mesh_purpose=None)
        result = self._call([j])
        assert result[0].mesh_purpose == "cfd"

    def test_has_pro_params_false_when_json_is_none(self):
        """job.mesh_params_json=None → has_pro_params=False."""
        j = _make_list_job(mesh_params_json=None)
        result = self._call([j])
        assert result[0].has_pro_params is False

    def test_has_pro_params_true_when_json_is_set(self):
        """job.mesh_params_json='{"tet_stop_energy": 5}' → has_pro_params=True."""
        j = _make_list_job(mesh_params_json='{"tet_stop_energy": 5}')
        result = self._call([j])
        assert result[0].has_pro_params is True

    def test_created_at_none_returns_empty_string(self):
        """job.created_at=None → created_at='' in response."""
        j = _make_list_job(created_at=None)
        result = self._call([j])
        assert result[0].created_at == ""

    def test_created_at_iso_format_has_z_suffix(self):
        """job.created_at → ISO-format string with 'Z' suffix."""
        j = _make_list_job(created_at=datetime(2026, 3, 15, 10, 30, 0))
        result = self._call([j])
        assert result[0].created_at == "2026-03-15T10:30:00Z"

    def test_limit_clamped_to_100(self):
        """limit > 100 must be clamped to 100."""
        jobs = [_make_list_job() for _ in range(5)]
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = jobs
        mock_query.limit.return_value = mock_query

        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        from api.jobs import list_jobs
        list_jobs(user_id="u1", limit=9999, db=mock_db)

        # Verify limit was called with a value <= 100
        limit_arg = mock_query.limit.call_args[0][0]
        assert limit_arg <= 100

    def test_limit_clamped_to_zero_when_negative(self):
        """limit < 0 must be clamped to 0 (max(0, ...))."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.limit.return_value = mock_query

        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        from api.jobs import list_jobs
        list_jobs(user_id="u1", limit=-5, db=mock_db)

        limit_arg = mock_query.limit.call_args[0][0]
        assert limit_arg == 0


# ---------------------------------------------------------------------------
# get_job_status — None timestamp branches
# ---------------------------------------------------------------------------

class TestGetJobStatusResponseBuilding:
    """get_job_status — response building for None timestamp fields."""

    def _call(self, job):
        from api.jobs import get_job_status
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = job
        return get_job_status(job_id=str(job.id), user_id="u1", db=mock_db)

    def _make_job(self, **kwargs):
        from db import JobStatus
        job = MagicMock()
        job.id = kwargs.get("id", "job-abc")
        job.status = kwargs.get("status", JobStatus.DONE)
        job.error_message = kwargs.get("error_message", None)
        job.amount_cents = kwargs.get("amount_cents", 0)
        job.stl_filename = kwargs.get("stl_filename", "model.stl")
        job.target_cells = kwargs.get("target_cells", 500_000)
        job.mesh_purpose = kwargs.get("mesh_purpose", "cfd")
        job.mesh_params_json = kwargs.get("mesh_params_json", None)
        job.result_num_cells = kwargs.get("result_num_cells", None)
        job.result_tier = kwargs.get("result_tier", None)
        job.created_at = kwargs.get("created_at", datetime(2026, 1, 1, 12, 0, 0))
        job.updated_at = kwargs.get("updated_at", datetime(2026, 1, 1, 13, 0, 0))
        return job

    def test_created_at_none_returns_none(self):
        """job.created_at=None → created_at=None in response."""
        job = self._make_job(created_at=None)
        result = self._call(job)
        assert result.created_at is None

    def test_updated_at_none_returns_none(self):
        """job.updated_at=None → updated_at=None in response."""
        job = self._make_job(updated_at=None)
        result = self._call(job)
        assert result.updated_at is None

    def test_created_at_set_returns_iso_with_z(self):
        """job.created_at set → ISO string with 'Z' suffix."""
        job = self._make_job(created_at=datetime(2026, 3, 28, 9, 0, 0))
        result = self._call(job)
        assert result.created_at == "2026-03-28T09:00:00Z"

    def test_download_ready_true_when_done(self):
        """job.status=DONE → download_ready=True."""
        from db import JobStatus
        job = self._make_job(status=JobStatus.DONE)
        result = self._call(job)
        assert result.download_ready is True

    def test_download_ready_false_when_processing(self):
        """job.status=PROCESSING → download_ready=False."""
        from db import JobStatus
        job = self._make_job(status=JobStatus.PROCESSING)
        result = self._call(job)
        assert result.download_ready is False

    def test_amount_cents_none_returns_zero(self):
        """job.amount_cents=None → amount_cents=0 in response."""
        job = self._make_job(amount_cents=None)
        result = self._call(job)
        assert result.amount_cents == 0

    def test_target_cells_none_defaults_to_500k(self):
        """job.target_cells=None → target_cells=500_000 in response."""
        job = self._make_job(target_cells=None)
        result = self._call(job)
        assert result.target_cells == 500_000

    def test_mesh_purpose_none_defaults_to_cfd(self):
        """job.mesh_purpose=None → mesh_purpose='cfd' in response."""
        job = self._make_job(mesh_purpose=None)
        result = self._call(job)
        assert result.mesh_purpose == "cfd"
