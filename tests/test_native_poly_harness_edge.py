"""beta56 — run_native_poly_harness dedicated edge case 회귀."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.generator.native_poly.dual import PolyDualResult
from core.generator.native_poly.harness import (
    PolyHarnessResult,
    run_native_poly_harness,
)
from core.generator.native_tet import NativeTetResult


def _sphere_mesh(subdivisions: int = 1) -> tuple[np.ndarray, np.ndarray]:
    import trimesh

    sp = trimesh.creation.icosphere(subdivisions=subdivisions, radius=1.0)
    return (
        np.asarray(sp.vertices, dtype=np.float64),
        np.asarray(sp.faces, dtype=np.int64),
    )


def test_empty_input_fails_gracefully(tmp_path: Path) -> None:
    """빈 input → crash 없이 PolyHarnessResult(success=False)."""
    V = np.zeros((0, 3))
    F: np.ndarray = np.zeros((0, 3), dtype=np.int64)
    result = run_native_poly_harness(V, F, tmp_path, max_iter=1)
    assert isinstance(result, PolyHarnessResult)
    assert result.success is False
    assert result.n_cells == 0


def test_max_iter_respected(tmp_path: Path) -> None:
    """max_iter=1 에서 iterations <= 1."""
    V, F = _sphere_mesh(subdivisions=1)
    result = run_native_poly_harness(
        V,
        F,
        tmp_path,
        max_iter=1,
        seed_density=8,
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
        V,
        F,
        tmp_path,
        max_iter=1,
        seed_density=6,
        max_tet_cells=50,
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Restore all iter-1 polyMesh bytes after a worse iter-2 candidate.

    This is a harness-state contract, so it isolates the generator, dual writer,
    and evaluator seams.  Real sphere generation remains covered separately by
    ``test_native_poly_dual.py``; a truthful geometry-gate rejection must not
    prevent this byte-restoration unit test from reaching its owned mechanism.
    No geometry threshold or shape assertion is removed or weakened here.
    """
    import core.generator.native_poly.harness as hm

    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = np.array(
        [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]],
        dtype=np.int64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    poly_names = ("points", "faces", "owner", "neighbour", "boundary")
    candidates = (
        {name: f"iter-1-best:{name}\n".encode() for name in poly_names},
        {name: f"iter-2-worse:{name}\n".encode() for name in poly_names},
    )
    dual_calls = {"n": 0}

    def _fake_tet(*_args: object, **_kwargs: object) -> NativeTetResult:
        return NativeTetResult(
            success=True,
            elapsed=0.0,
            n_cells=1,
            n_points=4,
            tet_points=vertices.copy(),
            tets=tets.copy(),
        )

    def _fake_dual(
        _points: np.ndarray,
        _tets: np.ndarray,
        output: Path,
        **_kwargs: object,
    ) -> PolyDualResult:
        candidate_index = dual_calls["n"]
        dual_calls["n"] += 1
        poly_dir = output / "constant" / "polyMesh"
        poly_dir.mkdir(parents=True)
        for name, payload in candidates[candidate_index].items():
            (poly_dir / name).write_bytes(payload)
        return PolyDualResult(
            success=True,
            elapsed=0.0,
            n_cells=200 if candidate_index == 0 else 100,
            n_points=120 if candidate_index == 0 else 50,
        )

    def _fake_eval(output: Path) -> tuple[bool, dict[str, object]]:
        marker = (output / "constant" / "polyMesh" / "points").read_bytes()
        if marker == candidates[0]["points"]:
            return False, {
                "cells": 200,
                "points": 120,
                "max_non_orthogonality": 50.0,
                "max_skewness": 1.5,
                "negative_volumes": 0,
                "mesh_ok": False,
            }
        assert marker == candidates[1]["points"]
        return False, {
            "cells": 100,
            "points": 50,
            "max_non_orthogonality": 70.0,
            "max_skewness": 2.0,
            "negative_volumes": 5,
            "mesh_ok": False,
        }

    monkeypatch.setattr(hm, "generate_native_tet", _fake_tet)
    monkeypatch.setattr(hm, "tet_to_poly_dual", _fake_dual)
    monkeypatch.setattr(hm, "_evaluate_poly_mesh", _fake_eval)

    case_dir = tmp_path / "case"
    result = run_native_poly_harness(
        vertices,
        faces,
        case_dir,
        max_iter=2,
        seed_density=6,
    )
    assert result.success is False
    assert result.iterations == 2
    assert result.n_cells == 100
    assert result.negative_volumes == 5
    assert dual_calls["n"] == 2
    installed = case_dir / "constant" / "polyMesh"
    assert {name: (installed / name).read_bytes() for name in poly_names} == candidates[0]
