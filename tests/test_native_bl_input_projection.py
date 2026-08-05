"""Card C: normalized BL selectors reach the layer-post namespace."""

from __future__ import annotations

from core.input_contract import normalize_input_contract, project_legacy_parameters


def test_wall_face_edge_and_yplus_projection_is_explicit() -> None:
    normalized = normalize_input_contract(
        {
            "boundary_layers": [
                {
                    "layers": 2,
                    "spacing_mode": "target_y_plus",
                    "target_y_plus": 1.0,
                    "wall_face_groups": ["wall"],
                    "wall_edge_groups": ["leading_edge"],
                    "excluded_groups": ["symmetry"],
                    "height_field": "wall_height",
                    "feature_angle_deg": 30.0,
                }
            ]
        },
        engine="native_tet",
        strict=False,
    )
    projected = project_legacy_parameters(normalized.config, "native_tet")
    assert projected["bl_layers"] == 2
    assert projected["post_layers_wall_patch_names"] == ["wall"]
    assert projected["post_layers_wall_edge_groups"] == ["leading_edge"]
    assert projected["post_layers_ignore_patch_names"] == ["symmetry"]
    assert projected["bl_target_y_plus"] == 1.0
    assert projected["bl_height_field"] == "wall_height"
    assert projected["bl_feature_angle_deg"] == 30.0


def test_zero_layers_still_projects_identity_without_wall_activation() -> None:
    normalized = normalize_input_contract(
        {"boundary_layers": [{"layers": 0, "wall_face_groups": ["wall"]}]},
        engine="native_hex",
        strict=False,
    )
    projected = project_legacy_parameters(normalized.config, "native_hex")
    assert projected["bl_layers"] == 0
    assert projected["post_layers_wall_patch_names"] == ["wall"]
