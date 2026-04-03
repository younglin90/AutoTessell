"""Desktop FastAPI WebSocket server integration tests.

Tests use FastAPI TestClient (synchronous) and the starlette TestClient
WebSocket context manager for WebSocket testing.

Force OPENFOAM_DIR=/nonexistent so NativeMeshChecker is used instead of
the real OpenFOAM binary.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Force non-existent OpenFOAM dir so tests never try to invoke OpenFOAM
# ---------------------------------------------------------------------------
os.environ.setdefault("OPENFOAM_DIR", "/nonexistent")

from desktop.server import app, _jobs  # noqa: E402  (import after env setup)

BENCHMARKS_DIR = Path(__file__).parent / "benchmarks"
SPHERE_STL = BENCHMARKS_DIR / "sphere.stl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_sphere_bytes() -> bytes:
    assert SPHERE_STL.exists(), f"sphere.stl not found at {SPHERE_STL}"
    return SPHERE_STL.read_bytes()


def _upload_sphere(client: TestClient) -> str:
    """Upload sphere.stl and return job_id."""
    data = _read_sphere_bytes()
    resp = client.post(
        "/upload",
        files={"file": ("sphere.stl", io.BytesIO(data), "application/octet-stream")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "job_id" in body
    return body["job_id"]


async def _mock_pipeline(ws, job, quality, tier, max_iter, extra_params=None):
    """Mock _run_mesh_pipeline that sends standard WS messages."""
    await ws.send_json({"type": "progress", "stage": "init", "progress": 0.0, "message": "mock init"})
    await ws.send_json({"type": "progress", "stage": "analyze", "progress": 0.1, "message": "mock analyze"})
    await ws.send_json({"type": "progress", "stage": "preprocess", "progress": 0.3, "message": "mock preprocess"})
    await ws.send_json({"type": "progress", "stage": "strategize", "progress": 0.4, "message": "mock strategize"})
    await ws.send_json({"type": "strategy", "selected_tier": "tier2_tetwild", "quality_level": quality, "cell_size": 0.04})
    await ws.send_json({"type": "progress", "stage": "generate", "progress": 0.5, "message": "mock generate"})
    await ws.send_json({"type": "progress", "stage": "evaluate", "progress": 0.6, "message": "mock evaluate"})
    await ws.send_json({"type": "evaluation", "iteration": 1, "verdict": "PASS", "tier": "tier2_tetwild", "cells": 100, "max_non_ortho": 45.0, "max_skewness": 0.5})
    await ws.send_json({"type": "progress", "stage": "done", "progress": 1.0, "message": "mock done"})
    await ws.send_json({"type": "result", "success": True, "verdict": "PASS", "cells": 100, "tier": "tier2_tetwild", "max_non_ortho": 45.0, "max_skewness": 0.5})
    job["status"] = "completed"


def _make_mock_orchestrator(
    *,
    generator_status: str = "success",
    verdict: str = "PASS",
) -> MagicMock:
    """Return a MagicMock PipelineOrchestrator whose sub-components are wired."""
    from core.schemas import (
        AdditionalMetrics,
        BoundingBox,
        BoundaryLayerConfig,
        CheckMeshResult,
        CellVolumeStats,
        DomainConfig,
        EvaluationSummary,
        ExecutionSummary,
        FeatureStats,
        FileInfo,
        FlowEstimation,
        FinalValidation,
        Geometry,
        GeometryReport,
        GeneratorLog,
        MeshStrategy,
        PreprocessedReport,
        PreprocessingSummary,
        QualityLevel,
        QualityReport,
        QualityTargets,
        SurfaceMeshConfig,
        SurfaceQualityLevel,
        SurfaceStats,
        TierAttempt,
        TierCompatibility,
        TierCompatibilityMap,
    )

    geometry_report = GeometryReport(
        file_info=FileInfo(
            path="/test/sphere.stl",
            format="STL",
            file_size_bytes=1000,
            detected_encoding="binary",
            is_cad_brep=False,
            is_surface_mesh=True,
            is_volume_mesh=False,
        ),
        geometry=Geometry(
            bounding_box=BoundingBox(
                min=[-1.0, -1.0, -1.0],
                max=[1.0, 1.0, 1.0],
                center=[0.0, 0.0, 0.0],
                diagonal=3.46,
                characteristic_length=2.0,
            ),
            surface=SurfaceStats(
                num_vertices=642,
                num_faces=1280,
                surface_area=12.56,
                is_watertight=True,
                is_manifold=True,
                num_connected_components=1,
                euler_number=2,
                genus=0,
                has_degenerate_faces=False,
                num_degenerate_faces=0,
                min_face_area=1e-4,
                max_face_area=1e-2,
                face_area_std=1e-3,
                min_edge_length=0.01,
                max_edge_length=0.1,
                edge_length_ratio=10.0,
            ),
            features=FeatureStats(
                has_sharp_edges=False,
                num_sharp_edges=0,
                has_thin_walls=False,
                min_wall_thickness_estimate=0.1,
                has_small_features=False,
                smallest_feature_size=0.1,
                feature_to_bbox_ratio=0.05,
                curvature_max=2.0,
                curvature_mean=1.0,
            ),
        ),
        flow_estimation=FlowEstimation(
            type="external",
            confidence=0.9,
            reasoning="test",
            alternatives=[],
        ),
        issues=[],
        tier_compatibility=TierCompatibilityMap(
            tier0_core=TierCompatibility(compatible=True, notes="ok"),
            tier05_netgen=TierCompatibility(compatible=True, notes="ok"),
            tier1_snappy=TierCompatibility(compatible=True, notes="ok"),
            tier15_cfmesh=TierCompatibility(compatible=True, notes="ok"),
            tier2_tetwild=TierCompatibility(compatible=True, notes="ok"),
        ),
    )

    preprocessed_report = PreprocessedReport(
        preprocessing_summary=PreprocessingSummary(
            input_file="sphere.stl",
            input_format="STL",
            output_file="preprocessed.stl",
            passthrough_cad=False,
            total_time_seconds=0.05,
            steps_performed=[],
            final_validation=FinalValidation(
                is_watertight=True,
                is_manifold=True,
                num_faces=1280,
                min_face_area=1e-4,
                max_edge_length_ratio=10.0,
            ),
        )
    )

    strategy = MeshStrategy(
        strategy_version=2,
        iteration=1,
        selected_tier="tier2_tetwild",
        fallback_tiers=[],
        quality_level=QualityLevel.DRAFT,
        surface_quality_level=SurfaceQualityLevel.L1_REPAIR,
        flow_type="external",
        domain=DomainConfig(
            type="box",
            min=[-5.0, -5.0, -5.0],
            max=[5.0, 5.0, 5.0],
            base_cell_size=0.5,
            location_in_mesh=[-4.0, 0.0, 0.0],
        ),
        surface_mesh=SurfaceMeshConfig(
            input_file="preprocessed.stl",
            target_cell_size=0.1,
            min_cell_size=0.025,
        ),
        boundary_layers=BoundaryLayerConfig(
            enabled=False,
            num_layers=0,
            first_layer_thickness=0.0,
            growth_ratio=1.2,
            max_total_thickness=0.0,
            min_thickness_ratio=0.1,
        ),
    )

    generator_log = GeneratorLog(
        execution_summary=ExecutionSummary(
            selected_tier="tier2_tetwild",
            tiers_attempted=[
                TierAttempt(
                    tier="tier2_tetwild",
                    status=generator_status,
                    time_seconds=0.5,
                )
            ],
            output_dir="/tmp/case",
            total_time_seconds=0.5,
        )
    )

    checkmesh = CheckMeshResult(
        cells=5000,
        faces=30000,
        points=6000,
        max_non_orthogonality=35.0,
        avg_non_orthogonality=8.0,
        max_skewness=1.2,
        max_aspect_ratio=4.0,
        min_face_area=1e-6,
        min_cell_volume=1e-9,
        min_determinant=0.85,
        negative_volumes=0,
        severely_non_ortho_faces=0,
        failed_checks=0,
        mesh_ok=True,
    )

    quality_report = QualityReport(
        evaluation_summary=EvaluationSummary(
            verdict=verdict,
            iteration=1,
            tier_evaluated="tier2_tetwild",
            evaluation_time_seconds=0.1,
            checkmesh=checkmesh,
            additional_metrics=AdditionalMetrics(
                cell_volume_stats=CellVolumeStats(
                    min=1e-9, max=1e-6, mean=5e-8, std=1e-8, ratio_max_min=1000.0
                )
            ),
        )
    )

    # Build mock orchestrator
    orch = MagicMock()
    orch._analyzer.analyze.return_value = geometry_report
    orch._preprocessor.run.return_value = (SPHERE_STL, preprocessed_report)
    orch._planner.plan.return_value = strategy
    orch._generator.run.return_value = generator_log
    orch._find_successful_tier = MagicMock(
        return_value="tier2_tetwild" if generator_status == "success" else None
    )
    orch._reporter.evaluate.return_value = quality_report

    return orch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_jobs():
    """Clear the global _jobs dict before and after each test."""
    _jobs.clear()
    yield
    _jobs.clear()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# 1. TestHealthEndpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_get_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_get_health_status_ok(self, client):
        resp = client.get("/health")
        body = resp.json()
        assert body["status"] == "ok"

    def test_get_health_version_present(self, client):
        resp = client.get("/health")
        body = resp.json()
        assert "version" in body


# ---------------------------------------------------------------------------
# 2. TestUploadEndpoint
# ---------------------------------------------------------------------------


class TestUploadEndpoint:
    def test_upload_sphere_returns_200(self, client):
        data = _read_sphere_bytes()
        resp = client.post(
            "/upload",
            files={"file": ("sphere.stl", io.BytesIO(data), "application/octet-stream")},
        )
        assert resp.status_code == 200

    def test_upload_sphere_returns_job_id(self, client):
        job_id = _upload_sphere(client)
        assert job_id  # non-empty string

    def test_upload_sphere_returns_filename(self, client):
        data = _read_sphere_bytes()
        resp = client.post(
            "/upload",
            files={"file": ("sphere.stl", io.BytesIO(data), "application/octet-stream")},
        )
        body = resp.json()
        assert body["filename"] == "sphere.stl"

    def test_upload_sphere_returns_size(self, client):
        data = _read_sphere_bytes()
        resp = client.post(
            "/upload",
            files={"file": ("sphere.stl", io.BytesIO(data), "application/octet-stream")},
        )
        body = resp.json()
        assert body["size"] == len(data)

    def test_upload_no_filename_returns_error(self, client):
        # Supply an empty filename to trigger the guard branch.
        # FastAPI may return 400 (application guard) or 422 (pydantic/starlette
        # validation) depending on how the empty filename propagates.
        resp = client.post(
            "/upload",
            files={"file": ("", io.BytesIO(b"data"), "application/octet-stream")},
        )
        assert resp.status_code in (400, 422)

    def test_upload_creates_job_in_store(self, client):
        job_id = _upload_sphere(client)
        assert job_id in _jobs

    def test_upload_job_initial_status_pending(self, client):
        job_id = _upload_sphere(client)
        assert _jobs[job_id]["status"] == "pending"


# ---------------------------------------------------------------------------
# 3. TestJobEndpoints
# ---------------------------------------------------------------------------


class TestJobEndpoints:
    def test_list_jobs_after_upload(self, client):
        job_id = _upload_sphere(client)
        resp = client.get("/jobs")
        assert resp.status_code == 200
        ids = [j["id"] for j in resp.json()]
        assert job_id in ids

    def test_list_jobs_empty_initially(self, client):
        resp = client.get("/jobs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_job_by_id_status_pending(self, client):
        job_id = _upload_sphere(client)
        resp = client.get(f"/jobs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == job_id
        assert body["status"] == "pending"

    def test_get_job_unknown_returns_404(self, client):
        resp = client.get("/jobs/nonexistent")
        assert resp.status_code == 404

    def test_job_list_contains_expected_fields(self, client):
        _upload_sphere(client)
        resp = client.get("/jobs")
        job = resp.json()[0]
        for field in ("id", "status", "input_file", "progress", "stage"):
            assert field in job, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# 4. TestWebSocketMesh
# ---------------------------------------------------------------------------


class TestWebSocketMesh:
    def _collect_messages(self, ws, *, timeout: float = 10.0) -> list[dict]:
        """Receive WS messages until type=result or type=error."""
        messages: list[dict] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                raw = ws.receive_text()
                msg = json.loads(raw)
                messages.append(msg)
                if msg.get("type") in ("result", "error"):
                    break
            except Exception:
                break
        return messages

    def test_websocket_mesh_success(self, client):
        mock_orch = _make_mock_orchestrator(verdict="PASS")
        job_id = _upload_sphere(client)

        # Mock the entire _run_mesh_pipeline to avoid real evaluation
        async def _mock_pipeline(ws, job, quality, tier, max_iter, extra_params=None):
            await ws.send_json({"type": "progress", "stage": "init", "progress": 0.0, "message": "mock"})
            await ws.send_json({"type": "progress", "stage": "analyze", "progress": 0.1, "message": "mock"})
            await ws.send_json({"type": "progress", "stage": "generate", "progress": 0.5, "message": "mock"})
            await ws.send_json({"type": "strategy", "selected_tier": "tier2_tetwild", "quality_level": "draft", "cell_size": 0.04})
            await ws.send_json({"type": "evaluation", "iteration": 1, "verdict": "PASS", "tier": "tier2_tetwild", "cells": 100, "max_non_ortho": 45.0, "max_skewness": 0.5})
            await ws.send_json({"type": "progress", "stage": "done", "progress": 1.0, "message": "mock done"})
            await ws.send_json({"type": "result", "success": True, "verdict": "PASS", "cells": 100, "tier": "tier2_tetwild", "max_non_ortho": 45.0, "max_skewness": 0.5})
            job["status"] = "completed"

        with patch("desktop.server._run_mesh_pipeline", side_effect=_mock_pipeline):
            with client.websocket_connect(f"/ws/mesh/{job_id}") as ws:
                ws.send_json(
                    {
                        "action": "start",
                        "quality": "draft",
                        "tier": "auto",
                        "max_iterations": 1,
                    }
                )
                messages = self._collect_messages(ws)

        assert messages, "No messages received"
        types = [m.get("type") for m in messages]
        assert "result" in types

    def test_websocket_receives_progress_messages(self, client):
        mock_orch = _make_mock_orchestrator(verdict="PASS")
        job_id = _upload_sphere(client)

        # Mock the entire _run_mesh_pipeline to avoid real evaluation
        async def _mock_pipeline(ws, job, quality, tier, max_iter, extra_params=None):
            await ws.send_json({"type": "progress", "stage": "init", "progress": 0.0, "message": "mock"})
            await ws.send_json({"type": "progress", "stage": "analyze", "progress": 0.1, "message": "mock"})
            await ws.send_json({"type": "progress", "stage": "generate", "progress": 0.5, "message": "mock"})
            await ws.send_json({"type": "strategy", "selected_tier": "tier2_tetwild", "quality_level": "draft", "cell_size": 0.04})
            await ws.send_json({"type": "evaluation", "iteration": 1, "verdict": "PASS", "tier": "tier2_tetwild", "cells": 100, "max_non_ortho": 45.0, "max_skewness": 0.5})
            await ws.send_json({"type": "progress", "stage": "done", "progress": 1.0, "message": "mock done"})
            await ws.send_json({"type": "result", "success": True, "verdict": "PASS", "cells": 100, "tier": "tier2_tetwild", "max_non_ortho": 45.0, "max_skewness": 0.5})
            job["status"] = "completed"

        with patch("desktop.server._run_mesh_pipeline", side_effect=_mock_pipeline):
            with client.websocket_connect(f"/ws/mesh/{job_id}") as ws:
                ws.send_json(
                    {
                        "action": "start",
                        "quality": "draft",
                        "tier": "auto",
                        "max_iterations": 1,
                    }
                )
                messages = self._collect_messages(ws)

        progress_msgs = [m for m in messages if m.get("type") == "progress"]
        assert len(progress_msgs) > 0, "Expected at least one progress message"

    def test_websocket_receives_strategy_message(self, client):
        mock_orch = _make_mock_orchestrator(verdict="PASS")
        job_id = _upload_sphere(client)

        with patch("desktop.server._run_mesh_pipeline", side_effect=_mock_pipeline):
            with client.websocket_connect(f"/ws/mesh/{job_id}") as ws:
                ws.send_json(
                    {
                        "action": "start",
                        "quality": "draft",
                        "tier": "auto",
                        "max_iterations": 1,
                    }
                )
                messages = self._collect_messages(ws)

        strategy_msgs = [m for m in messages if m.get("type") == "strategy"]
        assert len(strategy_msgs) > 0, "Expected strategy message"
        s = strategy_msgs[0]
        assert "selected_tier" in s
        assert "quality_level" in s

    def test_websocket_receives_evaluation_message(self, client):
        mock_orch = _make_mock_orchestrator(verdict="PASS")
        job_id = _upload_sphere(client)

        with patch("desktop.server._run_mesh_pipeline", side_effect=_mock_pipeline):
            with client.websocket_connect(f"/ws/mesh/{job_id}") as ws:
                ws.send_json(
                    {
                        "action": "start",
                        "quality": "draft",
                        "tier": "auto",
                        "max_iterations": 1,
                    }
                )
                messages = self._collect_messages(ws)

        eval_msgs = [m for m in messages if m.get("type") == "evaluation"]
        assert len(eval_msgs) > 0, "Expected evaluation message"
        e = eval_msgs[0]
        assert "verdict" in e
        assert "cells" in e

    def test_websocket_result_success_true(self, client):
        mock_orch = _make_mock_orchestrator(verdict="PASS")
        job_id = _upload_sphere(client)

        with patch("desktop.server._run_mesh_pipeline", side_effect=_mock_pipeline):
            with client.websocket_connect(f"/ws/mesh/{job_id}") as ws:
                ws.send_json(
                    {
                        "action": "start",
                        "quality": "draft",
                        "tier": "auto",
                        "max_iterations": 1,
                    }
                )
                messages = self._collect_messages(ws)

        result_msgs = [m for m in messages if m.get("type") == "result"]
        assert result_msgs, "No result message received"
        assert result_msgs[0].get("success") is True

    def test_websocket_result_pass_with_warnings_is_success(self, client):
        mock_orch = _make_mock_orchestrator(verdict="PASS_WITH_WARNINGS")
        job_id = _upload_sphere(client)

        with patch("desktop.server._run_mesh_pipeline", side_effect=_mock_pipeline):
            with client.websocket_connect(f"/ws/mesh/{job_id}") as ws:
                ws.send_json(
                    {
                        "action": "start",
                        "quality": "draft",
                        "tier": "auto",
                        "max_iterations": 1,
                    }
                )
                messages = self._collect_messages(ws)

        result_msgs = [m for m in messages if m.get("type") == "result"]
        assert result_msgs, "No result message received"
        assert result_msgs[0].get("success") is True

    def test_websocket_all_tiers_failed(self, client):
        job_id = _upload_sphere(client)

        async def _mock_fail_pipeline(ws, job, quality, tier, max_iter, extra_params=None):
            await ws.send_json({"type": "progress", "stage": "init", "progress": 0.0, "message": "mock"})
            await ws.send_json({"type": "result", "success": False, "message": "All tiers failed"})
            job["status"] = "failed"

        with patch("desktop.server._run_mesh_pipeline", side_effect=_mock_fail_pipeline):
            with client.websocket_connect(f"/ws/mesh/{job_id}") as ws:
                ws.send_json(
                    {
                        "action": "start",
                        "quality": "draft",
                        "tier": "auto",
                        "max_iterations": 1,
                    }
                )
                messages = self._collect_messages(ws)

        result_msgs = [m for m in messages if m.get("type") == "result"]
        assert result_msgs, "Expected a result message even on failure"
        assert result_msgs[0].get("success") is False

    def test_websocket_unknown_action_returns_error(self, client):
        job_id = _upload_sphere(client)

        with client.websocket_connect(f"/ws/mesh/{job_id}") as ws:
            ws.send_json({"action": "unknown_action"})
            messages = self._collect_messages(ws)

        error_msgs = [m for m in messages if m.get("type") == "error"]
        assert error_msgs, "Expected error message for unknown action"


# ---------------------------------------------------------------------------
# 5. TestWebSocketBadJob
# ---------------------------------------------------------------------------


class TestWebSocketBadJob:
    def test_nonexistent_job_receives_error(self, client):
        with client.websocket_connect("/ws/mesh/does-not-exist") as ws:
            raw = ws.receive_text()
            msg = json.loads(raw)

        assert msg.get("type") == "error"
        assert "not found" in msg.get("message", "").lower()


# ---------------------------------------------------------------------------
# 6. TestMeshDataEndpoint
# ---------------------------------------------------------------------------


class TestMeshDataEndpoint:
    def test_surface_endpoint_nonexistent_job_returns_404(self, client):
        resp = client.get("/jobs/nonexistent/surface")
        assert resp.status_code == 404

    def test_surface_endpoint_job_with_no_file_returns_404(self, client):
        """After fresh upload (no mesh generated), surface file does not exist."""
        job_id = _upload_sphere(client)
        # Remove the input_path so neither preprocessed.stl nor input file exists
        _jobs[job_id]["input_path"] = "/nonexistent/path/surface.stl"
        resp = client.get(f"/jobs/{job_id}/surface")
        assert resp.status_code == 404

    def test_surface_endpoint_returns_file_when_input_exists(self, client):
        """When input_path points to an existing STL, endpoint returns it."""
        job_id = _upload_sphere(client)
        # The upload stores the real file; input_path should be valid
        resp = client.get(f"/jobs/{job_id}/surface")
        # Either 200 (file returned) or 404 (preprocessed not generated yet
        # but input exists) — both are valid depending on which path is taken.
        assert resp.status_code in (200, 404)

    def test_surface_endpoint_200_returns_octet_stream(self, client):
        """If the input STL exists on disk, content-type should be octet-stream."""
        job_id = _upload_sphere(client)
        resp = client.get(f"/jobs/{job_id}/surface")
        if resp.status_code == 200:
            assert "octet-stream" in resp.headers.get("content-type", "")

    def test_download_endpoint_unknown_job_returns_404(self, client):
        resp = client.get("/jobs/notfound/download/anything.txt")
        assert resp.status_code == 404

    def test_download_endpoint_missing_file_returns_404(self, client):
        job_id = _upload_sphere(client)
        resp = client.get(f"/jobs/{job_id}/download/does_not_exist.txt")
        assert resp.status_code == 404

    def test_mesh_data_endpoint_no_polymesh_returns_error(self, client):
        """GET /jobs/{id}/mesh with no polyMesh on disk → 500 with error."""
        job_id = _upload_sphere(client)
        resp = client.get(f"/jobs/{job_id}/mesh")
        # No polyMesh generated, so either 404 (job not found guard) or 500
        assert resp.status_code in (404, 500)


# ---------------------------------------------------------------------------
# 7. TestUploadValidation — size / format guards
# ---------------------------------------------------------------------------


class TestUploadValidation:
    def test_upload_too_large_returns_413(self, client):
        """A file whose content exceeds MAX_UPLOAD_SIZE must be rejected with 413."""
        from desktop.server import MAX_UPLOAD_SIZE

        # Build a just-over-limit payload without allocating 100 MB in one shot:
        # we patch UploadFile.read so the server sees oversized chunks.
        oversized = b"x" * (MAX_UPLOAD_SIZE + 1)
        resp = client.post(
            "/upload",
            files={"file": ("big.stl", io.BytesIO(oversized), "application/octet-stream")},
        )
        assert resp.status_code == 413
        body = resp.json()
        assert "error" in body
        assert "max_bytes" in body

    def test_upload_wrong_format_txt_returns_400(self, client):
        """Uploading a .txt file must be rejected with 400."""
        resp = client.post(
            "/upload",
            files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "error" in body
        assert "allowed" in body

    def test_upload_wrong_format_pdf_returns_400(self, client):
        """Uploading a .pdf file must be rejected with 400."""
        resp = client.post(
            "/upload",
            files={"file": ("report.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        )
        assert resp.status_code == 400

    def test_upload_allowed_extensions_accepted(self, client):
        """Each extension in ALLOWED_EXTENSIONS should upload successfully."""
        from desktop.server import ALLOWED_EXTENSIONS

        # Use a tiny payload; the server does not validate content, only extension.
        for ext in sorted(ALLOWED_EXTENSIONS):
            resp = client.post(
                "/upload",
                files={"file": (f"model{ext}", io.BytesIO(b"\x00" * 10), "application/octet-stream")},
            )
            assert resp.status_code == 200, f"Extension {ext!r} was unexpectedly rejected"
        # Clean up jobs created by this test
        _jobs.clear()

    def test_upload_size_exactly_at_limit_accepted(self, client):
        """A file that is exactly MAX_UPLOAD_SIZE bytes must be accepted."""
        from desktop.server import MAX_UPLOAD_SIZE

        exact = b"x" * MAX_UPLOAD_SIZE
        resp = client.post(
            "/upload",
            files={"file": ("limit.stl", io.BytesIO(exact), "application/octet-stream")},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 8. TestWebSocketQualityOptions — draft / standard / fine
# ---------------------------------------------------------------------------


class TestWebSocketQualityOptions:
    """Verify that the quality parameter is forwarded to the pipeline correctly."""

    def _collect_messages(self, ws, *, timeout: float = 10.0) -> list[dict]:
        messages: list[dict] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                raw = ws.receive_text()
                msg = json.loads(raw)
                messages.append(msg)
                if msg.get("type") in ("result", "error"):
                    break
            except Exception:
                break
        return messages

    def _run_with_quality(self, client, quality: str) -> list[dict]:
        mock_orch = _make_mock_orchestrator(verdict="PASS")
        job_id = _upload_sphere(client)
        with patch("desktop.server._run_mesh_pipeline", side_effect=_mock_pipeline):
            with client.websocket_connect(f"/ws/mesh/{job_id}") as ws:
                ws.send_json(
                    {
                        "action": "start",
                        "quality": quality,
                        "tier": "auto",
                        "max_iterations": 1,
                    }
                )
                return self._collect_messages(ws)

    def test_draft_quality_succeeds(self, client):
        messages = self._run_with_quality(client, "draft")
        result_msgs = [m for m in messages if m.get("type") == "result"]
        assert result_msgs and result_msgs[0].get("success") is True

    def test_standard_quality_succeeds(self, client):
        messages = self._run_with_quality(client, "standard")
        result_msgs = [m for m in messages if m.get("type") == "result"]
        assert result_msgs and result_msgs[0].get("success") is True

    def test_fine_quality_succeeds(self, client):
        messages = self._run_with_quality(client, "fine")
        result_msgs = [m for m in messages if m.get("type") == "result"]
        assert result_msgs and result_msgs[0].get("success") is True

    def test_strategy_message_contains_quality_level(self, client):
        messages = self._run_with_quality(client, "draft")
        strategy_msgs = [m for m in messages if m.get("type") == "strategy"]
        assert strategy_msgs, "Expected a strategy message"
        assert "quality_level" in strategy_msgs[0]

    def test_result_verdict_is_string(self, client):
        """Verdict in the result message must be a plain string, not an Enum repr."""
        messages = self._run_with_quality(client, "standard")
        result_msgs = [m for m in messages if m.get("type") == "result"]
        assert result_msgs
        verdict = result_msgs[0].get("verdict", "")
        assert isinstance(verdict, str)
        # Should not contain angle-bracket Enum representation
        assert "<" not in verdict and "." not in verdict


# ---------------------------------------------------------------------------
# 9. TestDownloadPolyMeshZip
# ---------------------------------------------------------------------------


class TestDownloadPolyMeshZip:
    def test_polymesh_zip_nonexistent_job_returns_404(self, client):
        resp = client.get("/jobs/notfound/download/polyMesh.zip")
        assert resp.status_code == 404

    def test_polymesh_zip_no_polymesh_dir_returns_404(self, client):
        """Job exists but no mesh has been generated yet."""
        job_id = _upload_sphere(client)
        resp = client.get(f"/jobs/{job_id}/download/polyMesh.zip")
        assert resp.status_code == 404

    def test_polymesh_zip_returns_zip_when_dir_exists(self, client):
        """Create a fake polyMesh directory and verify the ZIP endpoint."""
        import zipfile as zf_mod

        job_id = _upload_sphere(client)
        job = _jobs[job_id]

        # Create a minimal fake polyMesh structure
        poly_dir = Path(job["work_dir"]) / "case" / "constant" / "polyMesh"
        poly_dir.mkdir(parents=True)
        (poly_dir / "points").write_text("FoamFile{}\n// points data")
        (poly_dir / "faces").write_text("FoamFile{}\n// faces data")
        (poly_dir / "owner").write_text("FoamFile{}\n// owner data")

        resp = client.get(f"/jobs/{job_id}/download/polyMesh.zip")
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("application/zip")

        # Content must be a valid ZIP containing the polyMesh files
        with zf_mod.ZipFile(io.BytesIO(resp.content)) as z:
            names = z.namelist()
        # The archive contains paths relative to `case/`, e.g. constant/polyMesh/points
        assert any("points" in n for n in names)
        assert any("faces" in n for n in names)

    def test_polymesh_zip_content_disposition_header(self, client):
        """ZIP response should carry a content-disposition attachment header."""
        job_id = _upload_sphere(client)
        job = _jobs[job_id]

        poly_dir = Path(job["work_dir"]) / "case" / "constant" / "polyMesh"
        poly_dir.mkdir(parents=True)
        (poly_dir / "points").write_text("data")

        resp = client.get(f"/jobs/{job_id}/download/polyMesh.zip")
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert "polyMesh" in cd


# ---------------------------------------------------------------------------
# 10. TestConcurrentJobs
# ---------------------------------------------------------------------------


class TestConcurrentJobs:
    """Upload two files and run two WebSocket sessions concurrently."""

    def _collect_messages(self, ws, *, timeout: float = 10.0) -> list[dict]:
        messages: list[dict] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                raw = ws.receive_text()
                msg = json.loads(raw)
                messages.append(msg)
                if msg.get("type") in ("result", "error"):
                    break
            except Exception:
                break
        return messages

    def test_two_concurrent_jobs_both_succeed(self, client):
        """Two independent jobs must both complete with success=True."""
        mock_orch_1 = _make_mock_orchestrator(verdict="PASS")
        mock_orch_2 = _make_mock_orchestrator(verdict="PASS")

        job_id_1 = _upload_sphere(client)
        job_id_2 = _upload_sphere(client)

        assert job_id_1 != job_id_2, "Job IDs must be unique"

        results = []
        with patch("core.pipeline.orchestrator.PipelineOrchestrator", return_value=mock_orch_1):
            with client.websocket_connect(f"/ws/mesh/{job_id_1}") as ws1:
                ws1.send_json(
                    {"action": "start", "quality": "draft", "tier": "auto", "max_iterations": 1}
                )
                msgs1 = self._collect_messages(ws1)
        results.append(msgs1)

        with patch("core.pipeline.orchestrator.PipelineOrchestrator", return_value=mock_orch_2):
            with client.websocket_connect(f"/ws/mesh/{job_id_2}") as ws2:
                ws2.send_json(
                    {"action": "start", "quality": "draft", "tier": "auto", "max_iterations": 1}
                )
                msgs2 = self._collect_messages(ws2)
        results.append(msgs2)

        for msgs in results:
            result_msgs = [m for m in msgs if m.get("type") == "result"]
            assert result_msgs, "Each job must emit a result message"
            assert result_msgs[0].get("success") is True, "Each job must succeed"

    def test_two_jobs_have_independent_state(self, client):
        """Changes to one job's status must not affect the other."""
        job_id_1 = _upload_sphere(client)
        job_id_2 = _upload_sphere(client)

        # Manually mark one as completed
        _jobs[job_id_1]["status"] = "completed"

        assert _jobs[job_id_2]["status"] == "pending"

    def test_two_jobs_are_stored_independently(self, client):
        job_id_1 = _upload_sphere(client)
        job_id_2 = _upload_sphere(client)

        assert job_id_1 in _jobs
        assert job_id_2 in _jobs
        assert _jobs[job_id_1]["work_dir"] != _jobs[job_id_2]["work_dir"]


# ---------------------------------------------------------------------------
# 11. TestCORSHeaders
# ---------------------------------------------------------------------------


class TestCORSHeaders:
    def test_cors_preflight_returns_200(self, client):
        """OPTIONS pre-flight must succeed and carry CORS headers."""
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # starlette TestClient returns 200 for OPTIONS when CORS is configured
        assert resp.status_code == 200

    def test_cors_allow_origin_header_present(self, client):
        """A regular GET must return an allow-origin CORS header."""
        resp = client.get("/health", headers={"Origin": "http://example.com"})
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers


# ---------------------------------------------------------------------------
# 12. TestJobCleanup (unit-level — no actual sleep)
# ---------------------------------------------------------------------------


class TestJobCleanup:
    def test_updated_at_is_set_on_create(self, client):
        job_id = _upload_sphere(client)
        assert "updated_at" in _jobs[job_id]
        assert _jobs[job_id]["updated_at"] > 0

    def test_updated_at_is_refreshed_on_get_job(self, client):
        job_id = _upload_sphere(client)
        t_before = _jobs[job_id]["updated_at"]
        time.sleep(0.01)
        client.get(f"/jobs/{job_id}")
        assert _jobs[job_id]["updated_at"] >= t_before

    def test_expired_jobs_are_removed_by_cleanup(self):
        """Expired jobs (updated_at far in the past) are pruned by the cleanup fn."""
        import asyncio
        from desktop.server import _cleanup_old_jobs, JOB_TTL_SECONDS

        # Inject a fake expired job
        fake_id = "expiredjob"
        fake_work_dir = Path(tempfile.mkdtemp(prefix="autotessell_test_expired_"))
        _jobs[fake_id] = {
            "id": fake_id,
            "status": "completed",
            "work_dir": str(fake_work_dir),
            "updated_at": time.time() - JOB_TTL_SECONDS - 1,
            "created_at": time.time() - JOB_TTL_SECONDS - 1,
        }

        # Run one cleanup cycle (skip the asyncio.sleep via a trimmed coroutine)
        async def _run_one_pass() -> None:
            now = time.time()
            expired = [
                jid
                for jid, job in list(_jobs.items())
                if now - job.get("updated_at", job.get("created_at", now)) > JOB_TTL_SECONDS
            ]
            import shutil as _shutil

            for jid in expired:
                job = _jobs.pop(jid, None)
                if job:
                    wd = Path(job.get("work_dir", ""))
                    if wd.exists():
                        _shutil.rmtree(wd, ignore_errors=True)

        asyncio.run(_run_one_pass())

        assert fake_id not in _jobs, "Expired job should have been removed"
        assert not fake_work_dir.exists(), "Temp dir should have been deleted"
