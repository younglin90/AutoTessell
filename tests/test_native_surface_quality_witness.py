import numpy as np
from core.evaluator.native_surface_quality_adapters import CanonicalSurfaceQualityInput
from core.evaluator.native_canonical_quality_witness import (
    build_canonical_surface_quality_witness,
    build_repeated_surface_quality_witness,
)

def test_square_quad_and_positive_bl_receipt(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_quality_witness_build")
    stack = {
        "source_points": np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float64),
        "edges": np.array([[17, 0, 1, 0]], dtype=np.int64),
        "layer_points": np.array(
            [[[[0.0, 0.1, 0.0], [1.0, 0.1, 0.0]]]], dtype=np.float64
        ),
        "normals": np.array([[0.0, 0.0, 1.0]], dtype=np.float64),
        "provenance": [{
            "source_wall_edge": 17,
            "source_face": 3,
            "layer": 1,
            "patch": "wall",
            "feature": "straight",
            "physical_group": "fluid",
            "component": "body",
            "provenance": "source-ledger",
            "generated_vertices": (0, 1),
        }],
        "collision_witness": [{
            "visible": True,
            "collision": False,
            "method": "synthetic-clearance",
        }],
        "geodesic_witness": [{
            "status": "measured",
            "distance": 0.1,
            "path_digest": "path-1",
            "method": "synthetic-geodesic",
        }],
    }
    item = CanonicalSurfaceQualityInput(
        vertices=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0]], dtype=np.float64),
        triangles=np.empty((0,3), dtype=np.int64), quads=np.array([[0,1,2,3]], dtype=np.int64),
        triangle_reference_normals=None, quad_reference_normals=((0.0,0.0,1.0),),
        source_sha256="a"*64, output_sha256="b"*64, source_face_lineage=(0,),
        patch_ids=("wall",), physical_groups=("fluid",), feature_ids=(0,),
        source_authority={"authority_ready": True},
        requested_layers=1, actual_layers=1, wall_edge_stack=stack,
    )
    result = build_canonical_surface_quality_witness(
        tmp_path, surface_input=item, strict_closed=False
    )
    assert result["accepted"] is True
    assert result["quality"]["quad_scaled_jacobian"]["min"] == 1.0
    assert result["boundary_layer"]["requested_layers"] == 1
    assert result["boundary_layer"]["positive_thickness"] is True
    assert result["wall_edge_quality"]["frozen_front"]["status"] == "frozen"
    repeated = build_repeated_surface_quality_witness(
        tmp_path, surface_input=item, strict_closed=False
    )
    assert repeated["accepted"] is True
    assert repeated["witness_repeats"] == [repeated["witness_sha256"]] * 3

    missing = item.__class__(
        vertices=item.vertices, triangles=item.triangles, quads=item.quads,
        triangle_reference_normals=item.triangle_reference_normals,
        quad_reference_normals=item.quad_reference_normals,
        source_sha256=item.source_sha256, output_sha256=item.output_sha256,
        source_face_lineage=item.source_face_lineage, patch_ids=item.patch_ids,
        physical_groups=item.physical_groups, feature_ids=item.feature_ids,
        source_authority=item.source_authority,
        requested_layers=1, actual_layers=1,
    )
    refused = build_canonical_surface_quality_witness(
        tmp_path, surface_input=missing, strict_closed=False
    )
    assert refused["reason"] == "surface_wall_edge_layer_ledger_missing"


def test_closed_cube_surface_topology_and_triangle_metric(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "/tmp/autotessell_quality_witness_build")
    vertices = np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]], dtype=np.float64)
    triangles = np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[3,7,6],[3,6,2],[0,4,7],[0,7,3],[1,2,6],[1,6,5]], dtype=np.int64)
    item = CanonicalSurfaceQualityInput(
        vertices=vertices, triangles=triangles, quads=np.empty((0,4), dtype=np.int64),
        triangle_reference_normals=None, quad_reference_normals=None,
        source_sha256="a"*64, output_sha256="b"*64,
        source_face_lineage=tuple(range(12)), patch_ids=tuple("wall" for _ in range(12)),
        physical_groups=tuple("fluid" for _ in range(12)), feature_ids=tuple(range(12)),
        source_authority={"authority_ready": True},
    )
    result = build_canonical_surface_quality_witness(tmp_path, surface_input=item)
    assert result["accepted"] is True
    assert result["topology"]["closed_manifold"] is True
    assert result["quality"]["tri_mean_ratio"]["max"] > 0.0
