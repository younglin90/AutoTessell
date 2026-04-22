"""core/preprocessor/native_repair/ 자체 L1 repair 회귀 테스트.

각 단계별 유닛 + 통합 run_native_repair 파이프라인. pymeshfix 과는 직접 parity 를
요구하지 않고 "합리적 개선" (정상 입력 불변 / 중복 제거 / non-manifold 제거) 을
검증한다.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.analyzer import topology as T
from core.analyzer.readers import read_stl
from core.preprocessor.native_repair import (
    NativeRepairResult,
    dedup_vertices,
    fill_small_holes,
    fix_face_winding,
    remove_degenerate_faces,
    remove_non_manifold_faces,
    run_native_repair,
)


_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"
BROKEN_SPHERE = _REPO / "tests" / "benchmarks" / "broken_sphere.stl"


# ---------------------------------------------------------------------------
# dedup_vertices
# ---------------------------------------------------------------------------


def test_dedup_merges_exact_duplicates() -> None:
    V = np.array([
        [0, 0, 0], [0, 0, 0],   # duplicate
        [1, 0, 0], [0, 1, 0],
    ], dtype=np.float64)
    F = np.array([[0, 2, 3], [1, 2, 3]], dtype=np.int64)
    V2, F2, n = dedup_vertices(V, F)
    assert n == 1
    assert V2.shape[0] == 3
    # F2 에서 둘 다 vertex 0 으로 리매핑 → face 두 개 identical
    assert (F2[0] == F2[1]).all()


def test_dedup_no_op_on_unique() -> None:
    """n_merged=0, vertex/face 수 유지. np.unique 가 lexicographic 정렬로 순서를
    바꾸더라도 face 를 재해석하면 결과 메쉬는 동일해야 한다 — face 를 V2 로
    인덱싱한 좌표가 원본과 같은지 검증."""
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    F = np.array([[0, 1, 2]], dtype=np.int64)
    V2, F2, n = dedup_vertices(V, F)
    assert n == 0
    assert V2.shape[0] == V.shape[0]
    assert F2.shape == F.shape
    # 원본 face 좌표 vs 재인덱싱 face 좌표가 같은 set 이어야 함
    orig_tri_coords = np.sort(V[F[0]], axis=0)
    new_tri_coords = np.sort(V2[F2[0]], axis=0)
    np.testing.assert_array_equal(orig_tri_coords, new_tri_coords)


def test_dedup_preserves_face_shape() -> None:
    """v0.4: numpy 2.x 에서 inverse 가 (V, 1) 로 올 때도 face shape 을 (F, 3) 유지."""
    V = np.random.RandomState(0).rand(10, 3)
    F = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
    V2, F2, _ = dedup_vertices(V, F)
    assert F2.shape == (2, 3)


# ---------------------------------------------------------------------------
# remove_degenerate_faces
# ---------------------------------------------------------------------------


def test_remove_zero_area_faces() -> None:
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    # degenerate: 세 vertex 가 일직선 (면적 0)
    F = np.array([
        [0, 1, 2],           # 정상
        [0, 0, 1],           # degenerate (중복 vertex)
    ], dtype=np.int64)
    F2, n = remove_degenerate_faces(V, F)
    assert n == 1
    assert F2.shape[0] == 1


def test_remove_duplicate_faces() -> None:
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float64)
    F = np.array([
        [0, 1, 2],
        [1, 2, 0],  # 정렬시 같은 vertex set → 중복
        [0, 1, 3],
    ], dtype=np.int64)
    F2, n = remove_degenerate_faces(V, F)
    assert n == 1
    assert F2.shape[0] == 2


# ---------------------------------------------------------------------------
# remove_non_manifold_faces
# ---------------------------------------------------------------------------


def test_remove_non_manifold_edge() -> None:
    # edge (0,1) 을 3 face 공유 (book-like non-manifold)
    F = np.array([
        [0, 1, 2],
        [0, 1, 3],
        [0, 1, 4],
    ], dtype=np.int64)
    F2, n = remove_non_manifold_faces(F)
    assert n >= 1
    # 제거 후 edge (0,1) 은 <= 2 face 공유
    assert T.is_edge_manifold(F2)


# ---------------------------------------------------------------------------
# fix_face_winding
# ---------------------------------------------------------------------------


def test_fix_winding_flips_inconsistent_neighbour() -> None:
    # 삼각형 두 개가 공통 edge (0,1) 공유 — 하나는 winding (0,1,2), 다른 하나는
    # (0,1,3) (동일 방향 → non-consistent).
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, -1, 0]], dtype=np.float64)
    F = np.array([[0, 1, 2], [0, 1, 3]], dtype=np.int64)
    F2, nflip = fix_face_winding(V, F)
    assert nflip >= 1
    # after fix: 두 face 의 공통 edge 가 반대 방향으로 나타나야 함.
    dirs_f0 = {(F2[0, 0], F2[0, 1]), (F2[0, 1], F2[0, 2]), (F2[0, 2], F2[0, 0])}
    dirs_f1 = {(F2[1, 0], F2[1, 1]), (F2[1, 1], F2[1, 2]), (F2[1, 2], F2[1, 0])}
    # 공통 edge (0,1) or (1,0) 중 서로 반대 방향 존재
    shared_edges = [(0, 1), (1, 0)]
    has_opposite = any(
        e in dirs_f0 and (e[1], e[0]) in dirs_f1 for e in shared_edges
    )
    assert has_opposite


# ---------------------------------------------------------------------------
# fill_small_holes
# ---------------------------------------------------------------------------


def test_fill_small_hole_in_triangle_gap() -> None:
    # 사각형 frame 에서 중심 3 vertex 삼각형이 빠진 구멍
    # 다섯 vertex: 외곽 4 + 중심 1 missing.
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0.5, 0.5, 0],
    ], dtype=np.float64)
    # 중심 vertex 를 포함하는 4 triangles 중 1 개가 빠진 상태 → hole edge 는
    # 3 directed edges.
    F = np.array([
        [0, 1, 4],
        [1, 2, 4],
        [2, 3, 4],
        # (3, 0, 4) 누락
    ], dtype=np.int64)
    F2, n_added = fill_small_holes(V, F, max_boundary=10)
    # 최소 1 face 추가되어야 함 (hole 메움)
    assert n_added >= 1
    assert F2.shape[0] >= F.shape[0] + 1


# ---------------------------------------------------------------------------
# run_native_repair (integrated)
# ---------------------------------------------------------------------------


def test_run_native_repair_on_valid_sphere_is_no_change() -> None:
    """정상 sphere → watertight/manifold 유지, face 수 크게 변하지 않음."""
    if not SPHERE_STL.exists():
        pytest.skip("sphere.stl 없음")
    m = read_stl(SPHERE_STL)
    r = run_native_repair(m.vertices, m.faces)
    assert isinstance(r, NativeRepairResult)
    assert r.watertight is True
    assert r.manifold is True
    # face 수는 보존 (정상 메쉬는 변동 없어야 함)
    assert r.faces.shape[0] == m.n_faces


def test_run_native_repair_on_broken_does_not_crash() -> None:
    """broken_sphere 가 있으면 repair 호출이 예외 없이 완료."""
    if not BROKEN_SPHERE.exists():
        pytest.skip("broken_sphere.stl 없음")
    m = read_stl(BROKEN_SPHERE)
    r = run_native_repair(m.vertices, m.faces)
    assert r.faces.shape[0] > 0
    # hole_fill 이 최소 한 번 실행되어 face 가 증가했을 것
    steps_by = {s["step"]: s for s in r.steps}
    assert "fill_small_holes" in steps_by


def test_run_native_repair_steps_recorded() -> None:
    """5 단계가 steps 배열에 기록된다."""
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    r = run_native_repair(m.vertices, m.faces)
    step_names = {s["step"] for s in r.steps}
    assert step_names == {
        "dedup_vertices",
        "remove_degenerate_faces",
        "remove_non_manifold_faces",
        "fill_small_holes",
        "fix_face_winding",
    }
