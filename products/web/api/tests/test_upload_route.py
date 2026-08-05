"""
Unit tests for the upload_stl route handler (api/upload.py).

The integration tests always run with dev_mode=True, so they don't cover:
  - user_id validation branches (blank, oversized)
  - mesh_purpose validation
  - target_cells range validation
  - mesh_params size/JSON validation
  - The prod path (S3 upload + Stripe PaymentIntent)

These unit tests cover those branches directly by calling the async route handler
without a running server.

Branches covered:
  1.  user_id blank → 400
  2.  user_id too long (> 255 chars) → 400
  3.  mesh_purpose invalid → 400
  4.  target_cells below minimum → 400
  5.  target_cells above maximum → 400
  6.  mesh_params too large (> 4096 bytes) → 400
  7.  mesh_params invalid JSON → 400
  8.  Non-.stl filename → 400
  9.  STLValidationError from validate_stl → 400
  10. Active job limit exceeded → 429 with Retry-After header
  11. Dev mode path — local file written, background task added, response
  12. Prod mode path — S3 uploaded, Stripe PaymentIntent created, response
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# Minimal valid STL content (ASCII, 1 triangle) used across tests
_MINIMAL_STL = (
    b"solid test\n"
    b"  facet normal 0 0 1\n"
    b"    outer loop\n"
    b"      vertex 0 0 0\n"
    b"      vertex 1 0 0\n"
    b"      vertex 0 1 0\n"
    b"    endloop\n"
    b"  endfacet\n"
    b"endsolid test\n"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_file(filename: str = "model.stl", content: bytes = _MINIMAL_STL) -> MagicMock:
    """Return a mock FastAPI UploadFile."""
    f = MagicMock()
    f.filename = filename
    f.read = AsyncMock(return_value=content)
    return f


def _make_background_tasks() -> MagicMock:
    return MagicMock()


def _make_db(active_count: int = 0) -> MagicMock:
    """Return a mock Session where active job count = active_count."""
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = active_count
    return db


def _make_settings(
    dev_mode: bool = True,
    max_stl_size_bytes: int = 50 * 1024 * 1024,
    max_jobs_per_user: int = 2,
    mesh_price_cents: int = 500,
    dev_storage_path: str = "/tmp/dev-storage",
    dev_api_base_url: str = "http://localhost:8000",
    stripe_secret_key: str = "sk_test",
    s3_bucket: str = "test-bucket",
    s3_region: str = "us-east-1",
    aws_access_key_id: str = "key",
    aws_secret_access_key: str = "secret",
) -> MagicMock:
    s = MagicMock()
    s.dev_mode = dev_mode
    s.max_stl_size_bytes = max_stl_size_bytes
    s.max_jobs_per_user = max_jobs_per_user
    s.mesh_price_cents = mesh_price_cents
    s.dev_storage_path = dev_storage_path
    s.dev_api_base_url = dev_api_base_url
    s.stripe_secret_key = stripe_secret_key
    s.s3_bucket = s3_bucket
    s.s3_region = s3_region
    s.aws_access_key_id = aws_access_key_id
    s.aws_secret_access_key = aws_secret_access_key
    return s


async def _call(
    *,
    file=None,
    background_tasks=None,
    user_id: str = "user-1",
    target_cells: int = 500_000,
    mesh_purpose: str = "cfd",
    mesh_params: str = "",
    db=None,
    settings=None,
    mock_validate_stl=None,
    stripe_stub=None,
):
    """Convenience wrapper: calls upload_stl with mocked dependencies."""
    from api.upload import upload_stl

    if file is None:
        file = _make_file()
    if background_tasks is None:
        background_tasks = _make_background_tasks()
    if db is None:
        db = _make_db()
    if settings is None:
        settings = _make_settings()
    if mock_validate_stl is None:
        mock_validate_stl = MagicMock()  # no-op by default

    # Job() takes no arguments in the stub env (SQLAlchemy stub); patch it.
    mock_job_cls = MagicMock(return_value=MagicMock())

    # Provide a stripe stub with real string values so Pydantic accepts them.
    if stripe_stub is None:
        _intent = MagicMock()
        _intent.id = "pi_test_123"
        _intent.client_secret = "pi_test_secret_abc"
        stripe_stub = MagicMock()
        stripe_stub.PaymentIntent.create.return_value = _intent

    with patch("api.upload.settings", settings), \
         patch("api.upload.validate_stl", mock_validate_stl), \
         patch("api.upload.Job", mock_job_cls), \
         patch("api.upload.stripe", stripe_stub):
        return await upload_stl(
            file=file,
            background_tasks=background_tasks,
            user_id=user_id,
            target_cells=target_cells,
            mesh_purpose=mesh_purpose,
            mesh_params=mesh_params,
            db=db,
        )


# ---------------------------------------------------------------------------
# user_id validation
# ---------------------------------------------------------------------------

class TestUserIdValidation:
    async def test_blank_user_id_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            await _call(user_id="")
        assert exc_info.value.status_code == 400
        assert "user_id" in exc_info.value.detail

    async def test_oversized_user_id_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            await _call(user_id="x" * 256)
        assert exc_info.value.status_code == 400
        assert "user_id" in exc_info.value.detail

    async def test_max_length_user_id_accepted(self):
        """user_id of exactly 255 chars must be accepted (boundary)."""
        result = await _call(
            user_id="u" * 255,
            settings=_make_settings(dev_mode=True),
        )
        assert result is not None


# ---------------------------------------------------------------------------
# mesh_purpose validation
# ---------------------------------------------------------------------------

class TestMeshPurposeValidation:
    async def test_invalid_mesh_purpose_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            await _call(mesh_purpose="invalid")
        assert exc_info.value.status_code == 400
        assert "mesh_purpose" in exc_info.value.detail

    async def test_cfd_accepted(self):
        result = await _call(mesh_purpose="cfd")
        assert result is not None

    async def test_fea_accepted(self):
        result = await _call(mesh_purpose="fea")
        assert result is not None


# ---------------------------------------------------------------------------
# target_cells validation
# ---------------------------------------------------------------------------

class TestTargetCellsValidation:
    async def test_below_minimum_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            await _call(target_cells=999)
        assert exc_info.value.status_code == 400
        assert "target_cells" in exc_info.value.detail

    async def test_above_maximum_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            await _call(target_cells=10_000_001)
        assert exc_info.value.status_code == 400
        assert "target_cells" in exc_info.value.detail

    async def test_minimum_boundary_accepted(self):
        result = await _call(target_cells=1_000)
        assert result is not None

    async def test_maximum_boundary_accepted(self):
        result = await _call(target_cells=10_000_000)
        assert result is not None


# ---------------------------------------------------------------------------
# mesh_params validation
# ---------------------------------------------------------------------------

class TestMeshParamsValidation:
    async def test_oversized_mesh_params_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            await _call(mesh_params="x" * 4097)
        assert exc_info.value.status_code == 400
        assert "mesh_params" in exc_info.value.detail

    async def test_invalid_json_mesh_params_raises_400(self):
        """Invalid JSON in mesh_params → 400 with 'Invalid mesh_params' detail."""
        fake_mesh_params = MagicMock()
        # Simulate MeshParams raising ValueError on bad JSON
        with patch("mesh.params.MeshParams") as mock_cls:
            mock_cls.from_json.side_effect = ValueError("bad JSON")
            with pytest.raises(HTTPException) as exc_info:
                await _call(mesh_params='{"bad": json}')
        assert exc_info.value.status_code == 400

    async def test_empty_mesh_params_skips_validation(self):
        """Empty string mesh_params → validation step skipped, upload proceeds."""
        result = await _call(mesh_params="")
        assert result is not None

    async def test_valid_mesh_params_accepted(self):
        """Valid JSON mesh_params ≤ 4096 bytes, valid MeshParams → accepted."""
        valid_json = json.dumps({"algorithm": "snappyHexMesh"})
        fake_mp = MagicMock()
        fake_mp.validated.return_value = fake_mp

        with patch("mesh.params.MeshParams") as mock_cls:
            mock_cls.from_json.return_value = fake_mp
            result = await _call(mesh_params=valid_json)

        assert result is not None

    async def test_json_decode_error_raises_400(self):
        """Truly invalid JSON (not parseable) in mesh_params → 400 via JSONDecodeError path."""
        # Don't patch MeshParams — let actual json.loads fail with JSONDecodeError
        with pytest.raises(HTTPException) as exc_info:
            await _call(mesh_params="not valid json at all !!!")
        assert exc_info.value.status_code == 400
        assert "mesh_params" in exc_info.value.detail.lower()

    async def test_type_error_from_mesh_params_raises_400(self):
        """TypeError from MeshParams.from_json (e.g. wrong field type) → 400."""
        with patch("mesh.params.MeshParams") as mock_cls:
            mock_cls.from_json.side_effect = TypeError("unexpected type")
            with pytest.raises(HTTPException) as exc_info:
                await _call(mesh_params='{"tet_stop_energy": "should be float"}')
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# File extension validation
# ---------------------------------------------------------------------------

class TestFileExtensionValidation:
    async def test_non_stl_extension_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            await _call(file=_make_file(filename="model.obj"))
        assert exc_info.value.status_code == 400
        assert ".stl" in exc_info.value.detail.lower() or "stl" in exc_info.value.detail.lower()

    async def test_uppercase_stl_extension_accepted(self):
        result = await _call(file=_make_file(filename="MODEL.STL"))
        assert result is not None

    async def test_no_extension_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            await _call(file=_make_file(filename="model"))
        assert exc_info.value.status_code == 400

    async def test_none_filename_raises_400(self):
        """file.filename=None → filename='' via `or ''` fallback → no .stl extension → 400."""
        file = _make_file()
        file.filename = None
        with pytest.raises(HTTPException) as exc_info:
            await _call(file=file)
        assert exc_info.value.status_code == 400
        assert "stl" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# STL validation
# ---------------------------------------------------------------------------

class TestStlValidation:
    async def test_stl_validation_error_raises_400(self):
        """STLValidationError from validate_stl → 400 with the error message."""
        from mesh.validator import STLValidationError

        mock_validate = MagicMock(side_effect=STLValidationError("corrupt STL"))
        with pytest.raises(HTTPException) as exc_info:
            await _call(mock_validate_stl=mock_validate)
        assert exc_info.value.status_code == 400
        assert "corrupt STL" in exc_info.value.detail

    async def test_validate_stl_called_with_content_and_max_size(self):
        """validate_stl must be called with the file content and max_size setting."""
        mock_validate = MagicMock()
        settings = _make_settings(max_stl_size_bytes=25 * 1024 * 1024)
        await _call(mock_validate_stl=mock_validate, settings=settings)

        mock_validate.assert_called_once_with(_MINIMAL_STL, max_size=25 * 1024 * 1024)


# ---------------------------------------------------------------------------
# Job limit enforcement
# ---------------------------------------------------------------------------

class TestJobLimitEnforcement:
    async def test_at_limit_raises_429(self):
        """active_count == max_jobs_per_user → 429."""
        settings = _make_settings(max_jobs_per_user=2)
        db = _make_db(active_count=2)
        with pytest.raises(HTTPException) as exc_info:
            await _call(db=db, settings=settings)
        assert exc_info.value.status_code == 429

    async def test_429_has_retry_after_header(self):
        settings = _make_settings(max_jobs_per_user=1)
        db = _make_db(active_count=1)
        with pytest.raises(HTTPException) as exc_info:
            await _call(db=db, settings=settings)
        assert "Retry-After" in exc_info.value.headers

    async def test_below_limit_proceeds(self):
        """active_count < max_jobs_per_user → upload proceeds."""
        settings = _make_settings(max_jobs_per_user=2, dev_mode=True)
        db = _make_db(active_count=1)
        result = await _call(db=db, settings=settings)
        assert result is not None


# ---------------------------------------------------------------------------
# Dev mode path
# ---------------------------------------------------------------------------

class TestDevModePath:
    async def test_returns_dev_mode_client_secret(self):
        """Dev mode must return client_secret='dev_mode'."""
        result = await _call(settings=_make_settings(dev_mode=True))
        assert result.client_secret == "dev_mode"

    async def test_dev_mode_amount_is_zero(self):
        result = await _call(settings=_make_settings(dev_mode=True))
        assert result.amount_cents == 0

    async def test_dev_mode_returns_job_id(self):
        result = await _call(settings=_make_settings(dev_mode=True))
        assert result.job_id  # non-empty UUID

    async def test_dev_mode_adds_background_task(self):
        """Background task must be added exactly once in dev mode."""
        bg = _make_background_tasks()
        await _call(background_tasks=bg, settings=_make_settings(dev_mode=True))
        bg.add_task.assert_called_once()

    async def test_dev_mode_writes_stl_to_disk(self, tmp_path):
        """STL content must be written to dev_storage_path in dev mode."""
        settings = _make_settings(dev_mode=True, dev_storage_path=str(tmp_path))
        result = await _call(settings=settings)
        stl_dir = tmp_path / "stl" / result.job_id
        stl_files = list(stl_dir.glob("*.stl"))
        assert len(stl_files) == 1

    async def test_dev_mode_saves_job_to_db(self):
        """Job must be added to and committed in the DB session."""
        db = _make_db(active_count=0)
        await _call(db=db, settings=_make_settings(dev_mode=True))
        db.add.assert_called_once()
        db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Prod mode path
# ---------------------------------------------------------------------------

class TestProdModePath:
    def _prod_settings(self):
        return _make_settings(dev_mode=False, mesh_price_cents=999)

    async def test_prod_mode_calls_upload_to_s3(self):
        """prod mode → _upload_to_s3 must be called with STL content."""
        with patch("api.upload._upload_to_s3") as mock_s3:
            result = await _call(settings=self._prod_settings())

        mock_s3.assert_called_once()
        call_args = mock_s3.call_args[0]
        assert call_args[0] == _MINIMAL_STL  # content

    async def test_prod_mode_returns_mesh_price(self):
        """prod mode → amount_cents must equal settings.mesh_price_cents."""
        with patch("api.upload._upload_to_s3"):
            result = await _call(settings=self._prod_settings())

        assert result.amount_cents == 999

    async def test_prod_mode_creates_stripe_payment_intent(self):
        """prod mode → stripe.PaymentIntent.create must be called."""
        stripe_stub = MagicMock()
        intent = MagicMock()
        intent.id = "pi_test"
        intent.client_secret = "pi_test_secret"
        stripe_stub.PaymentIntent.create.return_value = intent

        with patch("api.upload._upload_to_s3"):
            result = await _call(settings=self._prod_settings(), stripe_stub=stripe_stub)

        stripe_stub.PaymentIntent.create.assert_called_once()
        assert result.client_secret == "pi_test_secret"

    async def test_prod_mode_saves_job_to_db(self):
        """prod mode → job must be added and committed to DB."""
        db = _make_db(active_count=0)
        with patch("api.upload._upload_to_s3"):
            await _call(db=db, settings=self._prod_settings())
        db.add.assert_called_once()
        db.commit.assert_called_once()

    async def test_prod_mode_does_not_add_background_task(self):
        """prod mode → background task must NOT be added (mesh runs via Celery webhook)."""
        bg = _make_background_tasks()
        with patch("api.upload._upload_to_s3"):
            await _call(background_tasks=bg, settings=self._prod_settings())
        bg.add_task.assert_not_called()

    async def test_prod_mode_stl_key_contains_job_id(self):
        """S3 key must contain the job_id so objects are namespaced per job."""
        captured = {}

        def _capture_upload(content, key):
            captured["key"] = key

        with patch("api.upload._upload_to_s3", side_effect=_capture_upload):
            result = await _call(settings=self._prod_settings())

        assert result.job_id in captured["key"]


# ---------------------------------------------------------------------------
# Filename path-traversal stripping (upload.py line 106)
# ---------------------------------------------------------------------------

class TestFilenamePathStripping:
    """Path(filename).name strips directory components — security guard against
    filenames like '../../etc/passwd.stl' writing outside dev_storage_path."""

    async def test_path_traversal_filename_written_as_basename(self, tmp_path):
        """'../../etc/passwd.stl' → file stored as 'passwd.stl' inside dev_storage_path."""
        settings = _make_settings(dev_mode=True, dev_storage_path=str(tmp_path))
        result = await _call(
            file=_make_file(filename="../../etc/passwd.stl"),
            settings=settings,
        )
        stl_dir = tmp_path / "stl" / result.job_id
        assert (stl_dir / "passwd.stl").exists()

    async def test_nested_path_filename_written_as_basename(self, tmp_path):
        """'sub/dir/model.stl' → stored as 'model.stl', not under sub/dir/."""
        settings = _make_settings(dev_mode=True, dev_storage_path=str(tmp_path))
        result = await _call(
            file=_make_file(filename="sub/dir/model.stl"),
            settings=settings,
        )
        stl_dir = tmp_path / "stl" / result.job_id
        assert (stl_dir / "model.stl").exists()
        # The sub/dir/ path must NOT have been created
        assert not (stl_dir / "sub").exists()
