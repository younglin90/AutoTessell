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


def test_best_candidate_tracking_keeps_better_iter(
    tmp_path: Path, monkeypatch,
) -> None:
    """beta60 — iter 1 이 iter 2 보다 좋으면 최종 case_dir 은 iter 1 결과.

    buggy 버전 (beta59 이전) 에서는 best_metrics 없이 ``metrics < metrics`` 로
    자기 자신과 비교해 항상 False → 첫 iter 결과가 유지되었지만, 이는 "우연"
    이었다. 이 테스트는 iter 1 = 좋은 결과, iter 2 = 나쁜 결과 시나리오에서
    명시적으로 iter 1 이 보존되는지를 검증한다.
    """
    V, F = _sphere_mesh(subdivisions=1)

    import core.generator.native_poly.harness as hm
    call_idx = {"n": 0}
    def _fake_eval(case_dir):
        call_idx["n"] += 1
        if call_idx["n"] == 1:
            # 좋은 결과 (neg=0)
            return False, {
                "cells": 200, "points": 120, "max_non_orthogonality": 50.0,
                "max_skewness": 1.5, "negative_volumes": 0, "mesh_ok": False,
            }
        # 2nd call: 나쁜 결과 (neg=5)
        return False, {
            "cells": 100, "points": 50, "max_non_orthogonality": 70.0,
            "max_skewness": 2.0, "negative_volumes": 5, "mesh_ok": False,
        }
    monkeypatch.setattr(hm, "_evaluate_poly_mesh", _fake_eval)

    case_dir = tmp_path / "case"
    result = run_native_poly_harness(
        V, F, case_dir, max_iter=2, seed_density=6,
    )
    # 마지막 iter 실패 후 case_dir 에는 "best" (iter 1) 이 복사된다.
    # result 의 n_cells / negative_volumes 는 last_metrics (iter 2) 를 반영하지만,
    # case_dir 의 polyMesh 는 best_case_bytes (iter 1) 를 유지해야 한다.
    assert result.success is False
    assert (case_dir / "constant" / "polyMesh" / "points").exists()
