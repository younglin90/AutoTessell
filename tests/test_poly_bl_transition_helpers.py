"""beta59 — poly_bl_transition 의 _merge_vertices / PolyBLResult 회귀.

_merge_vertices 는 두 vertex 집합을 좌표 quantize 후 dedup 하여 합치는 routine 으로
tet→poly dual 변환에서 prism + dual vertex 병합에 사용된다. 기존 테스트는 cell
classification 만 다루므로 여기선 vertex merging 의 경계 조건을 별도로 고정한다.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.layers.poly_bl_transition import PolyBLResult, _merge_vertices


# ---------------------------------------------------------------------------
# PolyBLResult defaults
# ---------------------------------------------------------------------------


def test_poly_bl_result_defaults() -> None:
    r = PolyBLResult(success=True, elapsed=0.5)
    assert r.n_prism_cells == 0
    assert r.bulk_dual_applied is False
    assert r.message == ""


def test_poly_bl_result_override() -> None:
    r = PolyBLResult(
        success=False, elapsed=1.0,
        n_prism_cells=128, bulk_dual_applied=True, message="done",
    )
    assert r.success is False
    assert r.n_prism_cells == 128
    assert r.bulk_dual_applied is True
    assert r.message == "done"


# ---------------------------------------------------------------------------
# _merge_vertices
# ---------------------------------------------------------------------------


def test_merge_vertices_no_overlap() -> None:
    """두 집합에 공유 좌표 없음 → combined 에 모두 포함, remap 단조 증가."""
    orig = np.array([[0, 0, 0], [1, 0, 0]], dtype=np.float64)
    dual = np.array([[5, 5, 5], [7, 7, 7]], dtype=np.float64)
    V, r_o, r_d = _merge_vertices(orig, dual)
    assert V.shape == (4, 3)
    # 모든 remap 값이 [0, 4) 범위
    assert set(r_o.tolist()) | set(r_d.tolist()) == {0, 1, 2, 3}
    assert len(set(r_o.tolist()) & set(r_d.tolist())) == 0


def test_merge_vertices_exact_shared() -> None:
    """orig 과 dual 이 같은 좌표 하나 공유 → combined 크기 감소."""
    orig = np.array([[0, 0, 0], [1, 0, 0]], dtype=np.float64)
    dual = np.array([[1, 0, 0], [2, 0, 0]], dtype=np.float64)
    V, r_o, r_d = _merge_vertices(orig, dual)
    # orig[1] == dual[0] → dedup → 3 vertex
    assert V.shape == (3, 3)
    # 공유 인덱스 일치
    assert r_o[1] == r_d[0]


def test_merge_vertices_within_tol() -> None:
    """tol 내에서 동일하다고 판정 (default tol=1e-9 → 같은 quantized key)."""
    orig = np.array([[1.0, 0.0, 0.0]], dtype=np.float64)
    dual = np.array([[1.0 + 1e-12, 0.0, 0.0]], dtype=np.float64)  # < tol
    V, r_o, r_d = _merge_vertices(orig, dual)
    assert V.shape == (1, 3)
    assert r_o[0] == r_d[0]


def test_merge_vertices_beyond_tol() -> None:
    """tol 보다 큰 차이 → 별도 vertex."""
    orig = np.array([[1.0, 0.0, 0.0]], dtype=np.float64)
    dual = np.array([[1.001, 0.0, 0.0]], dtype=np.float64)
    V, r_o, r_d = _merge_vertices(orig, dual)
    assert V.shape == (2, 3)
    assert r_o[0] != r_d[0]


def test_merge_vertices_custom_tol() -> None:
    """더 관대한 tol 에서는 가까운 점이 같은 index 로 묶임."""
    orig = np.array([[1.0, 0.0, 0.0]], dtype=np.float64)
    dual = np.array([[1.0005, 0.0, 0.0]], dtype=np.float64)
    V, r_o, r_d = _merge_vertices(orig, dual, tol=1e-2)
    assert V.shape == (1, 3)
    assert r_o[0] == r_d[0]


def test_merge_vertices_empty_inputs() -> None:
    orig = np.zeros((0, 3), dtype=np.float64)
    dual = np.zeros((0, 3), dtype=np.float64)
    V, r_o, r_d = _merge_vertices(orig, dual)
    assert V.shape == (0, 3)
    assert r_o.shape == (0,)
    assert r_d.shape == (0,)


def test_merge_vertices_remap_preserves_uniqueness() -> None:
    """서로 다른 orig 점은 반드시 서로 다른 combined index 로 매핑."""
    orig = np.array([[i, 0, 0] for i in range(10)], dtype=np.float64)
    dual = np.zeros((0, 3), dtype=np.float64)
    V, r_o, _ = _merge_vertices(orig, dual)
    assert V.shape == (10, 3)
    assert len(set(r_o.tolist())) == 10


def test_merge_vertices_returns_int64() -> None:
    """remap dtype 이 int64 고정 (polyMesh 호환)."""
    orig = np.array([[0, 0, 0]], dtype=np.float64)
    dual = np.array([[1, 0, 0]], dtype=np.float64)
    _, r_o, r_d = _merge_vertices(orig, dual)
    assert r_o.dtype == np.int64
    assert r_d.dtype == np.int64


def test_merge_vertices_combined_preserves_coordinates() -> None:
    """combined 에 원본 좌표가 (dedup 후) 정확히 보존된다."""
    orig = np.array([[2.5, -1.0, 3.3]], dtype=np.float64)
    dual = np.array([[-7.0, 8.0, 0.5]], dtype=np.float64)
    V, r_o, r_d = _merge_vertices(orig, dual)
    np.testing.assert_allclose(V[r_o[0]], [2.5, -1.0, 3.3], atol=1e-8)
    np.testing.assert_allclose(V[r_d[0]], [-7.0, 8.0, 0.5], atol=1e-8)
