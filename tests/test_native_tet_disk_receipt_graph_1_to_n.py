from __future__ import annotations

from pathlib import Path

from core.generator.native_tet.disk_receipt_graph import audit_disk_receipt_graph


FACES = [
    [0, 1, 2],
    [0, 2, 3],
    [4, 5, 6, 7],
    [0, 1, 5, 4],
    [1, 2, 6, 5],
    [2, 3, 7, 6],
    [3, 0, 4, 7],
]


def _write_mesh(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "faces").write_text(
        "FoamFile { object faces; }\n7\n(\n"
        + "\n".join(f"{len(face)}({' '.join(map(str, face))})" for face in FACES)
        + "\n)\n",
        encoding="utf-8",
    )
    (root / "owner").write_text(
        "FoamFile { object owner; }\n7\n(\n0\n0\n0\n0\n0\n0\n0\n)\n",
        encoding="utf-8",
    )
    (root / "neighbour").write_text("FoamFile { object neighbour; }\n0\n(\n)\n", encoding="utf-8")
    (root / "boundary").write_text(
        "FoamFile { object boundary; }\n1\n(\nwall { type wall; nFaces 7; startFace 0; }\n)\n",
        encoding="utf-8",
    )


def _receipt() -> dict[str, object]:
    semantics = {
        "feature": "wall",
        "patch": "wall",
        "physical_group": "fluid-wall",
        "component": "tetra",
        "provenance": "writer-id",
    }
    interfaces = [
        {
            "source_face": "source-quad",
            "source_vertex_ids": [0, 1, 2, 3],
            "children": [
                {"output_face_id": "child-0", "disk_face_id": 0, "output_vertex_ids": FACES[0]},
                {"output_face_id": "child-1", "disk_face_id": 1, "output_vertex_ids": FACES[1]},
            ],
            **semantics,
        },
    ]
    for index in range(2, len(FACES)):
        interfaces.append({
            "source_face": f"source-{index}",
            "source_vertex_ids": FACES[index],
            "children": [{
                "output_face_id": f"child-{index}",
                "disk_face_id": index,
                "output_vertex_ids": FACES[index],
            }],
            **semantics,
        })
    return {
        "source_sha256": "a" * 64,
        "semantic_ledger_sha256": "b" * 64,
        "interface_children": interfaces,
    }


def test_disk_receipt_graph_accepts_explicit_one_to_many_children(tmp_path: Path) -> None:
    root = tmp_path / "polyMesh"
    _write_mesh(root)

    result = audit_disk_receipt_graph(root, _receipt())

    assert result["accepted"] is True
    assert result["mapping"] == "1:N"
    assert result["inverse_coverage"] is True
    assert result["source_face_count"] == 6
    assert result["output_face_count"] == 7
    assert result["source_output_1_to_n"] is True


def test_disk_receipt_graph_one_to_many_refuses_child_id_omission(tmp_path: Path) -> None:
    root = tmp_path / "polyMesh"
    _write_mesh(root)
    receipt = _receipt()
    children = receipt["interface_children"]
    assert isinstance(children, list)
    children[0]["children"] = children[0]["children"][:1]

    result = audit_disk_receipt_graph(root, receipt)

    assert result["accepted"] is False
    assert result["reason"] == "receipt_graph_source_output_coverage_mismatch"


def test_disk_receipt_graph_one_to_many_refuses_disk_face_binding_tamper(tmp_path: Path) -> None:
    root = tmp_path / "polyMesh"
    _write_mesh(root)
    receipt = _receipt()
    children = receipt["interface_children"]
    assert isinstance(children, list)
    children[0]["children"][0]["output_vertex_ids"] = [0, 2, 1]

    result = audit_disk_receipt_graph(root, receipt)

    assert result["accepted"] is False
    assert result["reason"] == "receipt_graph_child_disk_binding_invalid"
