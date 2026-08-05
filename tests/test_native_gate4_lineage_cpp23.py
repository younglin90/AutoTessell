from __future__ import annotations

from pathlib import Path

import pytest


native_gate4 = pytest.importorskip("native_gate4_lineage_witness")


def _make_staged_root(root: Path, *, face_count: int = 3) -> None:
    root.mkdir()
    (root / "points").write_text("points\n", encoding="utf-8")
    (root / "faces").write_text("faces\n", encoding="utf-8")
    (root / "owner").write_text("owner\n", encoding="utf-8")
    (root / "neighbour").write_text("neighbour\n", encoding="utf-8")
    (root / "boundary").write_text(
        f"""2
(
wall
{{
    type wall;
    nFaces {face_count};
    startFace 10;
}}
farfield
{{
    type patch;
    nFaces 0;
    startFace 100;
}}
)
""",
        encoding="utf-8",
    )


def _semantic_rows() -> list[dict[str, object]]:
    return [
        {
            "entity_kind": "stl_facet",
            "source_id": 0,
            "feature": "cube-face",
            "patch": "wall",
            "physical_group": "fluid-wall",
            "component": "cube",
            "provenance": "tests/benchmarks/cube.stl#facet/0",
        }
    ]


def _records(*, positive_bl: bool) -> list[dict[str, object]]:
    uids = ["boundary_face_10", "boundary_face_11", "boundary_face_12"]
    roles = ["wall", "inner", "outer"] if positive_bl else ["wall"] * 3
    operations = ["bl_extrude", "bl_extrude", "transition"] if positive_bl else ["identity"] * 3
    layers = [0, 1, 2] if positive_bl else [0] * 3
    parents = [None, "boundary_face_10", "boundary_face_11"] if positive_bl else [None] * 3
    measures = [1.0] * 3 if positive_bl else [0.0] * 3
    return [
        {
            "output_uid": uid,
            "entity_scope": "output_boundary",
            "source_ref": {"kind": "stl_facet", "id": 0},
            "semantic_owner_id": "sem/stl_facet/0",
            "operation": operation,
            "boundary_role": role,
            "layer_index": layer,
            "parent_uid": parent,
            "positive_measure": measure,
            "feature": "cube-face",
            "patch": "wall",
            "physical_group": "fluid-wall",
            "component": "cube",
            "provenance": "tests/benchmarks/cube.stl#facet/0",
        }
        for uid, role, operation, layer, parent, measure in zip(uids, roles, operations, layers, parents, measures)
    ]


def test_cpp23_witness_is_deterministic_for_bl0_and_bl1(tmp_path: Path) -> None:
    for positive_bl in (False, True):
        root = tmp_path / ("bl1" if positive_bl else "bl0")
        _make_staged_root(root)
        layer_count = 2 if positive_bl else 0
        result_a = native_gate4.audit_staged_lineage(
            str(root), _semantic_rows(), _records(positive_bl=positive_bl),
            layer_count, layer_count,
        )
        result_b = native_gate4.audit_staged_lineage(
            str(root), _semantic_rows(), _records(positive_bl=positive_bl),
            layer_count, layer_count,
        )
        assert result_a["accepted"] is True, result_a
        assert result_a["cpp_standard"] == "cxx_std_23"
        assert result_a["tree_sha256"] == result_b["tree_sha256"]
        assert result_a["lineage_sha256"] == result_b["lineage_sha256"]
        assert result_a["actual_boundary_uids"] == [
            "boundary_face_10", "boundary_face_11", "boundary_face_12"
        ]


def test_cpp23_witness_refuses_boundary_uid_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "mismatch"
    _make_staged_root(root, face_count=2)
    result = native_gate4.audit_staged_lineage(
        str(root), _semantic_rows(), _records(positive_bl=False), 0, 0,
    )
    assert result["accepted"] is False
    assert result["candidate_discarded"] is True
    assert "output_boundary_uid_missing" in result["reasons"]


def test_cpp23_witness_refuses_symlink_in_staged_tree(tmp_path: Path) -> None:
    root = tmp_path / "symlink"
    _make_staged_root(root)
    (root / "escape").symlink_to(root / "points")
    result = native_gate4.audit_staged_lineage(
        str(root), _semantic_rows(), _records(positive_bl=False), 0, 0,
    )
    assert result["accepted"] is False
    assert any("artifact_symlink_forbidden" in reason for reason in result["reasons"])


def test_cpp23_witness_refuses_missing_measure_and_unknown_parent(tmp_path: Path) -> None:
    root = tmp_path / "invalid_bl"
    _make_staged_root(root)
    records = _records(positive_bl=True)
    del records[1]["positive_measure"]
    records[2]["parent_uid"] = "missing-parent"
    result = native_gate4.audit_staged_lineage(
        str(root), _semantic_rows(), records, 2, 2,
    )
    assert result["accepted"] is False
    assert "bl_positive_measure_failed" in result["reasons"]
    assert "bl_parent_unknown" in result["reasons"]
