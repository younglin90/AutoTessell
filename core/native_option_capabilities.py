"""Truthful capability metadata for native input application receipts.

This registry describes the current wrapper-to-runner contract. It does not
promote an option to release support merely because it appears in a schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NativeOptionCapability:
    engine: str
    contract_key: str
    runner_key: str | None
    route: str
    release_ready: bool = False


_ROUTES = {
    "native_tet": "tier_native_tet -> run_native_tet_harness",
    "native_hex": "tier_native_hex -> generate_native_hex",
    "native_poly": "tier_native_poly -> run_native_poly_research/quality-harness/voronoi",
}

_KNOWN = {
    # These keys are accepted by the actual native wrapper/kernel signature.
    # Keeping the registry signature-derived prevents a GUI field from being
    # reported as applied while the wrapper still drops it.
    "native_tet": {
        "seed_density", "max_iter", "target_cells", "sliver_quality_threshold",
        "max_input_vertices", "enable_auto_fix_input", "enable_phase_a",
        "feature_angle_deg", "recovery_iterations", "protect_boundary_faces",
        "smooth_iterations", "smooth_relax", "enable_bsp_insertion",
        "bsp_max_inserts_per_triangle", "enable_edge_recovery",
        "edge_recovery_max_iter", "enable_phase_b", "local_ops_iterations",
        "split_ratio", "collapse_ratio", "flip_iterations",
        "tangent_smooth_iterations", "tangent_smooth_relax",
        "max_collapses_per_iter", "cell_drop_rollback_ratio",
        "sliver_drop_min_dihedral_deg", "sliver_drop_max_aspect",
        "enable_phase_c", "envelope_eps_relative", "quality_target_min_q",
        "quality_improvement_eps", "quality_window", "min_final_vertices",
        "enable_same_side_retriangulation", "allow_external_fallback",
        "use_adaptive_sizing", "use_anisotropic_metric", "anisotropic_ratio",
        "adaptive_min_ratio", "adaptive_max_ratio", "adaptive_curvature_gain",
        "enable_amips_smooth", "amips_iterations", "amips_alpha",
        "chunked_delaunay_threshold", "enable_chunked_delaunay", "chunked_n_div",
        "enable_edge_steiner", "edge_steiner_count", "enable_cdt_recovery",
        "cdt_recovery_max_cycles", "cdt_recovery_points_budget",
        "cdt_recovery_outer_iter", "cdt_recovery_target_ratio",
        "enable_boundary_clip", "boundary_clip_threshold", "score_weight_area",
        "score_weight_cdt", "score_weight_mq", "prefer_base_threshold",
        "use_torch_amips", "qed_min_faces", "enable_stellar_split",
    },
    "native_hex": {
        "seed_density", "target_cells", "max_cells", "bl_layers",
        "post_layers_num_layers", "max_cells_per_axis", "snap_boundary",
        "preserve_features", "feature_angle_deg", "adaptive", "n_levels",
        "refinement_distance_factor", "snap_iterations", "enable_post_smooth",
        "post_smooth_iterations", "post_smooth_relax", "hex_buffer_cells",
    },
    "native_poly": {
        "seed_density", "max_iter", "target_cells", "max_cells",
        "max_tet_cells", "smooth_iters", "smooth_relax", "n_lloyd",
        "auto_escalate", "auto_escalate_max", "bl_layers",
        "post_layers_num_layers",
    },
}


def canonical_engine(value: str) -> str:
    key = str(value or "").strip().lower()
    if key.startswith("tier_"):
        key = key[5:]
    if key in {"native_tri", "strict_quad", "tri_quad"}:
        return key
    if key == "tri":
        return "native_tri"
    return key if key in _ROUTES else "native_tet"


def capability(engine: str, key: str) -> NativeOptionCapability | None:
    selected = canonical_engine(engine)
    if key not in _KNOWN.get(selected, set()):
        return None
    return NativeOptionCapability(
        engine=selected,
        contract_key=key,
        runner_key=key,
        route=_ROUTES[selected],
    )


def receipt_for_run(
    *,
    engine: str,
    forwarded: dict[str, Any],
    success: bool,
    result: Any,
) -> dict[str, Any]:
    """Build a post-run receipt without claiming unsupported options applied."""
    selected = canonical_engine(engine)
    records: list[dict[str, Any]] = []
    for key, value in sorted(forwarded.items()):
        if key in {"target_edge_length", "source_path", "source_vertices", "source_faces",
                   "source_provenance", "input_config", "input_parameter_report", "native_poly_source_certificate"}:
            continue
        cap = capability(selected, key)
        if cap is None:
            status = "unsupported"
            route = None
        elif success:
            status = "applied_verified"
            route = cap.route
        else:
            status = "rejected"
            route = cap.route
        records.append({
            "pointer": f"/engine_options/{selected.removeprefix('native_')}/{key}",
            "requested": value,
            "effective": value if status == "applied_verified" else None,
            "status": status,
            "route": route,
            "kernel_receipt": {
                "result_success": bool(success),
                "result_type": type(result).__name__,
                "result_route": getattr(result, "route", None),
            },
        })
    return {
        "engine": selected,
        "route": _ROUTES.get(selected),
        "records": records,
        "applied_verified": [r["pointer"] for r in records if r["status"] == "applied_verified"],
        "unsupported": [r["pointer"] for r in records if r["status"] == "unsupported"],
        "rejected": [r["pointer"] for r in records if r["status"] == "rejected"],
    }
