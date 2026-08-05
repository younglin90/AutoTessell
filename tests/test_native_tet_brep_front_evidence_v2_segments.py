"""Triangle-local actual B-Rep segment identity and parameter gates."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, "/tmp/autotessell_surface_bl_front_shared_build")
from native_brep_front_evidence_v2 import validate_brep_front_evidence_v2  # noqa: E402

from core.analyzer.readers.step import load_cad_native_with_provenance
from core.layers.native_tet_brep_front_evidence_v2 import (
    build_brep_front_evidence_v2,
)
from tests.test_cad_xde_physical_authority import _write_styled_box
from tests.test_native_tet_brep_front_evidence_v2 import _explicit_owner_map


def test_actual_edge_segments_are_explicit_and_cross_checked(tmp_path: Path) -> None:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    cad = load_cad_native_with_provenance(source, ".step")
    payload = build_brep_front_evidence_v2(
        cad,
        source_digest=hashlib.sha256(source.read_bytes()).hexdigest(),
        owner_face_by_edge=_explicit_owner_map(cad),
    )
    assert validate_brep_front_evidence_v2(payload)["accepted"] is True
    for triangle in payload["triangles"]:
        for edge_id, segment_id, parameters in zip(
            triangle["brep_edge_ids"],
            triangle["brep_edge_segment_ids"],
            triangle["brep_edge_segment_parameters"],
            strict=True,
        ):
            if edge_id < 0:
                assert segment_id == -1
            else:
                assert segment_id == 0
                assert parameters == [0.0, 1.0]
    assert all(edge["segments"] == [{"segment_id": 0, "t0": 0.0, "t1": 1.0}] for edge in payload["edges"])

    mutated = dict(payload)
    mutated["triangles"] = [dict(triangle) for triangle in payload["triangles"]]
    mutated["triangles"][0]["brep_edge_segment_ids"] = [99, 0, -1]
    result = validate_brep_front_evidence_v2(mutated)
    assert result["accepted"] is False
    assert result["reason"] == "triangle_edge_segment_unknown"
