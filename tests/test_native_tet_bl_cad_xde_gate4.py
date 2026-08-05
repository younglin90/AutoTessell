"""CAD/XDE source binding boundary for the native Tet BL Gate4 contract."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.readers.step import load_cad_native, load_cad_native_with_provenance
from tests.test_cad_xde_physical_authority import _write_styled_box


def test_cad_xde_source_certificate_is_not_physical_group_authority(tmp_path: Path) -> None:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    legacy_vertices, legacy_faces = load_cad_native(source, ".step")
    result = load_cad_native_with_provenance(source, ".step")
    provenance = result.provenance

    assert np.array_equal(result.vertices, legacy_vertices)
    assert np.array_equal(result.faces, legacy_faces)
    assert provenance.face_count == 6
    assert provenance.xde_layer_authoritative is True
    assert provenance.xde_layer_coverage_count == provenance.face_count
    assert provenance.xde_metadata_sha256
    assert provenance.ordered_face_ordinal_sha256
    assert provenance.seam_connectivity_sha256
    assert provenance.xde_color_display_metadata_authoritative is True
    assert provenance.physical_groups_authoritative is False
    assert provenance.physical_group_names == (None,) * provenance.face_count
    assert provenance.xde_assembly_identity_authoritative is False
