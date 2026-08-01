"""L0 contracts for the independent written-volume topology audit."""

from __future__ import annotations

from pathlib import Path

from core.evaluator.strict_volume_topology import audit_strict_volume_topology

_POINTS = """8
(
(0 0 0)
(1 0 0)
(1 1 0)
(0 1 0)
(0 0 1)
(1 0 1)
(1 1 1)
(0 1 1)
)
"""
_FACES = """6
(
4(0 3 2 1)
4(4 5 6 7)
4(0 1 5 4)
4(1 2 6 5)
4(2 3 7 6)
4(3 0 4 7)
)
"""
_DUPLICATE_FACES = """7
(
4(0 3 2 1)
4(4 5 6 7)
4(0 1 5 4)
4(1 2 6 5)
4(2 3 7 6)
4(3 0 4 7)
4(0 3 2 1)
)
"""
_OWNER = """6
(
0
0
0
0
0
0
)
"""
_DUPLICATE_OWNER = """7
(
0
0
0
0
0
0
0
)
"""
_EMPTY_NEIGHBOUR = """0
(
)
"""


def _boundary(n_faces: int) -> str:
    return f"""1
(
wall
{{
    type wall;
    nFaces {n_faces};
    startFace 0;
}}
)
"""


def _write_cube(case_dir: Path, *, duplicate_face: bool = False) -> None:
    poly_mesh = case_dir / "constant" / "polyMesh"
    poly_mesh.mkdir(parents=True)
    n_faces = 7 if duplicate_face else 6
    values = {
        "points": _POINTS,
        "faces": _DUPLICATE_FACES if duplicate_face else _FACES,
        "owner": _DUPLICATE_OWNER if duplicate_face else _OWNER,
        "neighbour": _EMPTY_NEIGHBOUR,
        "boundary": _boundary(n_faces),
    }
    for name, text in values.items():
        (poly_mesh / name).write_text(text, encoding="utf-8")


def test_closed_cube_written_artifact_is_strictly_valid(tmp_path: Path) -> None:
    case_dir = tmp_path / "cube"
    _write_cube(case_dir)

    report = audit_strict_volume_topology(case_dir)

    assert report.status == "measured"
    assert report.valid
    assert report.n_duplicate_faces == 0
    assert report.n_nonmanifold_faces == 0
    assert report.n_inverted_cells == 0
    assert report.n_open_cell_edges == 0
    assert report.boundary_surface_valid


def test_duplicate_written_face_is_never_certified(tmp_path: Path) -> None:
    case_dir = tmp_path / "duplicate"
    _write_cube(case_dir, duplicate_face=True)

    report = audit_strict_volume_topology(case_dir)

    assert not report.valid
    assert report.n_duplicate_faces == 1
    assert report.boundary_duplicate_faces == 1


def test_missing_artifact_is_unverified_not_valid(tmp_path: Path) -> None:
    report = audit_strict_volume_topology(tmp_path / "missing")

    assert report.status == "unverified"
    assert not report.valid
    assert report.malformed_reason == "artifact_missing_or_unsafe"
