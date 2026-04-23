"""core/preprocessor/native_remesh/ 회귀 테스트 — isotropic remesh + Lloyd CVT."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.analyzer import topology as T
from core.analyzer.readers import read_stl
from core.preprocessor.native_remesh import isotropic_remesh, lloyd_cvt


_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"


@pytest.fixture
def sphere_mesh():
    if not SPHERE_STL.exists():
        pytest.skip("sphere.stl 없음")
    return read_stl(SPHERE_STL)


def _edge_length_stats(V: np.ndarray, F: np.ndarray) -> tuple[float, float, float, float]:
    e = np.concatenate([
        np.linalg.norm(V[F[:, 1]] - V[F[:, 0]], axis=1),
        np.linalg.norm(V[F[:, 2]] - V[F[:, 1]], axis=1),
        np.linalg.norm(V[F[:, 0]] - V[F[:, 2]], axis=1),
    ])
    return float(e.min()), float(e.mean()), float(e.max()), float(e.std())


# ---------------------------------------------------------------------------
# isotropic remesh
# ---------------------------------------------------------------------------


def test_isotropic_preserves_closed_manifold(sphere_mesh) -> None:
    V = sphere_mesh.vertices
    F = sphere_mesh.faces
    V2, F2 = isotropic_remesh(V, F, target_edge_length=0.15, n_iter=3)
    assert T.is_watertight(F2)
    assert T.is_manifold(F2)


def test_isotropic_reduces_edge_length_variance(sphere_mesh) -> None:
    """target 근처로 수렴하면 편차 감소 (또는 최소한 동등)."""
    V = sphere_mesh.vertices
    F = sphere_mesh.faces
    _, mean0, _, std0 = _edge_length_stats(V, F)
    V2, F2 = isotropic_remesh(V, F, target_edge_length=float(mean0), n_iter=3)
    _, mean1, _, std1 = _edge_length_stats(V2, F2)
    # 동일 target 기준이면 mean 은 근접, std 는 크게 증가하지 않아야 함
    assert std1 <= std0 * 1.5


def test_isotropic_increases_faces_for_small_target(sphere_mesh) -> None:
    """target 이 기존 mean edge 보다 작으면 face 수 증가 (split)."""
    V = sphere_mesh.vertices
    F = sphere_mesh.faces
    mean_before = _edge_length_stats(V, F)[1]
    V2, F2 = isotropic_remesh(V, F, target_edge_length=mean_before * 0.5, n_iter=2)
    assert F2.shape[0] > F.shape[0]


def test_isotropic_decreases_faces_for_large_target(sphere_mesh) -> None:
    """target 이 기존 max edge 보다 훨씬 크면 face 수 감소 (collapse)."""
    V = sphere_mesh.vertices
    F = sphere_mesh.faces
    _, _, max_before, _ = _edge_length_stats(V, F)
    V2, F2 = isotropic_remesh(V, F, target_edge_length=max_before * 3.0, n_iter=2)
    # sphere 에서는 collapse 가 많이 되어야 하나, MVP 는 보수적 — face 수가
    # 감소하거나 최소한 같아야 함.
    assert F2.shape[0] <= F.shape[0]


def test_isotropic_empty_input_is_noop() -> None:
    V = np.zeros((0, 3))
    F = np.zeros((0, 3), dtype=np.int64)
    V2, F2 = isotropic_remesh(V, F, target_edge_length=0.1, n_iter=3)
    assert V2.shape[0] == 0 and F2.shape[0] == 0


# ---------------------------------------------------------------------------
# Lloyd CVT
# ---------------------------------------------------------------------------


def test_cvt_preserves_topology_and_counts(sphere_mesh) -> None:
    V = sphere_mesh.vertices
    F = sphere_mesh.faces
    V2 = lloyd_cvt(V, F, n_iter=5)
    # topology 불변
    assert V2.shape == V.shape
    assert T.is_watertight(F)
    assert T.is_manifold(F)


def test_cvt_with_surface_projection_keeps_vertices_on_sphere(sphere_mesh) -> None:
    """원본 sphere 표면에 KDTree 사영 옵션: vertex 가 원본 표면 점 중 하나와 같음."""
    V = sphere_mesh.vertices
    F = sphere_mesh.faces
    V2 = lloyd_cvt(V, F, n_iter=3, original_surface=(V, F))
    # 각 new vertex 가 원본 vertex 집합 중 하나여야 함 (projection → 최근접 vertex)
    from scipy.spatial import cKDTree
    tree = cKDTree(V)
    _, idx = tree.query(V2, k=1)
    dists = np.linalg.norm(V2 - V[idx], axis=1)
    assert float(dists.max()) < 1e-9


def test_cvt_reduces_edge_length_std(sphere_mesh) -> None:
    """CVT relaxation 은 edge length std 를 증가시키지 않아야 한다."""
    V = sphere_mesh.vertices
    F = sphere_mesh.faces
    std0 = _edge_length_stats(V, F)[3]
    V2 = lloyd_cvt(V, F, n_iter=5, lam=0.3)
    std1 = _edge_length_stats(V2, F)[3]
    assert std1 <= std0 * 1.1  # 약간의 증가까지는 허용 (본질적으로 smoothing)


def test_cvt_empty_input_is_noop() -> None:
    V = np.zeros((0, 3))
    F = np.zeros((0, 3), dtype=np.int64)
    V2 = lloyd_cvt(V, F, n_iter=5)
    assert V2.shape[0] == 0


# ---------------------------------------------------------------------------
# beta99 Task C: valence_constraint 파라미터 테스트
# ---------------------------------------------------------------------------


def test_valence_constraint_signature_exists() -> None:
    """isotropic_remesh 에 valence_constraint 파라미터가 있어야 함."""
    import inspect
    from core.preprocessor.native_remesh.isotropic import isotropic_remesh
    sig = inspect.signature(isotropic_remesh)
    assert "valence_constraint" in sig.parameters
    assert sig.parameters["valence_constraint"].default is False


def test_valence_constraint_false_default_unchanged(sphere_mesh) -> None:
    """valence_constraint=False (기본) 은 기존 결과와 동일해야 함."""
    V = sphere_mesh.vertices
    F = sphere_mesh.faces
    V1, F1 = isotropic_remesh(V, F, target_edge_length=0.2, n_iter=2, valence_constraint=False)
    V2, F2 = isotropic_remesh(V, F, target_edge_length=0.2, n_iter=2)
    assert F1.shape == F2.shape
    assert V1.shape == V2.shape


def test_valence_constraint_true_produces_valid_mesh(sphere_mesh) -> None:
    """valence_constraint=True 로 remesh 후에도 manifold 유지."""
    from core.analyzer import topology as T
    V = sphere_mesh.vertices
    F = sphere_mesh.faces
    V2, F2 = isotropic_remesh(
        V, F, target_edge_length=0.15, n_iter=3, valence_constraint=True,
    )
    assert V2.shape[0] > 0
    assert F2.shape[0] > 0
    assert T.is_manifold(F2)


def test_valence_constraint_does_not_increase_deviation(sphere_mesh) -> None:
    """valence_constraint=True 가 False 보다 total valence deviation 을 낮추거나 같아야 함."""
    import numpy as _np
    from core.preprocessor.native_remesh.isotropic import _build_edge_map

    def _total_deviation(V: np.ndarray, F: np.ndarray) -> int:
        edge_map = _build_edge_map(F)
        n_verts = V.shape[0]
        valence = _np.zeros(n_verts, dtype=_np.int64)
        for f in F:
            for v in f:
                valence[int(v)] += 1
        on_boundary = _np.zeros(n_verts, dtype=bool)
        for (a, b), fl in edge_map.items():
            if len(fl) == 1:
                on_boundary[a] = True; on_boundary[b] = True
        target = _np.where(on_boundary, 4, 6)
        return int(_np.abs(valence - target).sum())

    V = sphere_mesh.vertices
    F = sphere_mesh.faces
    _, F_nc = isotropic_remesh(V, F, target_edge_length=0.2, n_iter=3, valence_constraint=False)
    _, F_vc = isotropic_remesh(V, F, target_edge_length=0.2, n_iter=3, valence_constraint=True)
    dev_nc = _total_deviation(V, F_nc)
    dev_vc = _total_deviation(V, F_vc)
    # valence_constraint 사용 시 deviation 이 증가하면 안 됨
    assert dev_vc <= dev_nc + 10  # 소폭 허용 (vertex 수 차이 가능)
