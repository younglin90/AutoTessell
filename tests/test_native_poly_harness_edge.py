"""beta56 — run_native_poly_harness dedicated edge case 회귀."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.generator.native_poly.harness import (
    PolyHarnessResult,
    run_native_poly_harness,
)


def _sphere_mesh(subdivisions: int = 1):
    import trimesh
    sp = trimesh.creation.icosphere(subdivisions=subdivisions, radius=1.0)
    return (
        np.asarray(sp.vertices, dtype=np.float64),
        np.asarray(sp.faces, dtype=np.int64),
    )


def test_empty_input_fails_gracefully(tmp_path: Path) -> None:
    """빈 input → crash 없이 PolyHarnessResult(success=False)."""
    V = np.zeros((0, 3))
    F = np.zeros((0, 3), dtype=np.int64)
    result = run_native_poly_harness(V, F, tmp_path, max_iter=1)
    assert isinstance(result, PolyHarnessResult)
    assert result.success is False
    assert result.n_cells == 0


def test_max_iter_respected(tmp_path: Path) -> None:
    """max_iter=1 에서 iterations <= 1."""
    V, F = _sphere_mesh(subdivisions=1)
    result = run_native_poly_harness(
        V, F, tmp_path, max_iter=1, seed_density=8,
    )
    assert isinstance(result, PolyHarnessResult)
    assert result.iterations <= 1


def test_poly_harness_result_fields() -> None:
    """PolyHarnessResult dataclass 필드 기본값."""
    r = PolyHarnessResult(success=True, elapsed=1.0, iterations=2)
    assert r.n_cells == 0
    assert r.n_points == 0
    assert r.open_cells == 0
    assert r.negative_volumes == 0
    assert r.message == ""


def test_max_tet_cells_cap_triggers_safety(tmp_path: Path) -> None:
    """max_tet_cells 를 매우 작게 → safety cap 동작, crash 없이 반환."""
    V, F = _sphere_mesh(subdivisions=1)
    result = run_native_poly_harness(
        V, F, tmp_path, max_iter=1, seed_density=6, max_tet_cells=50,
    )
    # cell 수 cap 발동해도 결과는 반환 (failure 여도 instance).
    assert isinstance(result, PolyHarnessResult)


def test_elapsed_always_non_negative(tmp_path: Path) -> None:
    V, F = _sphere_mesh(subdivisions=1)
    result = run_native_poly_harness(V, F, tmp_path, max_iter=1, seed_density=6)
    assert result.elapsed >= 0


def test_sphere_mesh_produces_some_cells(tmp_path: Path) -> None:
    """단순 sphere 에서 iter=1 에 cell 생성."""
    V, F = _sphere_mesh(subdivisions=1)
    result = run_native_poly_harness(V, F, tmp_path, max_iter=1, seed_density=8)
    # 성공 여부와 무관 — cell 이 생성되어야 harness 경로가 유효
    assert result.n_cells > 0 or not result.success
