"""Independent C++ disk quality oracle fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


_BUILD = Path(__file__).resolve().parents[1] / "auto_tessell_core" / "build"


def _module_or_skip():
    if str(_BUILD) not in sys.path:
        sys.path.insert(0, str(_BUILD))
    return pytest.importorskip("native_tet_polymesh_quality")


def _write_cube(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "points").write_text(
        """FoamFile { object points; }
8
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
""",
        encoding="utf-8",
    )
    (root / "faces").write_text(
        """FoamFile { object faces; }
6
(
4(0 3 2 1)
4(4 5 6 7)
4(0 1 5 4)
4(1 2 6 5)
4(2 3 7 6)
4(3 0 4 7)
)
""",
        encoding="utf-8",
    )
    (root / "owner").write_text(
        """FoamFile { object owner; }
6
(
0
0
0
0
0
0
)
""",
        encoding="utf-8",
    )
    (root / "neighbour").write_text(
        """FoamFile { object neighbour; }
0
(
)
""",
        encoding="utf-8",
    )
    (root / "boundary").write_text(
        """FoamFile { object boundary; }
1
(
wall { type wall; nFaces 6; startFace 0; }
)
""",
        encoding="utf-8",
    )


def test_disk_oracle_reads_actual_poly_mesh(tmp_path: Path) -> None:
    native = _module_or_skip()
    root = tmp_path / "constant" / "polyMesh"
    _write_cube(root)

    result = dict(native.audit(str(root)))

    assert result["valid"] is True
    assert result["quality_pass"] is True
    assert result["n_points"] == 8
    assert result["n_faces"] == 6
    assert result["n_internal_faces"] == 0
    assert result["n_boundary_faces"] == 6
    assert result["n_cells"] == 1
    assert result["max_non_orthogonality"] == pytest.approx(0.0, abs=1e-12)
    assert result["max_skewness"] == pytest.approx(0.0, abs=1e-12)
    assert result["max_aspect_ratio"] == pytest.approx(3.0**0.5, abs=1e-12)


def test_disk_oracle_fails_closed_on_boundary_gap(tmp_path: Path) -> None:
    native = _module_or_skip()
    root = tmp_path / "polyMesh"
    _write_cube(root)
    boundary = (root / "boundary").read_text(encoding="utf-8").replace(
        "startFace 0", "startFace 1"
    )
    (root / "boundary").write_text(boundary, encoding="utf-8")

    result = dict(native.audit(str(root)))

    assert result["valid"] is False
    assert result["quality_pass"] is False
    assert result["error"] == "polymesh_boundary_range_invalid"
