"""Final native-tet evidence must certify the immutable caller input."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.generator.native_tet.mesher import NativeTetResult, generate_native_tet
from core.generator.native_tet.surface_transaction_gate import (
    MetricSurfaceTransactionReport,
    MetricTopologyTransactionReport,
    SourceSurfaceMetrics,
)

_POINTS = np.asarray(
    ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    dtype=np.float64,
)
_FACES = np.asarray(
    ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)),
    dtype=np.int64,
)
_POLYMESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")
_CUBE = Path(__file__).resolve().parent / "benchmarks" / "cube.stl"
_VALID_POINT_SHA256 = "4165a5be53209fff5ace98d58c3de63f2de6ef10a25df234d95a52b06bca362f"
_VALID_TET_SHA256 = "e12414338bdb3184808636b59b3a3d9396c9c42204715b055a3f2569b8adb15e"
_VALID_FILE_SHA256 = {
    "points": "abf3ef72a9664ed2db70b97db09f5ca73fde009a231827f904ce5fe5c52ef5dc",
    "faces": "6a6d7371d0366795c449283952a4716ed00d612199d024774975e56106fafa35",
    "owner": "5c0977e5c44bcbc5f53cdb2bb0080a388c169dfad9d8498519628c6bebc46440",
    "neighbour": "6f96684a25759c24c7b8cd4161ac6d9a2fe9b545404fa8fd1e691f4324180950",
    "boundary": "f42e4d01286952eea4540c2b8389afe68b59734b5af395eed39432242a528fa6",
}


def _generate(
    points: np.ndarray,
    faces: np.ndarray,
    case_dir: Path,
) -> NativeTetResult:
    return generate_native_tet(
        points,
        faces,
        case_dir,
        target_cells=50,
        enable_bsp_insertion=False,
        enable_edge_recovery=False,
        enable_phase_b=False,
        enable_phase_c=False,
    )


def _digest(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array)).hexdigest()


def test_valid_tetrahedron_remains_byte_exact(tmp_path: Path) -> None:
    points = _POINTS.copy()
    faces = _FACES.copy()
    point_bytes = points.tobytes()
    face_bytes = faces.tobytes()
    case_dir = tmp_path / "valid"

    result = _generate(points, faces, case_dir)

    assert result.success, result.message
    assert result.n_points == 4
    assert result.n_cells == 1
    assert _digest(result.tet_points) == _VALID_POINT_SHA256
    assert _digest(result.tets) == _VALID_TET_SHA256
    poly_mesh = case_dir / "constant" / "polyMesh"
    assert {
        name: hashlib.sha256((poly_mesh / name).read_bytes()).hexdigest()
        for name in _POLYMESH_FILES
    } == _VALID_FILE_SHA256
    assert points.tobytes() == point_bytes
    assert faces.tobytes() == face_bytes


def test_auto_fix_cannot_replace_immutable_duplicate_coordinate_source(
    tmp_path: Path,
) -> None:
    points = np.vstack((_POINTS, _POINTS[0])).astype(np.float64, copy=False)
    faces = np.asarray(
        ((4, 2, 1), (0, 1, 3), (1, 2, 3), (2, 4, 3)),
        dtype=np.int64,
    )
    point_bytes = points.tobytes()
    face_bytes = faces.tobytes()
    case_dir = tmp_path / "duplicate_source_coordinate"

    result = _generate(points, faces, case_dir)

    assert not result.success
    assert result.n_points == 4
    assert result.n_cells == 1
    assert "source_points contains ambiguous duplicate coordinates" in result.message
    assert result.debug_info["strict_source_topology_error"] == (
        "ValueError: source_points contains ambiguous duplicate coordinates"
    )
    assert not (case_dir / "constant" / "polyMesh").exists()
    assert points.tobytes() == point_bytes
    assert faces.tobytes() == face_bytes


def test_vertex_and_face_reorder_still_certifies_original_source(tmp_path: Path) -> None:
    order = np.asarray((3, 0, 2, 1), dtype=np.int64)
    old_to_new = np.empty(order.size, dtype=np.int64)
    old_to_new[order] = np.arange(order.size, dtype=np.int64)
    points = _POINTS[order].copy()
    faces = old_to_new[_FACES[::-1, ::-1]].copy()
    point_bytes = points.tobytes()
    face_bytes = faces.tobytes()

    result = _generate(points, faces, tmp_path / "reordered")

    assert result.success, result.message
    assert result.debug_info["strict_source_topology"]["valid"] is True
    assert result.debug_info["strict_source_component_bijection"]["bijective"] is True
    assert (
        result.debug_info["strict_source_component_bijection"]["source_faces_preserved"]
        is True
    )
    assert points.tobytes() == point_bytes
    assert faces.tobytes() == face_bytes


def test_metric_transactions_receive_immutable_original_after_auto_fix_rebind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.generator.native_tet.input_check as input_check
    import core.generator.native_tet.klingner_full_sweep as klingner_sweep
    import core.generator.native_tet.metric_tensor_sweep as metric_sweep
    import core.generator.native_tet.plane_coverage as plane_coverage_module
    import core.generator.native_tet.surface_transaction_gate as transaction_gate

    mesh = read_stl(_CUBE)
    original_points = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    original_faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)

    # Exercise the entry coercion too: caller arrays are writable non-owning,
    # non-contiguous views.  The source ledger must not alias either them or
    # the arrays returned by the simulated auto-fix rebind.
    point_storage = np.empty((original_points.shape[0], 6), dtype=np.float64)
    face_storage = np.empty((original_faces.shape[0], 6), dtype=np.int64)
    caller_points = point_storage[:, ::2]
    caller_faces = face_storage[:, ::2]
    caller_points[...] = original_points
    caller_faces[...] = original_faces
    point_bytes = caller_points.tobytes()
    face_bytes = caller_faces.tobytes()
    repaired_points = original_points.copy()
    repaired_faces = original_faces.copy()
    auto_fix_calls = 0

    def forced_auto_fix(
        _vertices: np.ndarray,
        _faces: np.ndarray,
        **_kwargs: object,
    ) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
        nonlocal auto_fix_calls
        auto_fix_calls += 1
        return repaired_points, repaired_faces, {"n_winding_flip": 1}

    monkeypatch.setattr(input_check, "auto_fix_input", forced_auto_fix)

    def fixed_grade_b_coverage(
        _source_vertices: np.ndarray,
        _source_faces: np.ndarray,
        _points: np.ndarray,
        _tets: np.ndarray,
    ) -> SimpleNamespace:
        return SimpleNamespace(plane_coverage=0.9, area_coverage=0.9)

    monkeypatch.setattr(
        plane_coverage_module,
        "plane_coverage",
        fixed_grade_b_coverage,
    )

    def rejected_klingner_sweep(
        points: np.ndarray,
        tets: np.ndarray,
        **_kwargs: object,
    ) -> tuple[np.ndarray, np.ndarray, SimpleNamespace]:
        return points, tets, SimpleNamespace(accepted=False)

    monkeypatch.setattr(
        klingner_sweep,
        "klingner_full_sweep",
        rejected_klingner_sweep,
    )

    def accepted_identity_sweep(
        points: np.ndarray,
        tets: np.ndarray,
        **_kwargs: object,
    ) -> tuple[np.ndarray, np.ndarray, SimpleNamespace]:
        return (
            points.copy(),
            tets.copy(),
            SimpleNamespace(
                accepted=True,
                n_cycles_used=0,
                metric_aniso_max=1.0,
                pre_mean_q=0.2,
                post_mean_q=0.2,
                n_collapse=0,
                n_split=0,
                n_flip=0,
            ),
        )

    monkeypatch.setattr(metric_sweep, "metric_tensor_sweep", accepted_identity_sweep)
    monkeypatch.setenv("AUTO_TESSELL_TET_METRIC_SOURCE_TXN", "1")

    ledger_ids: list[tuple[int, int]] = []

    def assert_source_ledger(
        source_vertices: np.ndarray,
        source_faces: np.ndarray,
    ) -> None:
        assert source_vertices.flags.c_contiguous
        assert source_faces.flags.c_contiguous
        assert source_vertices.flags.owndata
        assert source_faces.flags.owndata
        assert not source_vertices.flags.writeable
        assert not source_faces.flags.writeable
        assert np.array_equal(source_vertices, original_points)
        assert np.array_equal(source_faces, original_faces)
        assert not np.shares_memory(source_vertices, caller_points)
        assert not np.shares_memory(source_faces, caller_faces)
        assert not np.shares_memory(source_vertices, repaired_points)
        assert not np.shares_memory(source_faces, repaired_faces)
        ledger_ids.append((id(source_vertices), id(source_faces)))

    def instrumented_topology_transaction(
        source_vertices: np.ndarray,
        source_faces: np.ndarray,
        _pre_points: np.ndarray,
        _pre_tets: np.ndarray,
        candidate_points: np.ndarray,
        candidate_tets: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, MetricTopologyTransactionReport]:
        assert_source_ledger(source_vertices, source_faces)
        return (
            candidate_points,
            candidate_tets,
            MetricTopologyTransactionReport(True, "instrumented", None),
        )

    metrics = SourceSurfaceMetrics(0.0, 1.0, 1.0)

    def instrumented_surface_transaction(
        source_vertices: np.ndarray,
        source_faces: np.ndarray,
        _pre_points: np.ndarray,
        _pre_tets: np.ndarray,
        candidate_points: np.ndarray,
        candidate_tets: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, MetricSurfaceTransactionReport]:
        assert_source_ledger(source_vertices, source_faces)
        return (
            candidate_points,
            candidate_tets,
            MetricSurfaceTransactionReport(True, "instrumented", metrics, metrics),
        )

    monkeypatch.setattr(
        transaction_gate,
        "apply_metric_topology_transaction",
        instrumented_topology_transaction,
    )
    monkeypatch.setattr(
        transaction_gate,
        "apply_metric_surface_transaction",
        instrumented_surface_transaction,
    )

    result = generate_native_tet(
        caller_points,
        caller_faces,
        tmp_path / "metric_source_ledger",
        target_cells=1_000,
    )

    assert result.n_cells > 100
    assert auto_fix_calls == 1
    assert len(ledger_ids) == 2
    assert ledger_ids[0] == ledger_ids[1]
    assert caller_points.tobytes() == point_bytes
    assert caller_faces.tobytes() == face_bytes
