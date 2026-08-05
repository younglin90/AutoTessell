"""CARD BOOLMERGE2 — core/generator/native_tet/boolean_merge.filter_tets_to_union 단위 테스트.

정본 실험(research/quality-harness/plan_boolmerge2.md)이 grid N=16~40 에서 실측 재현한 병합 볼륨
복원(union filter -> 실제 병합 볼륨 ~1.82, 해석값 1.875)을 seed 고정 24^3 grid 로
재확인한다. 대조군(단일 surface 필터 -> ~1.0)과 비교해 병합이 실제로 일어남을
함께 검증한다.
"""
from __future__ import annotations

import numpy as np
import pytest
from scipy.spatial import Delaunay

from core.generator.native_tet.boolean_merge import (
    UnionMergeResult,
    filter_tets_to_union,
)
from core.generator.native_tet.boundary_clip import clip_to_input_surface


def _unit_cube_mesh() -> tuple[np.ndarray, np.ndarray]:
    """[0,1]^3 축-정렬 cube 의 표면 (8 verts + 12 triangles)."""
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    F = np.array([
        [0, 2, 1], [0, 3, 2],   # bottom (z=0)
        [4, 5, 6], [4, 6, 7],   # top (z=1)
        [0, 1, 5], [0, 5, 4],   # front (y=0)
        [2, 3, 7], [2, 7, 6],   # back  (y=1)
        [1, 2, 6], [1, 6, 5],   # right (x=1)
        [0, 4, 7], [0, 7, 3],   # left  (x=0)
    ], dtype=np.int64)
    return V, F


def _cube_mesh(lo: float, hi: float) -> tuple[np.ndarray, np.ndarray]:
    """[lo, hi]^3 축-정렬 cube — _unit_cube_mesh 를 스케일/평행이동."""
    V, F = _unit_cube_mesh()
    return V * (hi - lo) + lo, F


def _background_tet_mesh(
    bbox_lo: np.ndarray, bbox_hi: np.ndarray, n: int, *, seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """union bbox 를 덮는 n^3 grid 위에 scipy Delaunay 로 tet 배경격자 생성.

    plan_boolmerge2.md 실험(정본 스크립트)과 동일한 방식 — 결정론적 seed 로
    작은 jitter 를 줘서 co-planar Delaunay 축퇴를 피한다.
    """
    rng = np.random.default_rng(seed)
    xs = np.linspace(bbox_lo[0], bbox_hi[0], n)
    ys = np.linspace(bbox_lo[1], bbox_hi[1], n)
    zs = np.linspace(bbox_lo[2], bbox_hi[2], n)
    gx, gy, gz = np.meshgrid(xs, ys, zs, indexing="ij")
    pts = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)
    cell = (bbox_hi[0] - bbox_lo[0]) / max(n - 1, 1)
    jitter = rng.uniform(-1, 1, size=pts.shape) * cell * 1e-4
    pts = pts + jitter
    tets = Delaunay(pts).simplices
    return pts, np.asarray(tets, dtype=np.int64)


def _two_region_background_tet_mesh(
    lo_a: float, hi_a: float, lo_b: float, hi_b: float, n: int, *, seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """두 큐브 각각 주변만 fine grid 로 채우고 하나의 Delaunay 호출로 결합.

    disjoint 케이스에서 전체 bbox(gap 포함)를 균일 grid 로 덮으면 cube 크기(1)
    대비 셀 크기가 너무 커져 volume 오차가 커진다. 대신 각 cube 주변만 조밀한
    local grid 로 채우되, 두 점군을 하나의 Delaunay 호출로 묶어 convex hull
    전체(= gap 포함)에 대한 tet 이 생성되게 한다 -- gap 을 잇는 큰 tet 의
    centroid 는 두 surface 모두에서 멀어 union 판정에서 자연히 제외되어야 한다.
    """
    rng = np.random.default_rng(seed)

    def _local_grid(lo: float, hi: float, pad: float) -> np.ndarray:
        xs = np.linspace(lo - pad, hi + pad, n)
        gx, gy, gz = np.meshgrid(xs, xs, xs, indexing="ij")
        return np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)

    pad = (hi_a - lo_a) * 0.1
    pts_a = _local_grid(lo_a, hi_a, pad)
    pts_b = _local_grid(lo_b, hi_b, pad)
    pts = np.concatenate([pts_a, pts_b], axis=0)

    cell = (hi_a - lo_a) / max(n - 1, 1)
    jitter = rng.uniform(-1, 1, size=pts.shape) * cell * 1e-4
    pts = pts + jitter
    tets = Delaunay(pts).simplices
    return pts, np.asarray(tets, dtype=np.int64)


def test_overlapping_cubes_union_volume_recovers_analytic() -> None:
    """A=[0,1]^3, B=[0.5,1.5]^3 -- union volume_after 가 해석값 1.875 근방."""
    V_a, F_a = _cube_mesh(0.0, 1.0)
    V_b, F_b = _cube_mesh(0.5, 1.5)
    surfaces = [(V_a, F_a), (V_b, F_b)]

    bbox_lo = np.array([-0.1, -0.1, -0.1])
    bbox_hi = np.array([1.6, 1.6, 1.6])
    pts, tets = _background_tet_mesh(bbox_lo, bbox_hi, n=24, seed=42)

    _, kept, result = filter_tets_to_union(pts, tets, surfaces)

    assert isinstance(result, UnionMergeResult)
    assert 1.70 <= result.volume_after <= 2.05, (
        f"volume_after={result.volume_after:.4f} outside [1.70, 2.05]"
    )

    # 대조군: 단일 surface(A) 만 필터하면 volume ~= 1.0 (병합 없음).
    _, _, single_result = filter_tets_to_union(pts, tets, [(V_a, F_a)])
    assert result.volume_after >= single_result.volume_after + 0.5, (
        f"union volume {result.volume_after:.4f} vs single-surface "
        f"{single_result.volume_after:.4f} -- merge did not happen"
    )

    assert result.n_tets_after < result.n_tets_before
    assert result.n_tets_after > 0
    assert kept.shape[0] == result.n_tets_after


def test_disjoint_cubes_no_tets_kept_in_gap() -> None:
    """A=[0,1]^3, B=[10,11]^3 -- volume_after ~= 2.0, 사이 gap 은 keep 되지 않는다."""
    V_a, F_a = _cube_mesh(0.0, 1.0)
    V_b, F_b = _cube_mesh(10.0, 11.0)
    surfaces = [(V_a, F_a), (V_b, F_b)]

    # 각 cube 주변만 조밀한 local grid, 하나의 Delaunay 로 결합(gap-bridging tet 포함).
    pts, tets = _two_region_background_tet_mesh(0.0, 1.0, 10.0, 11.0, n=18, seed=7)

    _, kept, result = filter_tets_to_union(pts, tets, surfaces)

    analytic = 2.0
    rel_err = abs(result.volume_after - analytic) / analytic
    assert rel_err <= 0.05, (
        f"volume_after={result.volume_after:.4f} vs analytic {analytic} "
        f"(rel_err={rel_err:.4f})"
    )

    # gap 영역([1.5, 9.5]^3 근방) centroid 를 갖는 tet 은 keep 되지 않아야 한다.
    kept_centroids = pts[kept].mean(axis=1)
    gap_mask = (
        (kept_centroids[:, 0] > 2.0) & (kept_centroids[:, 0] < 9.0)
        & (kept_centroids[:, 1] > 2.0) & (kept_centroids[:, 1] < 9.0)
        & (kept_centroids[:, 2] > 2.0) & (kept_centroids[:, 2] < 9.0)
    )
    assert not gap_mask.any(), "gap 영역 tet 이 keep 됨 -- union 판정 오류"


def test_single_surface_matches_boundary_clip() -> None:
    """surfaces=[(V,F)] 단일 케이스 -- boundary_clip.clip_to_input_surface 와 volume 일치.

    filter_tets_to_union 은 inside_union_winding_number(내부적으로 generalized
    winding number) 를, clip_to_input_surface 는 inside_winding_number(ray
    parity) 를 쓴다 -- 알고리즘은 다르지만 단일 axis-aligned cube 에서는 동일
    volume 으로 수렴해야 한다(1-surface 경로 무손상 보장).
    """
    V, F = _unit_cube_mesh()
    bbox_lo = np.array([-0.1, -0.1, -0.1])
    bbox_hi = np.array([1.1, 1.1, 1.1])
    pts, tets = _background_tet_mesh(bbox_lo, bbox_hi, n=12, seed=1)

    _, kept_union, result = filter_tets_to_union(pts, tets, [(V, F)])
    _, kept_clip, clip_result = clip_to_input_surface(pts, tets, V, F)

    from core.generator.native_tet.validate import signed_volume6

    clip_volume = float(np.abs(signed_volume6(pts, kept_clip)).sum() / 6.0)

    assert result.volume_after > 0.0
    assert clip_volume > 0.0
    rel_err = abs(result.volume_after - clip_volume) / clip_volume
    assert rel_err <= 0.02, (
        f"union-filter volume={result.volume_after:.6f} vs boundary_clip "
        f"volume={clip_volume:.6f} (rel_err={rel_err:.4f})"
    )
    # sign/scale 도 sanity-check -- 둘 다 unit cube 부피(~1.0) 근방이어야 한다.
    assert 0.7 <= result.volume_after <= 1.3
    assert 0.7 <= clip_volume <= 1.3


def test_non_union_classification_failure_is_fail_closed(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.generator.native_tet.mesher as mesher

    V, F = _unit_cube_mesh()

    def _raise(*_args, **_kwargs):
        raise RuntimeError("synthetic classifier failure")

    monkeypatch.setattr(mesher, "_inside_boolean_inputs", _raise)
    result = mesher.generate_native_tet(
        V,
        F,
        tmp_path / "case",
        target_edge_length=0.5,
        boolean_input_paths=["a.stl", "b.stl"],
        boolean_operation="intersection",
    )

    assert result.success is False
    assert "boolean intersection classification failed" in result.message
    assert "synthetic classifier failure" in result.message
