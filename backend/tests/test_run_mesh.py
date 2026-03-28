"""
Unit tests for worker/tasks.py — run_mesh Celery task.

Covers:
  - Successful dev-mode execution: job transitions PROCESSING → DONE
  - Job result stats saved (num_cells, tier)
  - generate_mesh_dev called with correct target_cells / mesh_purpose
  - mesh stats passed=False → RuntimeError, refund issued
  - generate_mesh_dev raises → refund issued
  - Invalid mesh_params_json → falls back to params=None (no crash)
  - Valid mesh_params_json parsed and passed through
  - Job-not-found raises an exception
  - DB session closed on success and on failure
  - _download_s3 dev-mode path (shutil.copy2)
  - _upload_s3 dev-mode path (creates destination tree)
  - _zip_mesh creates a valid ZIP with relative paths
"""

import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from db import JobStatus
from worker.tasks import _download_s3, _mark_failed_and_refund, _upload_s3, _zip_mesh, run_mesh


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(
    job_id: str = "job-001",
    status: JobStatus = JobStatus.PAID,
    stl_s3_key: str = "/tmp/input.stl",
    target_cells: int = 100_000,
    mesh_purpose: str = "cfd",
    mesh_params_json: str | None = None,
    stripe_payment_intent_id: str | None = "pi_test",
) -> MagicMock:
    job = MagicMock()
    job.id = job_id
    job.status = status
    job.stl_s3_key = stl_s3_key
    job.target_cells = target_cells
    job.mesh_purpose = mesh_purpose
    job.mesh_params_json = mesh_params_json
    job.stripe_payment_intent_id = stripe_payment_intent_id
    return job


def _make_db(job: MagicMock | None) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = job
    return db


def _mock_stats(passed: bool = True, num_cells: int = 80, tier: str = "pytetwild_dev") -> dict:
    return {
        "passed": passed,
        "num_cells": num_cells,
        "tier": tier,
        "max_skewness": 1.5,
        "max_non_orthogonality": 40.0,
    }


# ---------------------------------------------------------------------------
# Context manager helper to set up standard dev-mode patches
# ---------------------------------------------------------------------------

from contextlib import contextmanager


def _fake_celery_self() -> MagicMock:
    """Simulate the Celery task `self` argument (bind=True)."""
    self = MagicMock()
    self.request.id = "celery-task-test-123"
    return self


@contextmanager
def _dev_mode_patches(db, gen_return=None, gen_raises=None):
    """Apply standard dev-mode patches for run_mesh tests."""
    mock_settings = MagicMock()
    mock_settings.dev_mode = True
    mock_settings.stripe_secret_key = "sk_test"

    gen_mock = MagicMock()
    if gen_raises is not None:
        gen_mock.side_effect = gen_raises
    else:
        gen_mock.return_value = gen_return if gen_return is not None else _mock_stats()

    with patch("worker.tasks.SessionLocal", return_value=db), \
         patch("worker.tasks.settings", mock_settings), \
         patch("worker.tasks._download_s3"), \
         patch("worker.tasks._zip_mesh"), \
         patch("worker.tasks._upload_s3"), \
         patch("worker.tasks._mark_failed_and_refund") as mock_refund, \
         patch("mesh.dev_pipeline.generate_mesh_dev", gen_mock) as mock_gen:
        yield mock_gen, mock_refund


# ---------------------------------------------------------------------------
# TestRunMeshDevMode
# ---------------------------------------------------------------------------

class TestRunMeshDevMode:
    def test_successful_run_returns_dict(self):
        job = _make_job()
        stats = _mock_stats(num_cells=150, tier="pytetwild_dev")

        with _dev_mode_patches(_make_db(job), gen_return=stats):
            result = run_mesh(_fake_celery_self(), job.id)

        assert result["job_id"] == job.id
        assert result["tier"] == "pytetwild_dev"
        assert result["num_cells"] == 150

    def test_job_marked_done_on_success(self):
        job = _make_job()

        with _dev_mode_patches(_make_db(job)):
            run_mesh(_fake_celery_self(), job.id)

        assert job.status == JobStatus.DONE

    def test_job_result_stats_saved(self):
        job = _make_job()
        stats = _mock_stats(num_cells=999, tier="netgen")

        with _dev_mode_patches(_make_db(job), gen_return=stats):
            run_mesh(_fake_celery_self(), job.id)

        assert job.result_num_cells == 999
        assert job.result_tier == "netgen"

    def test_generate_mesh_dev_called_with_correct_args(self):
        job = _make_job(target_cells=250_000, mesh_purpose="fea")

        with _dev_mode_patches(_make_db(job)) as (mock_gen, _):
            run_mesh(_fake_celery_self(), job.id)

        call_kwargs = mock_gen.call_args[1]
        assert call_kwargs["target_cells"] == 250_000
        assert call_kwargs["mesh_purpose"] == "fea"

    def test_none_target_cells_defaults_to_500k(self):
        """job.target_cells=None must fall back to 500_000 (not raise TypeError)."""
        job = _make_job(target_cells=None)

        with _dev_mode_patches(_make_db(job)) as (mock_gen, _):
            run_mesh(_fake_celery_self(), job.id)

        call_kwargs = mock_gen.call_args[1]
        assert call_kwargs["target_cells"] == 500_000

    def test_none_mesh_purpose_defaults_to_cfd(self):
        """job.mesh_purpose=None must fall back to 'cfd' (not pass None)."""
        job = _make_job(mesh_purpose=None)

        with _dev_mode_patches(_make_db(job)) as (mock_gen, _):
            run_mesh(_fake_celery_self(), job.id)

        call_kwargs = mock_gen.call_args[1]
        assert call_kwargs["mesh_purpose"] == "cfd"

    def test_passed_false_raises_and_calls_refund(self):
        job = _make_job()
        stats = _mock_stats(passed=False)

        with _dev_mode_patches(_make_db(job), gen_return=stats) as (_, mock_refund):
            with pytest.raises(RuntimeError, match="checkMesh FAILED"):
                run_mesh(_fake_celery_self(), job.id)

        mock_refund.assert_called_once()

    def test_mesh_generation_error_calls_refund(self):
        job = _make_job()

        with _dev_mode_patches(_make_db(job), gen_raises=RuntimeError("pytetwild died")) as (_, mock_refund):
            with pytest.raises(RuntimeError):
                run_mesh(_fake_celery_self(), job.id)

        mock_refund.assert_called_once()
        args = mock_refund.call_args[0]
        assert args[0] == job.id

    def test_invalid_mesh_params_json_uses_defaults(self):
        job = _make_job(mesh_params_json="{not valid json}")

        with _dev_mode_patches(_make_db(job)) as (mock_gen, _):
            result = run_mesh(_fake_celery_self(), job.id)

        assert result["tier"] == "pytetwild_dev"
        call_kwargs = mock_gen.call_args[1]
        assert call_kwargs["params"] is None

    def test_valid_mesh_params_json_passed_through(self):
        import json
        job = _make_job(mesh_params_json=json.dumps({"tet_stop_energy": 5.0}))

        with _dev_mode_patches(_make_db(job)) as (mock_gen, _):
            run_mesh(_fake_celery_self(), job.id)

        call_kwargs = mock_gen.call_args[1]
        assert call_kwargs["params"] is not None
        assert call_kwargs["params"].tet_stop_energy == pytest.approx(5.0)

    def test_job_not_found_raises(self):
        db = _make_db(None)  # query returns None

        with _dev_mode_patches(db) as (_, mock_refund):
            with pytest.raises(Exception):
                run_mesh(_fake_celery_self(), "nonexistent-job")

    def test_db_closed_on_success(self):
        job = _make_job()
        db = _make_db(job)

        with _dev_mode_patches(db):
            run_mesh(_fake_celery_self(), job.id)

        db.close.assert_called_once()

    def test_db_closed_on_failure(self):
        job = _make_job()
        db = _make_db(job)

        with _dev_mode_patches(db, gen_raises=RuntimeError("crash")):
            with pytest.raises(RuntimeError):
                run_mesh(_fake_celery_self(), job.id)

        db.close.assert_called_once()

    def test_processing_status_set_before_generation(self):
        """Job must be marked PROCESSING before the mesh generator runs."""
        job = _make_job()
        status_at_gen_call = []

        def capture_status(*args, **kwargs):
            status_at_gen_call.append(job.status)
            return _mock_stats()

        mock_settings = MagicMock()
        mock_settings.dev_mode = True
        mock_settings.stripe_secret_key = "sk_test"

        with patch("worker.tasks.SessionLocal", return_value=_make_db(job)), \
             patch("worker.tasks.settings", mock_settings), \
             patch("worker.tasks._download_s3"), \
             patch("worker.tasks._zip_mesh"), \
             patch("worker.tasks._upload_s3"), \
             patch("worker.tasks._mark_failed_and_refund"), \
             patch("mesh.dev_pipeline.generate_mesh_dev", side_effect=capture_status):
            run_mesh(_fake_celery_self(), job.id)

        assert status_at_gen_call[0] == JobStatus.PROCESSING

    def test_soft_time_limit_calls_refund_with_timeout_message(self):
        """SoftTimeLimitExceeded must trigger refund with timeout message and re-raise."""
        from celery.exceptions import SoftTimeLimitExceeded
        job = _make_job()

        with _dev_mode_patches(_make_db(job), gen_raises=SoftTimeLimitExceeded("limit")) as (_, mock_refund):
            with pytest.raises(SoftTimeLimitExceeded):
                run_mesh(_fake_celery_self(), job.id)

        mock_refund.assert_called_once()
        call_args = mock_refund.call_args[0]
        assert call_args[0] == job.id
        assert "timed out" in call_args[1].lower()

    def test_soft_time_limit_refund_called_once_not_twice(self):
        """SoftTimeLimitExceeded must NOT double-invoke refund (caught separately from Exception)."""
        from celery.exceptions import SoftTimeLimitExceeded
        job = _make_job()

        with _dev_mode_patches(_make_db(job), gen_raises=SoftTimeLimitExceeded("limit")) as (_, mock_refund):
            with pytest.raises(SoftTimeLimitExceeded):
                run_mesh(_fake_celery_self(), job.id)

        assert mock_refund.call_count == 1

    def test_celery_task_id_stored_on_processing(self):
        """job.celery_task_id must be set to Celery's self.request.id when PROCESSING begins."""
        job = _make_job()

        with _dev_mode_patches(_make_db(job)):
            run_mesh(_fake_celery_self(), job.id)

        assert job.celery_task_id == "celery-task-test-123"

    def test_mesh_s3_key_stored_on_success(self):
        """After success, job.mesh_s3_key must be 'meshes/{job_id}/mesh.zip'."""
        job = _make_job(job_id="job-key-test")

        with _dev_mode_patches(_make_db(job)):
            run_mesh(_fake_celery_self(), job.id)

        assert job.mesh_s3_key == "meshes/job-key-test/mesh.zip"


# ---------------------------------------------------------------------------
# TestDownloadS3DevMode
# ---------------------------------------------------------------------------

class TestDownloadS3DevMode:
    def test_copies_file_in_dev_mode(self, tmp_path: Path):
        src = tmp_path / "source.stl"
        src.write_bytes(b"STL content")
        dest = tmp_path / "dest.stl"

        mock_settings = MagicMock()
        mock_settings.dev_mode = True

        with patch("worker.tasks.settings", mock_settings):
            _download_s3(str(src), dest)

        assert dest.exists()
        assert dest.read_bytes() == b"STL content"


# ---------------------------------------------------------------------------
# TestUploadS3DevMode
# ---------------------------------------------------------------------------

class TestUploadS3DevMode:
    def test_copies_file_to_dev_storage(self, tmp_path: Path):
        src = tmp_path / "mesh.zip"
        src.write_bytes(b"ZIP content")
        storage_root = tmp_path / "storage"

        mock_settings = MagicMock()
        mock_settings.dev_mode = True
        mock_settings.dev_storage_path = str(storage_root)

        with patch("worker.tasks.settings", mock_settings):
            _upload_s3(src, "meshes/job-001/mesh.zip")

        dest = storage_root / "meshes" / "job-001" / "mesh.zip"
        assert dest.exists()
        assert dest.read_bytes() == b"ZIP content"

    def test_creates_parent_directories(self, tmp_path: Path):
        src = tmp_path / "mesh.zip"
        src.write_bytes(b"data")
        storage_root = tmp_path / "nonexistent_storage"

        mock_settings = MagicMock()
        mock_settings.dev_mode = True
        mock_settings.dev_storage_path = str(storage_root)

        with patch("worker.tasks.settings", mock_settings):
            _upload_s3(src, "deep/nested/path/mesh.zip")

        assert (storage_root / "deep" / "nested" / "path" / "mesh.zip").exists()


# ---------------------------------------------------------------------------
# TestZipMesh
# ---------------------------------------------------------------------------

class TestZipMesh:
    def test_zip_contains_all_files(self, tmp_path: Path):
        mesh_dir = tmp_path / "case"
        (mesh_dir / "constant" / "polyMesh").mkdir(parents=True)
        (mesh_dir / "constant" / "polyMesh" / "faces").write_text("face data")
        (mesh_dir / "constant" / "polyMesh" / "points").write_text("point data")
        (mesh_dir / "system").mkdir(parents=True)
        (mesh_dir / "system" / "controlDict").write_text("controlDict")

        zip_path = tmp_path / "mesh.zip"
        _zip_mesh(mesh_dir, zip_path)

        assert zip_path.exists()
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
        assert "constant/polyMesh/faces" in names
        assert "constant/polyMesh/points" in names
        assert "system/controlDict" in names

    def test_zip_paths_are_relative(self, tmp_path: Path):
        mesh_dir = tmp_path / "case"
        mesh_dir.mkdir()
        (mesh_dir / "file.txt").write_text("data")

        zip_path = tmp_path / "out.zip"
        _zip_mesh(mesh_dir, zip_path)

        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert all(not n.startswith("/") for n in names)
        assert "file.txt" in names

    def test_empty_dir_produces_valid_zip(self, tmp_path: Path):
        mesh_dir = tmp_path / "empty_case"
        mesh_dir.mkdir()
        zip_path = tmp_path / "empty.zip"
        _zip_mesh(mesh_dir, zip_path)

        assert zip_path.exists()
        with zipfile.ZipFile(zip_path) as zf:
            assert zf.namelist() == []


# ---------------------------------------------------------------------------
# Production mode (dev_mode=False) — uses generate_mesh, not generate_mesh_dev
# ---------------------------------------------------------------------------

@contextmanager
def _prod_mode_patches(db, gen_return=None, gen_raises=None):
    """Apply standard production-mode patches for run_mesh tests."""
    mock_settings = MagicMock()
    mock_settings.dev_mode = False
    mock_settings.stripe_secret_key = "sk_live_test"

    gen_mock = MagicMock()
    if gen_raises is not None:
        gen_mock.side_effect = gen_raises
    else:
        gen_mock.return_value = gen_return if gen_return is not None else _mock_stats(tier="snappy")

    with patch("worker.tasks.SessionLocal", return_value=db), \
         patch("worker.tasks.settings", mock_settings), \
         patch("worker.tasks._download_s3"), \
         patch("worker.tasks._zip_mesh"), \
         patch("worker.tasks._upload_s3"), \
         patch("worker.tasks._mark_failed_and_refund") as mock_refund, \
         patch("worker.tasks.generate_mesh", gen_mock) as mock_gen:
        yield mock_gen, mock_refund


class TestRunMeshProductionMode:
    def test_calls_generate_mesh_not_dev(self):
        """Production mode must call generate_mesh, not generate_mesh_dev."""
        job = _make_job()
        db = _make_db(job)

        with _prod_mode_patches(db) as (mock_gen, _):
            result = run_mesh(_fake_celery_self(), job.id)

        mock_gen.assert_called_once()
        assert result["tier"] == "snappy"

    def test_production_mode_marks_done(self):
        job = _make_job()
        db = _make_db(job)

        with _prod_mode_patches(db):
            run_mesh(_fake_celery_self(), job.id)

        assert job.status == JobStatus.DONE

    def test_production_mode_failure_calls_refund(self):
        """Exception in production pipeline must trigger refund."""
        from mesh.generator import MeshGenerationError
        job = _make_job()
        db = _make_db(job)

        with _prod_mode_patches(db, gen_raises=MeshGenerationError("all tiers failed")) as (_, mock_refund):
            with pytest.raises(MeshGenerationError):
                run_mesh(_fake_celery_self(), job.id)

        mock_refund.assert_called_once()

    def test_max_skewness_in_return_dict(self):
        """Returned dict must include max_skewness from stats."""
        job = _make_job()
        db = _make_db(job)
        stats = _mock_stats(tier="snappy")
        stats["max_skewness"] = 2.3

        with _prod_mode_patches(db, gen_return=stats):
            result = run_mesh(_fake_celery_self(), job.id)

        assert result["max_skewness"] == pytest.approx(2.3)


# ---------------------------------------------------------------------------
# _mark_failed_and_refund — db.close() in finally
# ---------------------------------------------------------------------------

class TestMarkFailedAndRefundDbClose:
    def test_db_closed_on_normal_path(self):
        """_mark_failed_and_refund must close its own DB session."""
        job = _make_job()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = job

        with patch("worker.tasks.SessionLocal", return_value=db):
            with patch("worker.tasks.stripe"):
                _mark_failed_and_refund("test-job", "error")

        db.close.assert_called_once()

    def test_db_closed_even_when_stripe_raises(self):
        """DB session must be closed even if stripe.Refund.create raises an unexpected error."""
        import stripe as real_stripe
        job = _make_job()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = job

        with patch("worker.tasks.SessionLocal", return_value=db):
            with patch("worker.tasks.stripe") as mock_stripe:
                mock_stripe.Refund.create.side_effect = Exception("unexpected error")
                mock_stripe.StripeError = real_stripe.StripeError
                try:
                    _mark_failed_and_refund("test-job", "error")
                except Exception:
                    pass  # unexpected errors may propagate

        db.close.assert_called_once()


# ---------------------------------------------------------------------------
# Production-mode S3 helpers (_download_s3 and _upload_s3, dev_mode=False)
# ---------------------------------------------------------------------------

class TestDownloadS3ProdMode:
    def test_calls_download_file_in_prod_mode(self, tmp_path: Path):
        """_download_s3 prod path must call s3_client.download_file with correct args."""
        dest = tmp_path / "out.stl"
        mock_s3_client = MagicMock()
        mock_settings = MagicMock()
        mock_settings.dev_mode = False
        mock_settings.s3_bucket = "prod-bucket"

        with patch("worker.tasks.settings", mock_settings), \
             patch("worker.tasks._s3_client", return_value=mock_s3_client):
            _download_s3("stl/job-prod/input.stl", dest)

        mock_s3_client.download_file.assert_called_once_with(
            "prod-bucket", "stl/job-prod/input.stl", str(dest)
        )


class TestUploadS3ProdMode:
    def test_calls_upload_file_in_prod_mode(self, tmp_path: Path):
        """_upload_s3 prod path must call s3_client.upload_file with correct args."""
        src = tmp_path / "mesh.zip"
        src.write_bytes(b"zip data")
        mock_s3_client = MagicMock()
        mock_settings = MagicMock()
        mock_settings.dev_mode = False
        mock_settings.s3_bucket = "prod-bucket"

        with patch("worker.tasks.settings", mock_settings), \
             patch("worker.tasks._s3_client", return_value=mock_s3_client):
            _upload_s3(src, "meshes/job-prod/mesh.zip")

        mock_s3_client.upload_file.assert_called_once_with(
            str(src), "prod-bucket", "meshes/job-prod/mesh.zip"
        )
