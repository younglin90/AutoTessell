"""Minimal-to-basic regression ladder for the global input-surface ledger."""

from __future__ import annotations

from core.generator.native_tet.chen_source_subdivision_l0 import oriented_boundary_faces_l1
from core.generator.native_tet.input_surface_ledger_l0 import audit_input_surface_ledger_l0


_TET_POINTS = ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
_TET = ((0, 1, 2, 3),)
_TET_SURFACE = oriented_boundary_faces_l1(_TET_POINTS, _TET)


def test_input_surface_ledger_accepts_an_exact_tetrahedron_boundary() -> None:
    result = audit_input_surface_ledger_l0(_TET_POINTS, _TET_SURFACE, _TET_POINTS, _TET)

    assert result.accepted, result.reason
    assert result.missing_source_vertices == 0
    assert result.boundary_face_count == 4


def test_input_surface_ledger_rejects_a_dropped_source_vertex_before_face_audit() -> None:
    output_points = ((0, 0, 0), (1, 0, 0), (0, 1, 0))

    result = audit_input_surface_ledger_l0(_TET_POINTS, _TET_SURFACE, output_points, ())

    assert not result.accepted
    assert result.reason == "missing_exact_source_vertex"
    assert result.missing_source_vertices == 1
