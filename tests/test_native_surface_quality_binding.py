from core.evaluator.native_release_authority_gate import validate_native_surface_quality_binding

D = "a" * 64
O = "b" * 64
W = "c" * 64


def _surface_receipt(boundary_layer=None, wall_quality=None):
    return {
        "accepted": True,
        "source_sha256": D,
        "output_sha256": O,
        "witness_sha256": W,
        "witness_repeats": [W, W, W],
        "topology": {
            "closed_manifold": True,
            "boundary_edges": 0,
            "nonmanifold_edges": 0,
            "duplicate_faces": 0,
        },
        "quality": {},
        "n_triangles": 0,
        "n_quads": 1,
        "source_face_lineage": [0],
        "patch_ids": ["wall"],
        "physical_groups": ["fluid"],
        "feature_ids": [0],
        "boundary_layer": boundary_layer or {
            "requested_layers": 0,
            "actual_layers": 0,
        },
        **({"wall_edge_quality": wall_quality} if wall_quality is not None else {}),
    }


def row():
    return {
        "source_authority": {"authoritative": True, "sha256": D},
        "strict_topology": {"artifact_sha256": O},
        "source_output_authority": {"surface_quality": _surface_receipt()},
    }


def test_surface_quality_binding_accepts_three_identical_bl0_witnesses():
    result = validate_native_surface_quality_binding(row())
    assert result == {"valid": True, "reason": ""}


def test_surface_quality_binding_refuses_hash_mismatch():
    value = row()
    value["source_output_authority"]["surface_quality"]["output_sha256"] = D
    result = validate_native_surface_quality_binding(value)
    assert result["valid"] is False
    assert result["reason"] == "surface_quality_output_binding_mismatch"


def test_surface_quality_binding_accepts_measured_positive_bl():
    value = row()
    value["source_output_authority"]["surface_quality"] = _surface_receipt(
        boundary_layer={
            "requested_layers": 1,
            "actual_layers": 1,
            "positive_thickness": True,
        },
        wall_quality={
            "accepted": True,
            "actual_layers": 1,
        },
    )
    result = validate_native_surface_quality_binding(value)
    assert result == {"valid": True, "reason": ""}
