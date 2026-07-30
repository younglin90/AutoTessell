"""Mandatory native-Poly validity admission before canonical writes."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import core.generator.native_poly.voronoi as voronoi
from core.generator.native_poly import NativePolyResult

_POINTS = np.asarray(
    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    dtype=np.float64,
)
_VALID_CELL = [[[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]]
_INVALID_CELL = [[list(reversed(face)) for face in _VALID_CELL[0]]]
_SURFACE_FACES = np.asarray(_VALID_CELL[0], dtype=np.int64)


def _snapshot(path: Path) -> dict[str, bytes]:
    if not path.exists():
        return {}
    return {
        str(item.relative_to(path)): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def test_invalid_candidate_refuses_before_writer_and_preserves_existing_case(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "case"
    poly_dir = case_dir / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True)
    for name in ("points", "boundary", "neighbour", "faces", "owner"):
        (poly_dir / name).write_bytes(f"user-{name}".encode())
    (case_dir / "user-sentinel").write_bytes(b"keep-exact")
    before = _snapshot(case_dir)
    writer_calls = 0

    def fail_if_written(*_args: Any, **_kwargs: Any) -> dict[str, int]:
        nonlocal writer_calls
        writer_calls += 1
        raise AssertionError("invalid candidate must not reach writer")

    monkeypatch.setenv("AUTO_TESSELL_VAL2_OFF", "1")
    monkeypatch.setattr(voronoi, "_write_polymesh_poly", fail_if_written)

    outcome = voronoi._admit_and_write_polymesh_poly(
        _POINTS,
        _INVALID_CELL,
        case_dir,
        strict=False,
        started_at=time.perf_counter(),
    )

    assert writer_calls == 0
    assert outcome.stats is None
    assert outcome.refusal is not None
    assert outcome.refusal.failure_kind == "validity_refused"
    assert outcome.refusal.n_negative_volumes == 1
    assert outcome.refusal.n_degenerate_cells == 0
    assert _snapshot(case_dir) == before


def test_invalid_candidate_leaves_empty_case_artifact_free(tmp_path: Path) -> None:
    case_dir = tmp_path / "empty"

    outcome = voronoi._admit_and_write_polymesh_poly(
        _POINTS,
        _INVALID_CELL,
        case_dir,
        strict=False,
        started_at=time.perf_counter(),
    )

    assert outcome.refusal is not None
    assert not case_dir.exists()


def test_valid_candidate_writer_bytes_match_existing_writer(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    admitted = tmp_path / "admitted"

    voronoi._write_polymesh_poly(_POINTS, _VALID_CELL, baseline, strict=False)
    outcome = voronoi._admit_and_write_polymesh_poly(
        _POINTS,
        _VALID_CELL,
        admitted,
        strict=False,
        started_at=time.perf_counter(),
    )

    assert outcome.refusal is None
    assert outcome.stats is not None
    assert outcome.n_negative == 0
    assert outcome.n_degenerate == 0
    assert _snapshot(admitted) == _snapshot(baseline)
    poly_files = {name for name in _snapshot(admitted) if name.startswith("constant/polyMesh/")}
    assert poly_files == {
        "constant/polyMesh/boundary",
        "constant/polyMesh/faces",
        "constant/polyMesh/neighbour",
        "constant/polyMesh/owner",
        "constant/polyMesh/points",
    }


def test_public_auto_escalation_treats_validity_refusal_as_terminal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inner_calls = 0
    hex_calls = 0

    def refuse(*_args: Any, **_kwargs: Any) -> NativePolyResult:
        nonlocal inner_calls
        inner_calls += 1
        return NativePolyResult(
            False,
            0.0,
            message="native_poly_validity_refused: negative=1, degenerate=0",
            failure_kind="validity_refused",
            n_negative_volumes=1,
            n_degenerate_cells=0,
        )

    def unexpected_hex(*_args: Any, **_kwargs: Any) -> NativePolyResult:
        nonlocal hex_calls
        hex_calls += 1
        return NativePolyResult(False, 0.0, message="unexpected")

    monkeypatch.setattr(voronoi, "_generate_native_poly_voronoi_inner", refuse)
    monkeypatch.setattr(voronoi, "_hex_to_poly_fallback", unexpected_hex)

    result = voronoi.generate_native_poly_voronoi(
        _POINTS,
        _SURFACE_FACES,
        tmp_path,
        auto_escalate=True,
        auto_escalate_max=4,
        bl_layers=0,
    )

    assert result.failure_kind == "validity_refused"
    assert inner_calls == 1
    assert hex_calls == 0
    assert not (tmp_path / "constant" / "polyMesh").exists()
