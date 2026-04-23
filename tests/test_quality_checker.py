"""beta49 — CheckMeshParser dedicated 회귀.

core/evaluator/quality_checker.CheckMeshParser.parse 의 stdout 파싱 단위 회귀.
OpenFOAM checkMesh 출력의 다양한 패턴 처리.
"""
from __future__ import annotations

import pytest

from core.evaluator.quality_checker import CheckMeshParser


_SAMPLE_CLEAN_OUTPUT = """
Create time

Create polyMesh for time = 0

Time = 0

Mesh stats
    points:           4009
    internal points:  0
    faces:            15728
    internal faces:   7634
    cells:            4009
    faces per cell:   5.89
    boundary patches: 1
    point zones:      0
    face zones:       0
    cell zones:       0

Overall number of cells of each type:
    hexahedra:     0
    prisms:        0
    wedges:        0
    pyramids:      0
    tet wedges:    0
    tetrahedra:    4009
    polyhedra:     0

Checking topology...
    Boundary definition OK.
    Cell to face addressing OK.
    Point usage OK.
    Upper triangular ordering OK.
    Face vertices OK.
    Number of regions: 1 (OK).

Checking patch topology for multiply connected surfaces...
    Patch               Faces    Points   Surface topology
    defaultWall         8094     2192     ok (closed singly connected)

Checking geometry...
    Overall domain bounding box (-1 -1 -1) (1 1 1)
    Mesh has 3 geometric (non-empty/wedge) directions (1 1 1)
    Mesh has 3 solution (non-empty) directions (1 1 1)
    Boundary openness (0 0 0) OK.
    Max cell openness = 2.4e-16 OK.
    Max aspect ratio = 6.52 OK.
    Minimum face area = 1.23e-4. Maximum face area = 0.04.
    Min volume = 4.56e-05. Max volume = 0.04. Total volume = 3.65.
    Mesh non-orthogonality Max: 45.7 average: 12.3
    Non-orthogonality check OK.
    Face pyramids OK.
    Max skewness = 0.85 OK.
    Coupled point location match (average 0) OK.
    Min determinant = 0.012

Mesh OK.
"""


_SAMPLE_FAILED_OUTPUT = """
Mesh stats
    points:           100
    faces:            200
    cells:            50
    internal faces:   100

Checking geometry...
    Max aspect ratio = 850.5
    Mesh non-orthogonality Max: 85.2 average: 45.1
    Max skewness = 8.3
    ***Error: 5 negative volumes
    Min volume = -0.001
    Min determinant = 0.0
    Number of severely non-orthogonal (> 70 degrees) faces: 12

Failed 3 mesh checks.
"""


def test_parse_clean_output_returns_mesh_ok() -> None:
    parser = CheckMeshParser()
    r = parser.parse(_SAMPLE_CLEAN_OUTPUT)
    assert r.cells == 4009
    assert r.faces == 15728
    assert r.points == 4009
    assert r.max_non_orthogonality == pytest.approx(45.7)
    assert r.avg_non_orthogonality == pytest.approx(12.3)
    assert r.max_skewness == pytest.approx(0.85)
    assert r.max_aspect_ratio == pytest.approx(6.52)
    assert r.negative_volumes == 0
    assert r.failed_checks == 0
    assert r.mesh_ok is True


def test_parse_failed_output_sets_mesh_ok_false() -> None:
    """failed_checks > 0 → mesh_ok=False."""
    parser = CheckMeshParser()
    r = parser.parse(_SAMPLE_FAILED_OUTPUT)
    assert r.cells == 50
    assert r.faces == 200
    assert r.max_non_orthogonality == pytest.approx(85.2)
    assert r.max_skewness == pytest.approx(8.3)
    assert r.max_aspect_ratio == pytest.approx(850.5)
    assert r.negative_volumes == 5
    assert r.severely_non_ortho_faces == 12
    assert r.failed_checks == 3
    assert r.mesh_ok is False


def test_parse_empty_output_returns_defaults() -> None:
    """빈 stdout → 기본값 CheckMeshResult."""
    parser = CheckMeshParser()
    r = parser.parse("")
    assert r.cells == 0
    assert r.faces == 0
    assert r.points == 0
    assert r.max_non_orthogonality == 0.0
    assert r.mesh_ok is False  # "Mesh OK." 없음 + failed_checks=0


def test_parse_mesh_ok_line_sets_true() -> None:
    """'Mesh OK.' 문자열만으로 mesh_ok=True."""
    stdout = "cells: 10\nfaces: 20\nMesh OK.\n"
    parser = CheckMeshParser()
    r = parser.parse(stdout)
    assert r.mesh_ok is True


def test_parse_failed_checks_overrides_mesh_ok() -> None:
    """Mesh OK + Failed N → mesh_ok=False."""
    stdout = "cells: 10\nMesh OK.\nFailed 2 mesh checks.\n"
    parser = CheckMeshParser()
    r = parser.parse(stdout)
    assert r.failed_checks == 2
    assert r.mesh_ok is False


def test_parse_negative_volumes_detected() -> None:
    """***Error: N negative volume(s) 패턴 감지."""
    stdout = "***Error: 7 negative volumes\n"
    parser = CheckMeshParser()
    r = parser.parse(stdout)
    assert r.negative_volumes == 7


def test_parse_severely_non_ortho_extracted() -> None:
    stdout = "Number of severely non-orthogonal (> 70 degrees) faces: 42\n"
    parser = CheckMeshParser()
    r = parser.parse(stdout)
    assert r.severely_non_ortho_faces == 42


def test_parse_min_cell_volume_default_when_missing() -> None:
    """Min volume 미검출 시 기본값 1.0."""
    parser = CheckMeshParser()
    r = parser.parse("cells: 10\n")
    assert r.min_cell_volume == 1.0


def test_parse_min_determinant_default_when_missing() -> None:
    """Min determinant 미검출 시 기본값 1.0."""
    parser = CheckMeshParser()
    r = parser.parse("cells: 10\n")
    assert r.min_determinant == 1.0


def test_parse_alternative_non_ortho_pattern() -> None:
    """'Max non-orthogonality = 45.0' 형식도 파싱."""
    parser = CheckMeshParser()
    r = parser.parse("Max non-orthogonality = 45.0\n")
    assert r.max_non_orthogonality == pytest.approx(45.0)
