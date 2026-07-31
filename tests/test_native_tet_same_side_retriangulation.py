"""Focused strict same-side repair regression on the representative sphere."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.generator.native_tet.mesher import generate_native_tet
from core.generator.native_tet.same_side_retriangulation import (
    retriangulate_if_strictly_safer,
)

_SPHERE = Path(__file__).resolve().parent / "benchmarks" / "sphere.stl"


def test_sphere_retriangulation_strictly_reduces_same_side_debt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AUTO_TESSELL_TET_SAME_SIDE_RETRIANGULATION", "0")
    mesh = read_stl(_SPHERE)
    result = generate_native_tet(
        np.ascontiguousarray(mesh.vertices, dtype=np.float64),
        np.ascontiguousarray(mesh.faces, dtype=np.int64),
        tmp_path / "sphere",
        target_cells=2000,
        enable_bsp_insertion=False,
        enable_edge_recovery=False,
        enable_phase_b=False,
        enable_phase_c=False,
    )
    transaction = retriangulate_if_strictly_safer(
        mesh.vertices,
        mesh.faces,
        result.tet_points,
        result.tets,
    )

    assert transaction.accepted is True
    assert transaction.exact_rollback is False
    assert transaction.source_component_bijective is True
    assert transaction.source_faces_preserved is True
    assert transaction.candidate_unowned_faces == 0
    assert transaction.candidate_inverted_tets <= transaction.before_inverted_tets
    assert (
        transaction.candidate_same_side_internal_faces
        < transaction.before_same_side_internal_faces
    )
