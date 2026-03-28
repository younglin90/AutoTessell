"""Unit tests for checkMesh output parser."""

from mesh.checkmesh import parse_checkmesh_output


PASSING_OUTPUT = """
/*---------------------------------------------------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     |
    \\\\  /    A nd           |
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/

Checking geometry...
    Max non-orthogonality = 42.3 degrees.
    Max skewness = 0.87
    Overall domain bounding box (-1 -1 -1) (1 1 1)
    Cell volumes OK.
    Mesh OK.
"""

FAILING_OUTPUT = """
    Max non-orthogonality = 95.1 degrees.
    Max skewness = 4.2
    ***High aspect ratio cells found, 3 cells with aspect ratio > 1000***
    Failed 1 mesh checks.
"""

PARTIAL_OUTPUT = """
    cells:          1234567
    Mesh OK.
"""


def test_passing_mesh():
    r = parse_checkmesh_output(PASSING_OUTPUT)
    assert r.passed is True
    assert r.max_non_orthogonality == pytest.approx(42.3)
    assert r.max_skewness == pytest.approx(0.87)


def test_failing_mesh():
    r = parse_checkmesh_output(FAILING_OUTPUT)
    assert r.passed is False
    assert r.max_non_orthogonality == pytest.approx(95.1)
    assert r.max_skewness == pytest.approx(4.2)


def test_cell_count_parsed():
    r = parse_checkmesh_output(PARTIAL_OUTPUT)
    assert r.passed is True
    assert r.num_cells == 1234567


def test_empty_output():
    r = parse_checkmesh_output("")
    assert r.passed is False
    assert r.max_non_orthogonality is None
    assert r.max_skewness is None


import pytest
