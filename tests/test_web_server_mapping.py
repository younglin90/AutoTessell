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
from desktop.server import (  # noqa: E402
    _build_run_kwargs,
    _create_job,
    _jobs,
    _ThreadScopedLogHandler,
    app,
)


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

    def test_zero_bl_layers_is_preserved_as_explicit_disable(self):
        k = _build_run_kwargs("standard", "auto", "hex_dominant", 1, {"bl_layers": 0})
        tsp = k["tier_specific_params"]
        assert tsp["bl_layers"] == 0
        assert tsp["cfmesh_bl_n_layers"] == 0

    @pytest.mark.parametrize("value", [-1, "-1", "invalid", None])
    def test_negative_or_invalid_bl_layers_are_omitted(self, value):
        k = _build_run_kwargs("standard", "auto", "hex_dominant", 1, {"bl_layers": value})
        assert "tier_specific_params" not in k

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
            ("/styles.css", "--orange"),  # blueprint design token
        ]:
            r = client.get(path)
            assert r.status_code == 200, path
            assert needle in r.text, path

    def test_static_assets_are_no_cache(self, client):
        # Live UI edits must always show on reload (local desktop tool).
        r = client.get("/styles.css")
        assert "no-store" in r.headers.get("cache-control", "")


# ---------------------------------------------------------------------------
# Demo data endpoints
# ---------------------------------------------------------------------------


class TestDemoEndpoints:
    def test_list_demos_returns_available(self, client):
        r = client.get("/demos")
        assert r.status_code == 200
        demos = r.json()["demos"]
        # At least the cube ships with the repo; each item is client-consumable.
        keys = {d["key"] for d in demos}
        assert "cube" in keys
        for d in demos:
            assert d["label"] and d["name"] and "key" in d

    def test_get_demo_returns_file_bytes(self, client):
        r = client.get("/demos/cube")
        assert r.status_code == 200
        assert r.content.startswith(b"solid") or len(r.content) > 0
        assert "demo_cube.stl" in r.headers.get("content-disposition", "")

    def test_unknown_demo_returns_404(self, client):
        assert client.get("/demos/nope").status_code == 404


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


class TestMeshInternalFaces:
    """GET /jobs/{id}/mesh?internal=1 must return interior faces for the slice
    viewer.  OpenFOAM orders faces [interior .. boundary]; nInternalFaces equals
    the neighbour-list length."""

    def _write_polymesh(self, job):
        from pathlib import Path

        poly = Path(job["work_dir"]) / "case" / "constant" / "polyMesh"
        poly.mkdir(parents=True, exist_ok=True)
        # 5 points, 3 faces: face0 interior, faces 1-2 boundary (one patch).
        (poly / "points").write_text(
            "5\n(\n(0 0 0)\n(1 0 0)\n(1 1 0)\n(0 1 0)\n(1 1 1)\n)\n"
        )
        (poly / "faces").write_text(
            "3\n(\n3(0 1 2)\n3(0 1 3)\n3(1 2 4)\n)\n"
        )
        (poly / "owner").write_text("3\n(\n0\n0\n1\n)\n")
        (poly / "neighbour").write_text("1\n(\n1\n)\n")  # 1 interior face
        (poly / "boundary").write_text(
            "1\n(\n    walls { type wall; nFaces 2; startFace 1; }\n)\n"
        )

    def test_internal_faces_returned_when_requested(self, client):
        job = _create_job("x.stl")
        self._write_polymesh(job)
        r = client.get(f"/jobs/{job['id']}/mesh?internal=1")
        assert r.status_code == 200, r.text
        j = r.json()
        # interior face count == neighbour length (1); boundary faces == 2
        assert j.get("internal_available") is True
        assert len(j["internal_faces"]) == 1
        assert j["internal_faces"][0] == [0, 1, 2]
        assert len(j["boundary_faces"]) == 2

    def test_internal_faces_omitted_by_default(self, client):
        job = _create_job("x.stl")
        self._write_polymesh(job)
        j = client.get(f"/jobs/{job['id']}/mesh").json()
        assert "internal_faces" not in j
        assert len(j["boundary_faces"]) == 2

    def test_stats_counts_and_shapes(self, client):
        job = _create_job("x.stl")
        self._write_polymesh(job)
        j = client.get(f"/jobs/{job['id']}/mesh?quality=1").json()
        s = j.get("stats")
        assert s, j.get("error")
        assert s["n_points"] == 5
        assert s["n_faces"] == 3
        assert s["n_cells"] == 2
        # all 3 faces are triangles
        assert s["face_shapes"] == {"tri": 3, "quad": 0, "poly": 0}
        # neither cell has a full tet signature (only 2 faces each) → poly
        assert s["cell_shapes"]["poly"] == 2
        # histograms present with min <= max and 14 bins
        for key in ("non_ortho", "skewness"):
            h = s[key]
            assert h is None or (
                h["min"] <= h["max"] and len(h["counts"]) == 14
            )

    def test_stats_absent_without_quality(self, client):
        job = _create_job("x.stl")
        self._write_polymesh(job)
        j = client.get(f"/jobs/{job['id']}/mesh").json()
        assert "stats" not in j

    def test_crinkle_data_present_with_internal(self, client):
        # cell centroids + per-face cell ids for the crinkle slice
        job = _create_job("x.stl")
        self._write_polymesh(job)
        j = client.get(f"/jobs/{job['id']}/mesh?internal=1").json()
        assert len(j["cell_centroids"]) == j["num_cells"] == 2
        # boundary faces: 2, each owned by a cell (0 or 1)
        assert len(j["boundary_cells"]) == len(j["boundary_faces"]) == 2
        # 1 interior face straddling cells 0 and 1
        assert j["internal_owner"] == [0]
        assert j["internal_neighbour"] == [1]


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


# ---------------------------------------------------------------------------
# _ThreadScopedLogHandler — GUI detail-log streaming
# ---------------------------------------------------------------------------


class TestThreadScopedLogHandler:
    """The handler must forward ONLY records from its own worker thread —
    this is what keeps two concurrent jobs' detail logs from crossing over
    (each job's ``run_in_executor`` callable runs start-to-finish on one OS
    thread; contextvars don't propagate into it, so thread-id is the seam)."""

    def _record(self, logger_name="core.x", msg="event", level=20, thread=1):
        import logging
        r = logging.LogRecord(logger_name, level, __file__, 1, msg, (), None)
        r.thread = thread
        return r

    def test_forwards_only_matching_thread(self):
        box: dict = {"id": 111}
        sunk: list = []
        h = _ThreadScopedLogHandler(box, sunk.append)
        h.emit(self._record(thread=111))
        h.emit(self._record(thread=222))  # different thread → dropped
        assert len(sunk) == 1

    def test_drops_everything_before_thread_id_is_set(self):
        box: dict = {"id": None}
        sunk: list = []
        h = _ThreadScopedLogHandler(box, sunk.append)
        h.emit(self._record(thread=111))
        assert sunk == []

    def test_level_mapping_and_prefix(self):
        box: dict = {"id": 5}
        sunk: list = []
        h = _ThreadScopedLogHandler(box, sunk.append)
        for lvl, expect in [(10, "debug"), (20, "info"), (30, "warn"), (40, "error"), (50, "error")]:
            h.emit(self._record(level=lvl, thread=5))
        levels = [p["level"] for p in sunk]
        assert levels == ["debug", "info", "warn", "error", "error"]
        assert all(p["message"].startswith("[Engine] ") for p in sunk)
        assert all(p["type"] == "log" for p in sunk)

    def test_bad_record_does_not_raise(self):
        # a broken formatter must not kill the emitting thread — falls back
        # to record.getMessage().
        box: dict = {"id": 1}
        sunk: list = []
        h = _ThreadScopedLogHandler(box, sunk.append)

        class _BadFormatter:
            def format(self, record):
                raise ValueError("boom")

        h.formatter = _BadFormatter()
        h.emit(self._record(thread=1, msg="fallback message"))
        assert sunk and "fallback message" in sunk[0]["message"]
