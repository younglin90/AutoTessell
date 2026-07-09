"""Unit tests for the web GUI server's new pure/mapping code and endpoints.

Covers:
- _build_run_kwargs  (payload → orchestrator.run kwargs mapping)
- desktop.default_env.apply_default_env  (setdefault semantics)
- static SPA mount  (GET "/" + assets)
- POST /jobs/{id}/cancel  and  GET /jobs/{id}/export  error paths

These complement tests/test_desktop_server.py (REST + WebSocket flow).
"""

from __future__ import annotations

import os

os.environ.setdefault("OPENFOAM_DIR", "/nonexistent")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from desktop.default_env import DEFAULT_ENV, apply_default_env  # noqa: E402
from desktop.server import _build_run_kwargs, _create_job, _jobs, app  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_jobs():
    _jobs.clear()
    yield
    _jobs.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# _build_run_kwargs — pure mapping function
# ---------------------------------------------------------------------------


class TestBuildRunKwargs:
    def test_quality_mesh_tier_passthrough(self):
        k = _build_run_kwargs("fine", "auto", "hex_dominant", 1, {})
        assert k["quality_level"] == "fine"
        assert k["mesh_type"] == "hex_dominant"
        assert k["tier_hint"] == "auto"
        assert k["write_of_case"] is True

    def test_max_cells_goes_to_kwarg_and_tsp(self):
        k = _build_run_kwargs("draft", "auto", "tet", 1, {"max_cells": "5000"})
        assert k["max_cells"] == 5000
        assert k["tier_specific_params"]["max_cells"] == 5000
        assert k["tier_specific_params"]["target_cells"] == 5000

    def test_bl_layers_maps_to_cfmesh_knob(self):
        k = _build_run_kwargs("standard", "auto", "hex_dominant", 1, {"bl_layers": "12"})
        tsp = k["tier_specific_params"]
        assert tsp["bl_layers"] == 12
        assert tsp["cfmesh_bl_n_layers"] == 12

    def test_element_size_kwarg_base_cell_size_tsp(self):
        k = _build_run_kwargs(
            "draft", "auto", "tet", 1, {"element_size": 0.5, "base_cell_size": 1.0}
        )
        assert k["element_size"] == 0.5
        assert "base_cell_size" not in k  # not a run() kwarg
        assert k["tier_specific_params"]["base_cell_size"] == 1.0

    def test_engine_auto_is_skipped(self):
        k = _build_run_kwargs("draft", "auto", "tet", 1, {"remesh_engine": "auto"})
        assert "remesh_engine" not in k

    def test_named_remesh_engine_included(self):
        k = _build_run_kwargs("draft", "auto", "tet", 1, {"remesh_engine": "pyacvd"})
        assert k["remesh_engine"] == "pyacvd"

    def test_checker_engine_maps_to_validator_engine(self):
        k = _build_run_kwargs("draft", "auto", "tet", 1, {"checker_engine": "openfoam"})
        assert k["validator_engine"] == "openfoam"

    def test_unknown_keys_merge_into_tsp(self):
        k = _build_run_kwargs("draft", "auto", "tet", 1, {"snappy_snap_iterations": 20})
        assert k["tier_specific_params"]["snappy_snap_iterations"] == 20

    def test_zero_and_empty_values_filtered(self):
        k = _build_run_kwargs(
            "draft", "auto", "tet", 1, {"max_cells": 0, "bl_layers": "", "element_size": 0}
        )
        assert "max_cells" not in k
        assert "element_size" not in k
        assert "tier_specific_params" not in k

    def test_auto_retry_off_at_one_iteration(self):
        assert _build_run_kwargs("draft", "auto", "tet", 1, {})["auto_retry"] == "off"

    def test_auto_retry_continue_when_multi_iteration(self):
        assert _build_run_kwargs("draft", "auto", "tet", 3, {})["auto_retry"] == "continue"

    def test_max_iterations_clamped_to_one(self):
        assert _build_run_kwargs("draft", "auto", "tet", -5, {})["max_iterations"] == 1

    def test_boolean_flags(self):
        k = _build_run_kwargs(
            "draft", "auto", "tet", 1,
            {"no_repair": True, "dry_run": True, "force_remesh": True, "allow_ai_fallback": True},
        )
        assert k["no_repair"] is True
        assert k["dry_run"] is True
        assert k["surface_remesh"] is True  # force_remesh → surface_remesh
        assert k["allow_ai_fallback"] is True

    def test_none_extra_does_not_crash(self):
        k = _build_run_kwargs("draft", "auto", "tet", 1, None)
        assert k["quality_level"] == "draft"


# ---------------------------------------------------------------------------
# default_env — shared knobs
# ---------------------------------------------------------------------------


class TestDefaultEnv:
    def test_all_values_are_strings(self):
        assert all(isinstance(v, str) for v in DEFAULT_ENV.values())

    def test_setdefault_respects_existing_value(self, monkeypatch):
        monkeypatch.setenv("AUTO_TESSELL_STELLAR_KLINGNER", "0")
        apply_default_env()
        assert os.environ["AUTO_TESSELL_STELLAR_KLINGNER"] == "0"

    def test_sets_missing_value(self, monkeypatch):
        monkeypatch.delenv("AUTO_TESSELL_POLY_BACKEND", raising=False)
        apply_default_env()
        assert os.environ["AUTO_TESSELL_POLY_BACKEND"] == DEFAULT_ENV["AUTO_TESSELL_POLY_BACKEND"]


# ---------------------------------------------------------------------------
# Static SPA mount
# ---------------------------------------------------------------------------


class TestStaticMount:
    def test_index_html_served_at_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        # Electron redesign rebranded the title to "AutoTessell" and added ui.js.
        assert "AutoTessell" in r.text
        assert "ui.js" in r.text

    def test_spa_assets_served(self, client):
        for path, needle in [
            ("/app.js", "MeshViewer"),
            ("/viewer.js", "MeshViewer"),
            ("/styles.css", "--accent"),
        ]:
            r = client.get(path)
            assert r.status_code == 200, path
            assert needle in r.text, path


# ---------------------------------------------------------------------------
# Cancel endpoint
# ---------------------------------------------------------------------------


class TestCancelEndpoint:
    def test_unknown_job_returns_404(self, client):
        assert client.post("/jobs/nonexistent/cancel").status_code == 404

    def test_cancel_sets_event(self, client):
        job = _create_job("x.stl")
        r = client.post(f"/jobs/{job['id']}/cancel")
        assert r.status_code == 200
        assert job["cancel_event"].is_set()


# ---------------------------------------------------------------------------
# Export endpoint (error paths — success path covered by the e2e smoke)
# ---------------------------------------------------------------------------


class TestExportEndpoint:
    def test_unknown_job_returns_404(self, client):
        assert client.get("/jobs/nonexistent/export?format=vtu").status_code == 404

    def test_unsupported_format_returns_400(self, client):
        job = _create_job("x.stl")
        r = client.get(f"/jobs/{job['id']}/export?format=zzz")
        assert r.status_code == 400

    def test_no_mesh_returns_404(self, client):
        job = _create_job("x.stl")  # work dir exists but no polyMesh yet
        r = client.get(f"/jobs/{job['id']}/export?format=vtu")
        assert r.status_code == 404
