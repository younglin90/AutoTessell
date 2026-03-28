"""Unit tests for checkMesh output parser."""

import pytest

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


def test_raw_output_preserved():
    r = parse_checkmesh_output(PASSING_OUTPUT)
    assert PASSING_OUTPUT in r.raw_output


def test_num_cells_none_when_absent():
    r = parse_checkmesh_output("Mesh OK.\n")
    assert r.passed is True
    assert r.num_cells is None


def test_mesh_ok_with_failed_check_is_failed():
    """If both 'Mesh OK.' and 'Failed N mesh checks.' appear, treat as failed."""
    output = "    Mesh OK.\n    Failed 1 mesh checks.\n"
    r = parse_checkmesh_output(output)
    assert r.passed is False


def test_failed_check_case_insensitive():
    """'FAILED 2 MESH CHECKS' should also be detected."""
    output = "Mesh OK.\nFAILED 2 MESH CHECKS.\n"
    r = parse_checkmesh_output(output)
    assert r.passed is False


def test_large_cell_count_parsed():
    """Cell counts in the millions must parse correctly."""
    output = "    cells:          12345678\n    Mesh OK.\n"
    r = parse_checkmesh_output(output)
    assert r.num_cells == 12345678


def test_non_orthogonality_with_extra_whitespace():
    """Extra spaces between '=' and the value must not break extraction."""
    output = "    Max non-orthogonality =    55.7 degrees.\n    Mesh OK.\n"
    r = parse_checkmesh_output(output)
    assert r.max_non_orthogonality == pytest.approx(55.7)


def test_checkmesh_result_dataclass_fields():
    """CheckMeshResult must expose the expected fields."""
    from mesh.checkmesh import CheckMeshResult
    r = CheckMeshResult(passed=True, max_non_orthogonality=30.0, max_skewness=0.5, num_cells=1000, raw_output="")
    assert r.passed is True
    assert r.max_non_orthogonality == pytest.approx(30.0)
    assert r.max_skewness == pytest.approx(0.5)
    assert r.num_cells == 1000


def test_failed_without_mesh_ok():
    """'Failed N mesh checks.' without 'Mesh OK.' must also be detected as failed."""
    output = "    Failed 3 mesh checks.\n"
    r = parse_checkmesh_output(output)
    assert r.passed is False


def test_non_ortho_and_skewness_both_none_when_absent():
    """Output with no quality metrics must return None for both fields."""
    output = "    cells:    500\n    Mesh OK.\n"
    r = parse_checkmesh_output(output)
    assert r.max_non_orthogonality is None
    assert r.max_skewness is None


def test_passed_requires_mesh_ok_keyword():
    """A well-formed output must contain 'Mesh OK.' to be considered passing."""
    output = "    Max non-orthogonality = 30.0 degrees.\n    Max skewness = 0.5\n"
    r = parse_checkmesh_output(output)
    # No 'Mesh OK.' → not passed
    assert r.passed is False


def test_skewness_value_none_when_only_non_ortho_present():
    """max_skewness must be None when only non-orthogonality appears in output."""
    output = "    Max non-orthogonality = 55.0 degrees.\n    Mesh OK.\n"
    r = parse_checkmesh_output(output)
    assert r.max_non_orthogonality == pytest.approx(55.0)
    assert r.max_skewness is None
