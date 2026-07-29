"""Focused regressions for native BL persistence and anti-invert safety."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import core.layers.native_bl as native_bl
from core.generator.polymesh_writer import write_generic_polymesh
from core.layers.aspect_cap_enforcer import AspectCapResult
from core.layers.native_bl import BLConfig, generate_native_bl
from core.utils.polymesh_reader import parse_foam_points


def _write_single_tet_case(case_dir: Path) -> np.ndarray:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    cell_faces = [
        [
            [0, 1, 2],
            [0, 3, 1],
            [1, 3, 2],
            [2, 3, 0],
        ]
    ]
    write_generic_polymesh(
        points,
        cell_faces,
        case_dir,
        patch_name="wall",
        patch_type="wall",
    )
    return points


def _set_stable_test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_TESSELL_BL_VD_ENABLE", "0")
    monkeypatch.delenv("AUTO_TESSELL_BL_VD_FOR", raising=False)
    monkeypatch.setenv("AUTO_TESSELL_BL_ANISO_SPLIT", "0")
    monkeypatch.setenv("AUTO_TESSELL_BL_ANISO_SPLIT_DIAG", "0")


def test_aspect_enforced_points_are_written_once_and_metrics_match_disk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_single_tet_case(tmp_path)
    _set_stable_test_environment(monkeypatch)
    monkeypatch.setenv("AUTO_TESSELL_BL_ASPECT_ENFORCE", "1")
    monkeypatch.setenv("AUTO_TESSELL_BL_ANTI_INVERT_CAP", "0")

    accepted: dict[str, np.ndarray] = {}
    stats_context: dict[str, Any] = {}
    write_calls: list[np.ndarray] = []
    real_stats = native_bl._prism_aspect_ratio_stats
    real_write_points = native_bl._write_points

    def fake_enforce(
        points: np.ndarray,
        prisms: np.ndarray,
        **_: Any,
    ) -> tuple[np.ndarray, AspectCapResult]:
        changed = points.copy()
        changed[int(prisms[0, 3]), 0] += 0.123456
        accepted["points"] = changed.copy()
        return changed, AspectCapResult(
            n_prisms=len(prisms),
            n_violations_pre=1,
            n_violations_post=0,
            aspect_max_pre=100.0,
            aspect_max_post=50.0,
            n_outer_modified=1,
        )

    def recording_stats(
        points: np.ndarray,
        wall_tri_verts: dict[int, tuple[int, int, int]],
        wall_face_indices: list[int],
        layer_point_ids: list[dict[int, int]],
        num_layers: int,
        *,
        threshold: float,
    ) -> tuple[int, float]:
        stats_context.update(
            wall_tri_verts=wall_tri_verts,
            wall_face_indices=wall_face_indices,
            layer_point_ids=layer_point_ids,
            num_layers=num_layers,
            threshold=threshold,
        )
        return real_stats(
            points,
            wall_tri_verts,
            wall_face_indices,
            layer_point_ids,
            num_layers,
            threshold=threshold,
        )

    def recording_write_points(path: Path, points: np.ndarray) -> None:
        write_calls.append(points.copy())
        real_write_points(path, points)

    monkeypatch.setattr(
        "core.layers.aspect_cap_enforcer.enforce_prism_aspect_cap_v2",
        fake_enforce,
    )
    monkeypatch.setattr(native_bl, "_prism_aspect_ratio_stats", recording_stats)
    monkeypatch.setattr(native_bl, "_write_points", recording_write_points)

    config = BLConfig(
        num_layers=1,
        first_thickness=0.05,
        collision_safety=False,
        feature_lock=False,
        backup_original=False,
        aspect_ratio_threshold=1.0,
    )
    result = generate_native_bl(tmp_path, config)

    assert result.success, result.message
    assert "points" in accepted
    assert len(write_calls) == 1
    disk_points = np.asarray(
        parse_foam_points(tmp_path / "constant" / "polyMesh" / "points"),
        dtype=np.float64,
    )
    np.testing.assert_allclose(disk_points, accepted["points"], atol=1e-8, rtol=0.0)
    np.testing.assert_allclose(write_calls[0], accepted["points"], atol=0.0, rtol=0.0)

    disk_n_degenerate, disk_max_aspect = real_stats(
        disk_points,
        stats_context["wall_tri_verts"],
        stats_context["wall_face_indices"],
        stats_context["layer_point_ids"],
        stats_context["num_layers"],
        threshold=stats_context["threshold"],
    )
    quality = json.loads((tmp_path / "native_bl_quality.json").read_text(encoding="utf-8"))
    assert result.n_degenerate_prisms == disk_n_degenerate
    assert result.max_aspect_ratio == pytest.approx(disk_max_aspect, rel=1e-7)
    assert quality["n_degenerate_prisms"] == disk_n_degenerate
    assert quality["max_aspect_ratio"] == pytest.approx(disk_max_aspect, rel=1e-7)


@pytest.mark.parametrize("joint_enabled", [False, True])
def test_anti_invert_cap_applies_in_both_joint_modes_and_floor_cannot_raise_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    joint_enabled: bool,
) -> None:
    original_points = _write_single_tet_case(tmp_path)
    _set_stable_test_environment(monkeypatch)
    monkeypatch.setenv("AUTO_TESSELL_BL_ASPECT_ENFORCE", "0")
    monkeypatch.setenv("AUTO_TESSELL_BL_ANTI_INVERT_CAP", "1")
    monkeypatch.setenv(
        "AUTO_TESSELL_BL_ANTI_INVERT_JOINT",
        "1" if joint_enabled else "0",
    )
    monkeypatch.setenv("AUTO_TESSELL_BL_ANTI_INVERT_GLOBAL", "1")
    monkeypatch.setenv("AUTO_TESSELL_BL_ANTI_INVERT_SELECTIVE", "0")
    monkeypatch.setenv("AUTO_TESSELL_BL_ANTI_INVERT_FLOOR", "0.5")

    safe_bound = 1.0e-3
    joint_calls = 0

    def fake_caps(
        _points: np.ndarray,
        _faces: list[list[int]],
        _owner: np.ndarray,
        _neighbour: np.ndarray,
        wall_vertices: list[int],
        _motion_dirs: dict[int, np.ndarray],
        *,
        safety_factor: float,
    ) -> dict[int, float]:
        assert safety_factor > 0.0
        return {int(vertex): safe_bound for vertex in wall_vertices}

    def fake_joint(*_: Any, **__: Any) -> float:
        nonlocal joint_calls
        joint_calls += 1
        return 0.5

    monkeypatch.setattr(
        "core.layers.native_bl_anti_invert.compute_anti_invert_caps",
        fake_caps,
    )
    monkeypatch.setattr(
        "core.layers.native_bl_anti_invert.compute_joint_cell_inversion_scale",
        fake_joint,
    )

    result = generate_native_bl(
        tmp_path,
        BLConfig(
            num_layers=1,
            first_thickness=0.05,
            collision_safety=False,
            feature_lock=False,
            quality_check_enabled=False,
            backup_original=False,
        ),
    )

    assert result.success, result.message
    assert joint_calls == int(joint_enabled)
    disk_points = np.asarray(
        parse_foam_points(tmp_path / "constant" / "polyMesh" / "points"),
        dtype=np.float64,
    )
    displacements = np.linalg.norm(
        disk_points[: len(original_points)] - original_points,
        axis=1,
    )
    assert np.max(displacements) > 0.0
    assert np.max(displacements) <= safe_bound + 1e-9

    quality = json.loads((tmp_path / "native_bl_quality.json").read_text(encoding="utf-8"))
    assert quality["anti_invert_cap"]["enabled"] is True
    assert quality["anti_invert_cap"]["n_capped"] == len(original_points)
    assert quality["anti_invert_cap"]["max_reduction"] > 0.0
