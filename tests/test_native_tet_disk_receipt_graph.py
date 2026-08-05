from __future__ import annotations

from pathlib import Path

from core.generator.native_tet.disk_receipt_graph import audit_disk_receipt_graph


_FACES = [
    [0, 3, 2, 1],
    [4, 5, 6, 7],
    [0, 1, 5, 4],
    [1, 2, 6, 5],
    [2, 3, 7, 6],
    [3, 0, 4, 7],
]


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
        "FoamFile { object faces; }\n6\n(\n"
        + "\n".join(f"4({' '.join(map(str, face))})" for face in _FACES)
        + "\n)\n",
        encoding="utf-8",
    )
    (root / "owner").write_text("FoamFile { object owner; }\n6\n(\n0\n0\n0\n0\n0\n0\n)\n", encoding="utf-8")
    (root / "neighbour").write_text("FoamFile { object neighbour; }\n0\n(\n)\n", encoding="utf-8")
    (root / "boundary").write_text(
        "FoamFile { object boundary; }\n1\n(\nwall { type wall; nFaces 6; startFace 0; }\n)\n",
        encoding="utf-8",
    )


def _receipt(faces: list[list[int]] = _FACES, *, patch: str = "wall") -> dict[str, object]:
    return {
        "source_sha256": "a" * 64,
        "semantic_ledger_sha256": "b" * 64,
        "interface_triangles": [
            {
                "source_face": str(index),
                "triangle": face,
                "feature": "wall",
                "patch": patch,
                "physical_group": "fluid-wall",
                "component": "tetra",
                "provenance": f"surface#{index}",
            }
            for index, face in enumerate(faces)
        ],
    }


def test_disk_receipt_graph_accepts_actual_boundary_faces(tmp_path: Path) -> None:
    root = tmp_path / "polyMesh"
    _write_cube(root)

    result = audit_disk_receipt_graph(root, _receipt())

    assert result["accepted"] is True
    assert result["source_output_exact"] is True
    assert result["disk_boundary_face_count"] == 6


def test_disk_receipt_graph_rejects_reversed_source_cycle(tmp_path: Path) -> None:
    root = tmp_path / "polyMesh"
    _write_cube(root)
    reversed_faces = list(_FACES)
    reversed_faces[0] = list(reversed(reversed_faces[0]))

    result = audit_disk_receipt_graph(root, _receipt(reversed_faces))

    assert result["accepted"] is False
    assert result["reason"] == "receipt_graph_source_face_disk_match_invalid"


def test_disk_receipt_graph_rejects_patch_semantic_tamper(tmp_path: Path) -> None:
    root = tmp_path / "polyMesh"
    _write_cube(root)

    result = audit_disk_receipt_graph(root, _receipt(patch="inlet"))

    assert result["accepted"] is False
    assert result["reason"] == "receipt_graph_patch_type_mismatch"
