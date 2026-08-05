from __future__ import annotations

from core.input_contract import input_schema_document, normalize_input_contract


def test_schema_exposes_quality_first_controls_from_user_contract() -> None:
    document = input_schema_document()
    catalog = set(document["field_catalog"])
    expected = {
        "sizing.boundary_size_extension",
        "sizing.proximity.cells_across_gap",
        "surface.preserve_physical_groups",
        "surface.maximum_quad_warpage",
        "surface.min_triangle_angle_deg",
        "surface.project_vertices_to_source",
        "quality.max_boundary_skewness",
        "quality.min_volume_ratio",
        "quality.boundary_layer.max_metric_aspect_ratio",
        "boundary_layers.wall_edge_groups",
        "boundary_layers.collision_buffer",
        "boundary_layers.entity_dimension",
        "boundary_layers.spacing",
        "engine_options.tet.cell_radius_edge_ratio_max",
        "engine_options.hex.minimum_cut_cell_volume_fraction",
        "engine_options.poly.face_planarity_tolerance",
        "engine_options.strict_quad.allow_triangles",
        "engine_options.tri_quad.target_quad_fraction",
    }
    assert expected <= catalog
    descriptors = {item["capability_key"]: item for item in document["field_descriptors"]}
    assert descriptors["input.inside_points"]["value_type"] == "json"
    assert descriptors["input.inside_points"]["control"] == "textarea"
    assert descriptors["local_controls"]["value_type"] == "json"



def test_nested_bl_spacing_is_normalized_and_preserved_for_bl0_and_bl1() -> None:
    bl1 = normalize_input_contract({
        "schema_version": "1.0",
        "input": {"units": "mm"},
        "boundary_layers": [{
            "entity_dimension": "edge",
            "selector": {"physical_groups": ["wall"]},
            "layers": 1,
            "spacing": {
                "mode": "first_and_growth",
                "first_height": 0.01,
                "growth_rate": 1.2,
            },
        }],
    }, engine="native_tri")
    entry = bl1.config["boundary_layers"][0]
    assert entry["spacing_mode"] == "first_and_growth"
    assert entry["first_height"] == 1.0e-5
    assert entry["spacing"]["first_height"] == 1.0e-5
    assert entry["growth_rate"] == 1.2
    assert "boundary_layers[0].first_height" in bl1.report["derived"]

    bl0 = normalize_input_contract({
        "schema_version": "1.0",
        "boundary_layers": [{"layers": 0, "spacing": {"mode": "invalid"}}],
    }, engine="native_tri")
    assert bl0.config["boundary_layers"][0]["status"] == "disabled_identity"
    assert bl0.report["errors"] == []

def test_contract_preserves_array_and_engine_specific_user_values() -> None:
    raw = {
        "schema_version": "1.0",
        "target": {"mode": "soft", "count": 1200, "tolerance": 0.15},
        "input": {"inside_points": [[0.1, 0.2, 0.3]]},
        "surface": {"preserve_physical_groups": True},
        "quality": {"max_boundary_skewness": 0.35},
        "boundary_layers": [{"layers": 0, "wall_edge_groups": ["wall"]}],
        "local_controls": [{"selector": {"physical_groups": ["leading_edge"]}, "size": 0.01}],
        "engine_options": {"strict_quad": {"allow_triangles": False}},
    }
    result = normalize_input_contract(raw, engine="strict_quad")
    assert result.config["input"]["inside_points"] == [[0.1, 0.2, 0.3]]
    assert result.config["local_controls"][0]["selector"]["physical_groups"] == ["leading_edge"]
    assert result.config["engine_options"]["strict_quad"]["allow_triangles"] is False
