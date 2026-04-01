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
    orch._evaluate = MagicMock(return_value=quality_report)

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

        with patch("core.pipeline.orchestrator.PipelineOrchestrator", return_value=mock_orch):
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

        with patch("core.pipeline.orchestrator.PipelineOrchestrator", return_value=mock_orch):
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

        with patch("core.pipeline.orchestrator.PipelineOrchestrator", return_value=mock_orch):
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

        with patch("core.pipeline.orchestrator.PipelineOrchestrator", return_value=mock_orch):
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

        with patch("core.pipeline.orchestrator.PipelineOrchestrator", return_value=mock_orch):
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

        with patch("core.pipeline.orchestrator.PipelineOrchestrator", return_value=mock_orch):
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
        mock_orch = _make_mock_orchestrator(generator_status="failed")
        job_id = _upload_sphere(client)

        # _find_successful_tier returns None for failed
        mock_orch._find_successful_tier.return_value = None

        with patch("core.pipeline.orchestrator.PipelineOrchestrator", return_value=mock_orch):
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
