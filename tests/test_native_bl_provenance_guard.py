"""Native boundary-layer lineage and zero-layer contract regressions."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from core.evaluator.native_checker import NativeMeshChecker
from core.generator.polymesh_writer import write_generic_polymesh
from core.layers.native_bl import BLConfig, generate_native_bl
from core.layers.poly_bl_transition import run_poly_bl_transition
from core.utils.polymesh_reader import parse_foam_points

_TET_POINTS = np.array(
    [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ],
    dtype=np.float64,
)
_TET_FACES = [[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]]


def _write_single_tet(case_dir: Path) -> None:
    write_generic_polymesh(
        _TET_POINTS,
        [[list(face) for face in _TET_FACES]],
        case_dir,
        patch_name="wall",
        patch_type="wall",
    )


def _snapshot(case_dir: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(case_dir)): path.read_bytes()
        for path in sorted(case_dir.rglob("*"))
        if path.is_file()
    }


def _stable_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_TESSELL_BL_VD_ENABLE", "0")
    monkeypatch.delenv("AUTO_TESSELL_BL_VD_FOR", raising=False)
    monkeypatch.setenv("AUTO_TESSELL_BL_ASPECT_ENFORCE", "0")
    monkeypatch.setenv("AUTO_TESSELL_BL_ANTI_INVERT_CAP", "0")
    monkeypatch.setenv("AUTO_TESSELL_BL_ANISO_SPLIT", "0")
    monkeypatch.setenv("AUTO_TESSELL_BL_ANISO_SPLIT_DIAG", "0")
    monkeypatch.setenv("AUTO_TESSELL_BL_INNER_SMOOTH", "0")


def _assert_original_surface_coordinates_remain(case_dir: Path) -> None:
    output = np.asarray(
        parse_foam_points(case_dir / "constant" / "polyMesh" / "points"),
        dtype=np.float64,
    )
    for expected in _TET_POINTS:
        assert np.any(np.all(np.isclose(output, expected, atol=1e-12), axis=1))


def test_single_transition_records_lineage_and_preserves_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_single_tet(tmp_path)
    _stable_environment(monkeypatch)

    result = run_poly_bl_transition(
        tmp_path,
        num_layers=2,
        growth_ratio=1.2,
        first_thickness=0.01,
        backup_original=False,
        apply_bulk_dual=False,
    )

    assert result.success, result.message
    assert result.n_prism_cells == 8
    state = json.loads((tmp_path / "native_bl_state.json").read_text())
    assert state["state"] == "completed"
    assert state["requested_layers"] == 2
    assert state["actual_layers"] == 2
    assert state["last_transform"] == "poly_bl_transition"
    assert state["input_polymesh_sha256"] != state["output_polymesh_sha256"]
    _assert_original_surface_coordinates_remain(tmp_path)
    assert NativeMeshChecker().run(tmp_path).negative_volumes == 0


def test_direct_pre_layered_input_is_rejected_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_single_tet(tmp_path)
    _stable_environment(monkeypatch)
    first = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=2,
            growth_ratio=1.2,
            first_thickness=0.01,
            backup_original=False,
        ),
    )
    assert first.success, first.message
    before = _snapshot(tmp_path)

    second = run_poly_bl_transition(
        tmp_path,
        num_layers=2,
        growth_ratio=1.2,
        first_thickness=0.01,
        backup_original=False,
        apply_bulk_dual=False,
    )

    assert not second.success
    assert "pre_layered_input" in second.message
    assert _snapshot(tmp_path) == before


def test_second_transition_is_rejected_after_post_transform_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_single_tet(tmp_path)
    _stable_environment(monkeypatch)
    first = run_poly_bl_transition(
        tmp_path,
        num_layers=1,
        growth_ratio=1.1,
        first_thickness=0.01,
        backup_original=False,
        apply_bulk_dual=True,
    )
    assert first.success, first.message
    before = _snapshot(tmp_path)

    second = run_poly_bl_transition(
        tmp_path,
        num_layers=1,
        growth_ratio=1.1,
        first_thickness=0.01,
        backup_original=False,
        apply_bulk_dual=True,
    )

    assert not second.success
    assert "pre_layered_input" in second.message
    assert _snapshot(tmp_path) == before


def test_zero_layers_is_exact_no_op(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_single_tet(tmp_path)
    _stable_environment(monkeypatch)
    before = _snapshot(tmp_path)

    result = run_poly_bl_transition(
        tmp_path,
        num_layers=0,
        growth_ratio=0.0,
        first_thickness=0.0,
        apply_bulk_dual=True,
    )

    assert result.success, result.message
    assert result.n_prism_cells == 0
    assert not result.bulk_dual_applied
    assert _snapshot(tmp_path) == before


def test_negative_layers_fails_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_single_tet(tmp_path)
    _stable_environment(monkeypatch)
    before = _snapshot(tmp_path)

    result = run_poly_bl_transition(
        tmp_path,
        num_layers=-1,
        growth_ratio=1.2,
        first_thickness=0.01,
    )

    assert not result.success
    assert _snapshot(tmp_path) == before


def test_zero_layers_cannot_remove_existing_layers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_single_tet(tmp_path)
    _stable_environment(monkeypatch)
    first = run_poly_bl_transition(
        tmp_path,
        num_layers=1,
        growth_ratio=1.1,
        first_thickness=0.01,
        backup_original=False,
        apply_bulk_dual=False,
    )
    assert first.success, first.message
    before = _snapshot(tmp_path)

    zero = run_poly_bl_transition(
        tmp_path,
        num_layers=0,
        growth_ratio=1.0,
        first_thickness=0.01,
    )

    assert not zero.success
    assert "zero_layer_request_on_pre_layered_input" in zero.message
    assert _snapshot(tmp_path) == before
