from __future__ import annotations

import pytest

pytest.importorskip("OCP")

from scripts.build_native_release_matrix import make_cad_sources, run_hex_xde


def test_anisotropic_xde_row_has_authority_receipt_digest_and_repeatability(tmp_path) -> None:
    sources = make_cad_sources(tmp_path / "campaign")
    row = run_hex_xde(
        tmp_path / "campaign" / "cases",
        "native-hex-anisotropic-xde",
        sources["anisotropic_xde"],
    )
    assert row["id"] == "native-hex-anisotropic-xde"
    assert row["engine"] == "hex"
    assert row["route"] == "native_hex_stepcaf_xde_anisotropic_release"
    assert row["source_authority"]["authoritative"] is True
    assert row["strict_topology"]["valid"] is True
    assert row["strict_topology"]["n_inverted_cells"] == 0
    assert row["boundary_layer"]["layers"] == 1
    assert row["boundary_layer"]["positive_first_layer_height"] > 0.0
    assert row["boundary_layer"]["positive_cell_count"] > 0
    assert row["repeatability"]["run_count"] == 3
    assert row["repeatability"]["byte_identical"] is True
    certificate = row["source_output_authority"]
    assert certificate["authoritative"] is True
    assert len(certificate["source_shape_sha256"]) == 64
    assert len(certificate["output_shape_sha256"]) == 64
    assert certificate["source_face_provenance"] is True
    assert certificate["quality_witness"]["accepted"] is True
    assert certificate["boundary_receipt"]["accepted"] is True
    assert len(certificate["boundary_receipt_sha256"]) == 64
    witness = certificate["native_artifact_digest"]
    assert witness["valid"] is True
    assert witness["status"] == "native_recomputed"
    assert witness["witness_repeats"] == [witness["tree_sha256"]] * 3
