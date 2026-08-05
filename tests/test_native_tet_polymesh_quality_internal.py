from __future__ import annotations

import sys
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "auto_tessell_core" / "build"))
import native_tet_polymesh_quality as native  # noqa: E402


def _write_two_cubes(root: Path) -> None:
    root.mkdir(parents=True)
    points = [
        (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
        (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
        (2, 0, 0), (2, 1, 0), (2, 0, 1), (2, 1, 1),
    ]
    faces = [
        (1, 2, 6, 5),
        (0, 1, 2, 3), (4, 7, 6, 5), (0, 3, 7, 4),
        (0, 4, 5, 1), (3, 2, 6, 7),
        (8, 10, 11, 9), (1, 8, 9, 2), (5, 6, 11, 10),
        (1, 5, 10, 8), (2, 9, 11, 6),
    ]
    (root / "points").write_text(
        "FoamFile { object points; }\n12\n(\n"
        + "\n".join(f"({x} {y} {z})" for x, y, z in points)
        + "\n)\n",
        encoding="utf-8",
    )
    (root / "faces").write_text(
        "FoamFile { object faces; }\n11\n(\n"
        + "\n".join(f"4({' '.join(map(str, face))})" for face in faces)
        + "\n)\n",
        encoding="utf-8",
    )
    (root / "owner").write_text(
        "FoamFile { object owner; }\n11\n(\n"
        + "\n".join(["0"] * 6 + ["1"] * 5)
        + "\n)\n",
        encoding="utf-8",
    )
    (root / "neighbour").write_text(
        "FoamFile { object neighbour; }\n1\n(\n1\n)\n",
        encoding="utf-8",
    )
    (root / "boundary").write_text(
        "FoamFile { object boundary; }\n2\n(\n"
        "left { type wall; nFaces 5; startFace 1; }\n"
        "right { type wall; nFaces 5; startFace 6; }\n)\n",
        encoding="utf-8",
    )


def test_disk_oracle_handles_internal_face_and_two_cells(tmp_path: Path) -> None:
    root = tmp_path / "polyMesh"
    _write_two_cubes(root)

    result = dict(native.audit(str(root)))

    assert result["valid"] is True
    assert result["quality_pass"] is True
    assert result["n_internal_faces"] == 1
    assert result["n_boundary_faces"] == 10
    assert result["n_cells"] == 2
    assert result["max_non_orthogonality"] == pytest.approx(0.0, abs=1e-12)
    assert result["max_internal_skewness"] == pytest.approx(0.0, abs=1e-12)
    assert result["max_boundary_skewness"] == pytest.approx(0.0, abs=1e-12)
    assert result["max_aspect_ratio"] == pytest.approx(3.0**0.5, abs=1e-12)
