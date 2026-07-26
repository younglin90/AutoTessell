"""POLY-NO-DROP-HOLES1 topology, transaction, and route regressions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.generator import native_poly
from core.generator.native_poly import tet_to_poly_dual, voronoi
from core.generator.native_poly.quality import (
    capture_poly_mesh_contract,
    conservative_no_drop_repair,
    drop_degenerate_poly_cells,
    no_drop_holes1_enabled,
    verify_poly_mesh_contract,
)
from core.generator.polymesh_writer import write_generic_polymesh
from core.utils.polymesh_reader import parse_foam_boundary

_REPO = Path(__file__).resolve().parents[1]


def _one_bad_shared_face() -> tuple[np.ndarray, list[list[list[int]]]]:
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.5, 0.0, 0.0],
        ],
        dtype=np.float64,
    )
    good = [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]]
    bad = [[0, 1, 2], [0, 4, 1], [1, 4, 2], [2, 4, 0]]
    return vertices, [good, bad]


def _split_tetra() -> tuple[np.ndarray, list[list[list[int]]]]:
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1e-3, 1e-3, 1e-3],
        ],
        dtype=np.float64,
    )
    tets = [(4, 2, 1, 0), (4, 1, 3, 0), (4, 3, 2, 0), (4, 1, 2, 3)]

    def faces(tet: tuple[int, int, int, int]) -> list[list[int]]:
        a, b, c, d = tet
        return [[a, c, b], [a, b, d], [a, d, c], [b, c, d]]

    return vertices, [faces(tet) for tet in tets]


def _case_snapshot(case_dir: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(case_dir)): path.read_bytes()
        for path in sorted(item for item in case_dir.rglob("*") if item.is_file())
    }


def test_legacy_drop_manufactures_boundary_from_shared_face() -> None:
    vertices, cells = _one_bad_shared_face()
    kept, n_drop = drop_degenerate_poly_cells(vertices, cells)

    shared_key = tuple(sorted((0, 1, 2)))
    raw_refs = [
        cell_index
        for cell_index, cell in enumerate(cells)
        if any(tuple(sorted(face)) == shared_key for face in cell)
    ]
    kept_refs = [
        cell_index
        for cell_index, cell in enumerate(kept)
        if any(tuple(sorted(face)) == shared_key for face in cell)
    ]

    assert n_drop == 1
    assert raw_refs == [0, 1]
    assert kept_refs == [0]


def test_conservative_trial_rolls_back_when_quality_gate_fails() -> None:
    vertices, cells = _split_tetra()
    before = capture_poly_mesh_contract(vertices, cells)

    result = conservative_no_drop_repair(vertices, cells)
    after = capture_poly_mesh_contract(result.vertices, cells)

    assert result.accepted is False
    assert result.reason == "quality_regressed"
    assert result.n_bad_before == 3
    assert result.n_bad_after == 0
    assert np.array_equal(result.vertices, vertices)
    assert verify_poly_mesh_contract(before, after) == (True, "accepted")


def test_contract_preserves_two_patch_identity() -> None:
    vertices, cells = _split_tetra()
    baseline = capture_poly_mesh_contract(vertices, cells)
    labels = {key: ("upper" if 3 in key else "lower") for key in baseline.boundary_face_keys}

    snapshot = capture_poly_mesh_contract(
        vertices,
        cells,
        boundary_patch_by_face=labels,
    )

    assert {name for name, _keys in snapshot.patch_identity} == {"lower", "upper"}
    assert len(snapshot.boundary_components) == 1
    assert all(len(refs) in (1, 2) for _key, refs in snapshot.face_incidence)


def test_strict_python_writer_rejects_before_writing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from core.generator import polymesh_writer as writer

    vertices, cells = _one_bad_shared_face()
    monkeypatch.setattr(writer, "_NATIVE_POLYMESH", None)
    monkeypatch.setattr(writer, "_NATIVE_POLYMESH_IMPORT_ATTEMPTED", True)
    case_dir = tmp_path / "strict"

    with pytest.raises(ValueError, match="strict polyMesh contract"):
        write_generic_polymesh(vertices, cells, case_dir, strict=True)

    assert not case_dir.exists()


def test_strict_writer_keeps_two_boundary_patches(tmp_path: Path) -> None:
    vertices, cells = _split_tetra()

    def classifier(face: list[int], _points: np.ndarray) -> tuple[str, str]:
        return ("upper", "wall") if 3 in face else ("lower", "patch")

    write_generic_polymesh(
        vertices,
        cells,
        tmp_path,
        boundary_patch_classifier=classifier,
        strict=True,
    )

    patches = parse_foam_boundary(tmp_path / "constant/polyMesh/boundary")
    assert {patch["name"] for patch in patches} == {"lower", "upper"}
    assert sum(int(patch["nFaces"]) for patch in patches) == 4


def test_flag_default_off_and_legacy_writer_still_drops(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("AUTO_TESSELL_POLY_NO_DROP_HOLES1", raising=False)
    vertices, cells = _one_bad_shared_face()

    assert no_drop_holes1_enabled() is False
    stats = write_generic_polymesh(vertices, cells, tmp_path)
    assert stats["num_cells"] == 1


def test_direct_scipy_no_drop_real_smoke(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AUTO_TESSELL_POLY_NO_DROP_HOLES1", "1")
    cases = (("cube", False, 0), ("cylinder", False, 0), ("sphere", True, 36))
    for shape, expect_success, expected_cells in cases:
        mesh = read_stl(_REPO / "tests" / "benchmarks" / f"{shape}.stl")
        result = voronoi.generate_native_poly_voronoi(
            mesh.vertices,
            mesh.faces,
            tmp_path / shape,
            seed_density=8,
            n_lloyd=0,
            auto_escalate=False,
            prefer_hex_for_budget=False,
            bl_layers=0,
        )

        assert result.success is expect_success
        assert result.n_cells == expected_cells
        if not expect_success:
            assert "strict polyMesh contract" in result.message


def test_canonical_polydual_fixed_primal_is_flag_noop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.3, 0.3, 1.0],
            [0.3, 0.3, -1.0],
        ],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3], [0, 2, 1, 4]], dtype=np.int64)
    off_case = tmp_path / "off"
    on_case = tmp_path / "on"

    monkeypatch.delenv("AUTO_TESSELL_POLY_NO_DROP_HOLES1", raising=False)
    off = tet_to_poly_dual(vertices, tets, off_case)
    monkeypatch.setenv("AUTO_TESSELL_POLY_NO_DROP_HOLES1", "1")
    on = tet_to_poly_dual(vertices, tets, on_case)

    assert off.success and on.success
    assert _case_snapshot(off_case) == _case_snapshot(on_case)


def test_budget_boundary_layer_hex_route_is_flag_noop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    faces = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]], dtype=np.int64)
    calls: list[int] = []

    def fake_hex(*_args: Any, **kwargs: Any) -> native_poly.NativePolyResult:
        calls.append(int(kwargs["bl_layers"]))
        return native_poly.NativePolyResult(
            True,
            0.0,
            n_cells=4,
            n_points=4,
            n_faces=10,
            quality_grade="B",
        )

    def fail_inner(*_args: Any, **_kwargs: Any) -> native_poly.NativePolyResult:
        raise AssertionError("direct SciPy route must not run")

    monkeypatch.setattr(voronoi, "_hex_to_poly_fallback", fake_hex)
    monkeypatch.setattr(voronoi, "_generate_native_poly_voronoi_inner", fail_inner)
    results = []
    for enabled in (False, True):
        if enabled:
            monkeypatch.setenv("AUTO_TESSELL_POLY_NO_DROP_HOLES1", "1")
        else:
            monkeypatch.delenv("AUTO_TESSELL_POLY_NO_DROP_HOLES1", raising=False)
        results.append(
            voronoi.generate_native_poly_voronoi(
                vertices,
                faces,
                tmp_path / str(enabled),
                target_cells=4,
                prefer_hex_for_budget=True,
                bl_layers=2,
                auto_escalate=False,
            )
        )

    assert calls == [2, 2]
    assert [(result.success, result.n_cells) for result in results] == [(True, 4), (True, 4)]
