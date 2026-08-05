"""
Unit tests for the serve_dev_file route handler (main.py).

The handler is registered at module load time only when settings.dev_mode=True.
In the test environment the pydantic_settings stub defaults dev_mode=False, so
serve_dev_file is not in main's namespace.  We test the handler by extracting
it from the app's route table after patching settings.

Branches covered:
  1. Path traversal attempt (../../etc/passwd)    → 400
  2. Path that resolves outside storage root       → 400
  3. Valid path but file does not exist            → 404
  4. Multi-segment path that doesn't exist        → 404
  5. Valid file inside storage root               → FileResponse
  6. FileResponse filename equals the file's name
  7. File at root of storage dir                  → allowed
"""

import sys
import importlib

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Extract serve_dev_file from the app with dev_mode patched to True
# ---------------------------------------------------------------------------

def _get_serve_dev_file():
    """
    Force-reload main.py with settings.dev_mode=True so that serve_dev_file
    is registered, then extract the underlying callable from the route table.
    """
    import config

    # Temporarily set dev_mode=True on the settings singleton
    orig_dev_mode = config.settings.dev_mode
    config.settings.dev_mode = True

    # Remove any cached import of main so the if-block re-evaluates
    sys.modules.pop("main", None)

    try:
        import main as _main  # re-imports with dev_mode=True now set
        # Locate the route by path pattern
        for route in _main.app.routes:
            if hasattr(route, "path") and route.path == "/dev/files/{path:path}":
                return route.endpoint
        raise RuntimeError("serve_dev_file route not found in app.routes")
    finally:
        config.settings.dev_mode = orig_dev_mode
        # Keep the reloaded main in sys.modules for the rest of the test run
        # (other tests won't be affected — they never import serve_dev_file)


_serve_dev_file = _get_serve_dev_file()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _call(path: str, storage_root: str):
    mock_settings = MagicMock()
    mock_settings.dev_storage_path = storage_root
    with patch("main.settings", mock_settings):
        return _serve_dev_file(path)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestServeDevFile:

    # ------------------------------------------------------------------
    # Path traversal guard → 400
    # ------------------------------------------------------------------

    def test_path_traversal_raises_400(self, tmp_path):
        """../../etc/passwd must not escape storage_root → 400."""
        with pytest.raises(HTTPException) as exc_info:
            _call("../../etc/passwd", str(tmp_path))
        assert exc_info.value.status_code == 400
        assert "path" in exc_info.value.detail.lower()

    def test_traversal_to_sibling_dir_raises_400(self, tmp_path):
        """Path that resolves outside storage_root must raise 400."""
        sibling = tmp_path.parent / "sibling_escape"
        sibling.mkdir(exist_ok=True)
        (sibling / "secret.txt").write_text("secret")
        with pytest.raises(HTTPException) as exc_info:
            _call("../sibling_escape/secret.txt", str(tmp_path))
        assert exc_info.value.status_code == 400

    # ------------------------------------------------------------------
    # File not found → 404
    # ------------------------------------------------------------------

    def test_missing_file_raises_404(self, tmp_path):
        """Valid path inside storage_root but file does not exist → 404."""
        with pytest.raises(HTTPException) as exc_info:
            _call("meshes/job-1/mesh.zip", str(tmp_path))
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    def test_missing_nested_path_raises_404(self, tmp_path):
        """Multi-segment path that doesn't exist → 404."""
        with pytest.raises(HTTPException) as exc_info:
            _call("stl/abc/model.stl", str(tmp_path))
        assert exc_info.value.status_code == 404

    # ------------------------------------------------------------------
    # Happy path → FileResponse
    # ------------------------------------------------------------------

    def test_existing_file_returns_file_response(self, tmp_path):
        """File that exists inside storage_root → FileResponse."""
        mesh_dir = tmp_path / "meshes" / "job-1"
        mesh_dir.mkdir(parents=True)
        (mesh_dir / "mesh.zip").write_bytes(b"fake-zip")

        result = _call("meshes/job-1/mesh.zip", str(tmp_path))
        assert isinstance(result, FileResponse)

    def test_file_response_uses_correct_filename(self, tmp_path):
        """FileResponse.filename must be the file's basename."""
        stl_dir = tmp_path / "stl" / "job-2"
        stl_dir.mkdir(parents=True)
        (stl_dir / "model.stl").write_bytes(b"solid...")

        result = _call("stl/job-2/model.stl", str(tmp_path))
        assert result.filename == "model.stl"

    def test_file_at_root_of_storage_dir_allowed(self, tmp_path):
        """A file directly at storage_root depth-0 is inside root → allowed."""
        (tmp_path / "readme.txt").write_text("hello")
        result = _call("readme.txt", str(tmp_path))
        assert isinstance(result, FileResponse)
