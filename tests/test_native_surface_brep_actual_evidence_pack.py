from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from core.evaluator.native_surface_brep_evidence_pack_bridge import (
    write_actual_brep_surface_evidence_pack_v2,
)
from tests.test_cad_xde_physical_authority import _write_styled_box
from tests.test_native_tet_brep_front_evidence_v2 import _explicit_owner_map
from core.analyzer.readers.step import load_cad_native_with_provenance
from core.layers.native_tet_brep_front_evidence_v2 import build_brep_front_evidence_v2


def _mapping(source: Path):
    raw_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    cad = load_cad_native_with_provenance(source, ".step")
    evidence = build_brep_front_evidence_v2(
        cad, source_digest=raw_digest, owner_face_by_edge=_explicit_owner_map(cad)
    )
    rows = []
    selected = int(evidence["edges"][0]["brep_edge_id"])
    for edge in evidence["edges"]:
        edge_id = int(edge["brep_edge_id"])
        rows.append(
            {
                "source_edge": edge_id,
                "source_face": int(edge["owner_face_id"]),
                "wall_edge": f"wall-{edge_id}",
                "output_face": f"output-{edge_id}",
                "patch": "wall",
                "feature": "cad-face",
                "physical_group": "fluid-wall",
                "component": "styled-box",
                "provenance": "explicit-user-map",
                "mapping_source": "explicit_user",
                "direct": True,
                "selected_for_bl": edge_id == selected,
            }
        )
    return rows, _explicit_owner_map(cad)


@pytest.mark.parametrize("requested_layers, expected_records", [(0, 0), (1, 1), (3, 3)])
def test_actual_brep_surface_pack_bl_matrix(
    tmp_path: Path, monkeypatch, requested_layers: int, expected_records: int
):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_surface_bl_front_shared_build")
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    mapping, owners = _mapping(source)
    result = write_actual_brep_surface_evidence_pack_v2(
        tmp_path / f"pack-{requested_layers}",
        source,
        explicit_mapping=mapping,
        owner_face_by_edge=owners,
        requested_layers=requested_layers,
        domain_side_authority_fixture=True,
    )
    assert result["accepted"] is True, result
    assert result["authority_level"] == "L0_actual_brep_fixture"
    assert result["publication_eligible"] is False
    assert len(result["producer_runs"]) == 3
    assert len(result["transactions"]) == 3
    assert len(result["producer_runs"][0]["layer_records"]) == expected_records
    root = Path(result["evidence_root"])
    assert root.joinpath("evidence.atne").is_file()
    assert root.joinpath("layers.tsv").is_file()
    assert "authority_canonical_positions_digest=" in root.joinpath("evidence.atne").read_text()


def test_actual_brep_surface_pack_rejects_mapping_mutation(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_surface_bl_front_shared_build")
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    mapping, owners = _mapping(source)
    mapping[0]["physical_group"] = "tampered-group"
    result = write_actual_brep_surface_evidence_pack_v2(
        tmp_path / "tampered",
        source,
        explicit_mapping=mapping,
        owner_face_by_edge=owners,
        requested_layers=1,
        domain_side_authority_fixture=True,
    )
    assert result["accepted"] is False
    assert result["candidate_discarded"] is True
    assert not (tmp_path / "tampered").exists()
