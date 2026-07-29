"""QOPT0 native local-cavity infrastructure tests."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest


_BUILD = Path(__file__).resolve().parents[1] / "auto_tessell_core" / "build"


def _module_or_skip():
    if str(_BUILD) not in sys.path:
        sys.path.insert(0, str(_BUILD))
    return pytest.importorskip("native_tet_qopt")


def _sample_mesh() -> tuple[np.ndarray, np.ndarray]:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 0.0],
            [1.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    tets = np.array(
        [
            [0, 1, 2, 3],
            [1, 4, 2, 3],
            [1, 5, 4, 3],
        ],
        dtype=np.int64,
    )
    return points, tets


def test_local_cavity_quality_vectors_match_python_fallback() -> None:
    native = _module_or_skip()
    from core.generator.native_tet import qopt

    points, tets = _sample_mesh()
    seeds = np.array([0, 1, 2], dtype=np.int64)

    native_result = native.local_cavity_quality_vectors(points, tets, seeds, max_ring=1)
    fallback_result = qopt.local_cavity_quality_vectors(points, tets, seeds, max_ring=1)

    assert np.array_equal(native_result[0], fallback_result[0])
    assert np.array_equal(native_result[1], fallback_result[1])
    assert np.allclose(native_result[2], fallback_result[2], rtol=1e-14, atol=1e-14)
    assert dict(native_result[3]) == fallback_result[3]
    assert native_result[0].tolist() == [0, 3, 6, 9]
    assert native_result[1].tolist() == [0, 1, 2, 0, 1, 2, 0, 1, 2]


def test_ring_zero_cavity_is_seed_only_and_deterministic() -> None:
    native = _module_or_skip()
    points, tets = _sample_mesh()
    offsets, cavity_tets, quality, stats = native.local_cavity_quality_vectors(
        points, tets, np.array([2, 0], dtype=np.int64), max_ring=0,
    )
    assert offsets.tolist() == [0, 1, 2]
    assert cavity_tets.tolist() == [2, 0]
    assert np.all(np.asarray(quality) > 0.0)
    assert dict(stats) == {"n_cavities": 2, "max_cavity_size": 1, "max_ring": 0}


def test_quality_vector_compare_is_sorted_lexicographic() -> None:
    native = _module_or_skip()
    assert native.compare_quality_vectors(
        np.array([0.3, 0.1, 0.2]), np.array([0.3, 0.2, 0.2]),
    ) == 1
    assert native.quality_vector_accepts(
        np.array([0.3, 0.1, 0.2]), np.array([0.3, 0.2, 0.2]),
    )
    assert native.compare_quality_vectors(
        np.array([0.3, 0.2, 0.2]), np.array([0.3, 0.1, 0.2]),
    ) == -1
    assert native.compare_quality_vectors(
        np.array([0.2, 0.3]), np.array([0.2, 0.3]),
    ) == 0


def test_quality_vector_compare_uses_shorter_tie_as_smaller_mesh_win() -> None:
    native = _module_or_skip()
    assert native.compare_quality_vectors(
        np.array([0.2, 0.3, 0.4]), np.array([0.2, 0.3]),
    ) == 1
    assert native.compare_quality_vectors(
        np.array([0.2, 0.3]), np.array([0.2, 0.3, 0.4]),
    ) == -1


def test_qopt_wrapper_runs_without_native_for_public_fallback() -> None:
    from core.generator.native_tet import qopt

    points, tets = _sample_mesh()
    offsets, cavity_tets, quality, stats = qopt.local_cavity_quality_vectors(
        points, tets, np.array([1], dtype=np.int64), max_ring=1,
    )
    assert offsets.tolist() == [0, 3]
    assert cavity_tets.tolist() == [0, 1, 2]
    assert len(quality) == 3
    assert stats["max_cavity_size"] == 3
    assert qopt.quality_vector_accepts(
        np.array([0.1, 0.2]), np.array([0.15, 0.2]),
    )


def test_guarded_vertex_moves_accept_only_local_quality_improvements() -> None:
    native = _module_or_skip()
    h_regular = np.sqrt(2.0 / 3.0)
    y_apex = np.sqrt(3.0) / 6.0
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, np.sqrt(3.0) / 2.0, 0.0],
            [0.5, y_apex, 0.12],
            [3.0, 0.0, 0.0],
            [4.0, 0.0, 0.0],
            [3.5, np.sqrt(3.0) / 2.0, 0.0],
            [3.5, y_apex, h_regular],
        ],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3], [4, 5, 6, 7]], dtype=np.int64)
    vertices = np.array([3, 7], dtype=np.int64)
    targets = np.array(
        [
            [0.5, y_apex, h_regular],
            [3.5, y_apex, 0.05],
        ],
        dtype=np.float64,
    )

    out, stats = native.apply_guarded_vertex_moves(points, tets, vertices, targets)

    assert dict(stats)["attempted"] == 2
    assert dict(stats)["accepted"] == 1
    assert dict(stats)["rejected_quality"] == 1
    assert np.allclose(out[3], targets[0])
    assert np.allclose(out[7], points[7])

    from core.generator.native_tet.qopt import build_vertex_to_tets_csr

    offsets, incident = build_vertex_to_tets_csr(tets, points.shape[0])
    out_csr, stats_csr = native.apply_guarded_vertex_moves_csr(
        points, tets, offsets, incident, vertices, targets,
    )
    assert np.array_equal(out_csr, out)
    assert dict(stats_csr) == dict(stats)


def test_guarded_vertex_moves_reject_inversion() -> None:
    native = _module_or_skip()
    points, tets = _sample_mesh()
    out, stats = native.apply_guarded_vertex_moves(
        points,
        tets[:1],
        np.array([3], dtype=np.int64),
        np.array([[0.25, 0.25, -0.1]], dtype=np.float64),
    )
    assert dict(stats)["accepted"] == 0
    assert dict(stats)["rejected_volume"] == 1
    assert np.array_equal(out, points)


def test_build_vertex_to_tets_csr_matches_expected_incidents() -> None:
    from core.generator.native_tet.qopt import build_vertex_to_tets_csr

    _points, tets = _sample_mesh()
    offsets, incident = build_vertex_to_tets_csr(tets, 6)
    assert offsets.tolist() == [0, 1, 4, 6, 9, 11, 12]
    assert incident[offsets[1]:offsets[2]].tolist() == [0, 1, 2]
    assert incident[offsets[5]:offsets[6]].tolist() == [2]


def test_native_fused_guarded_smooth_matches_public_smooth_result() -> None:
    native = _module_or_skip()
    from core.generator.native_tet.smooth import smooth_interior

    points, tets = _sample_mesh()
    locked = np.array([0, 2, 4], dtype=np.int64)
    fused_points, fused_stats = native.smooth_interior_guarded(
        points, tets, locked, n_iter=2, relax=0.35,
    )

    public_points = points.copy()
    public_stats = smooth_interior(
        public_points, tets, locked_vertex_ids=locked, n_iter=2, relax=0.35,
        quality_guard=True,
    )

    assert np.allclose(fused_points, public_points)
    assert int(dict(fused_stats)["accepted"]) == public_stats.qopt_accepted
    assert int(dict(fused_stats)["rejected_quality"]) == public_stats.qopt_rejected_quality
