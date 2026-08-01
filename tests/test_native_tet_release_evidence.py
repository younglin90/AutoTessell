"""Native Tet Gate4 authority certificate integration."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.evaluator.native_tet_release_evidence import certify_native_tet_release_output
from core.generator.native_tet.mesher import generate_native_tet


def test_native_tet_written_cube_has_authoritative_shape_patch_group_certificate(tmp_path: Path) -> None:
    source_path = Path("tests/benchmarks/cube.stl")
    mesh = read_stl(source_path)
    result = generate_native_tet(
        np.asarray(mesh.vertices),
        np.asarray(mesh.faces),
        tmp_path,
        seed_density=4,
        sliver_quality_threshold=0.0,
        enable_same_side_retriangulation=True,
        enable_phase_a=False,
        recovery_iterations=0,
        smooth_iterations=0,
    )
    assert result.success, result.message
    face_count = len(mesh.faces)
    certificate = certify_native_tet_release_output(
        tmp_path,
        source_path,
        mesh.vertices,
        mesh.faces,
        result.tet_points,
        result.tets,
        source_feature_ids=("none",) * face_count,
        source_patch_ids=("wall",) * face_count,
        source_physical_groups=("wall",) * face_count,
        debug_info=result.debug_info,
    )
    assert certificate.authoritative
    assert certificate.source_vertices_preserved
    assert certificate.source_faces_preserved
    assert certificate.feature_preserved
    assert certificate.patch_preserved
    assert certificate.physical_groups_preserved
    assert certificate.component_bijection
    assert certificate.provenance_complete
