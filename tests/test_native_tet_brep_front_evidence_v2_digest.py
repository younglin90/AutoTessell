"""C++ v2 provenance digest recomputation gates."""

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


def test_cpp_recomputes_all_v2_provenance_digests(tmp_path: Path) -> None:
    source = tmp_path / "styled-box.step"
    _write_styled_box(source)
    cad = load_cad_native_with_provenance(source, ".step")
    payload = build_brep_front_evidence_v2(
        cad,
        source_digest=hashlib.sha256(source.read_bytes()).hexdigest(),
        owner_face_by_edge=_explicit_owner_map(cad),
    )
    for field in ("canonical_positions_digest", "face_ordinal_digest", "orientation_digest", "seam_digest"):
        mutated = dict(payload)
        mutated[field] = "0" * 64
        result = validate_brep_front_evidence_v2(mutated)
        assert result["accepted"] is False
        assert "digest" in result["reason"]
