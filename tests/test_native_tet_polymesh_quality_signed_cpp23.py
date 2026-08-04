from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_native_tet_polymesh_quality import _module_or_skip


def _write_two_cell_mesh(root: Path, internal_face: str) -> None:
    root.mkdir(parents=True)
    (root / "points").write_text(
        """FoamFile { object points; }
12
(
(0 0 0) (1 0 0) (1 1 0) (0 1 0) (0 0 1) (1 0 1) (1 1 1) (0 1 1)
(2 0 0) (2 1 0) (2 0 1) (2 1 1)
)
""",
        encoding="utf-8",
    )
    boundary_faces = [
        "4(0 3 2 1)", "4(0 1 5 4)", "4(2 3 7 6)", "4(3 0 4 7)",
        "4(8 9 11 10)", "4(1 8 10 5)", "4(2 6 11 9)", "4(5 10 8 1)",
        "4(3 7 11 2)", "4(4 5 10 8)",
    ]
    (root / "faces").write_text(
        "FoamFile { object faces; }\n11\n(\n"
        + internal_face + "\n"
        + "\n".join(boundary_faces)
        + "\n)\n",
        encoding="utf-8",
    )
    (root / "owner").write_text(
        "FoamFile { object owner; }\n11\n(\n"
        + "0\n" + "\n".join(["0", "0", "0", "0", "1", "1", "1", "1", "1", "1"])
        + "\n)\n",
        encoding="utf-8",
    )
    (root / "neighbour").write_text("FoamFile { object neighbour; }\n1\n(\n1\n)\n", encoding="utf-8")
    (root / "boundary").write_text(
        "FoamFile { object boundary; }\n1\n(\nwall { type wall; nFaces 10; startFace 1; }\n)\n",
        encoding="utf-8",
    )


def test_internal_non_orthogonality_preserves_face_orientation(tmp_path: Path) -> None:
    native = _module_or_skip()
    good = tmp_path / "good"
    bad = tmp_path / "bad"
    _write_two_cell_mesh(good, "4(1 2 6 5)")
    _write_two_cell_mesh(bad, "4(1 5 6 2)")

    good_result = dict(native.audit(str(good)))
    bad_result = dict(native.audit(str(bad)))

    assert good_result["valid"] is True
    assert good_result["max_non_orthogonality"] < 10.0
    assert bad_result["valid"] is True
    assert bad_result["max_non_orthogonality"] > 170.0
    assert bad_result["quality_pass"] is False
