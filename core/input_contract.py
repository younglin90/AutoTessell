"""Versioned user meshing-input contract.

The web/Electron client sends this envelope instead of an ever-growing set of
flat keyword arguments.  This module deliberately owns normalization and
validation only; native kernels remain responsible for applying the options
they advertise in their capability table.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = "1.0"

_UNIT_SCALE = {
    "m": 1.0,
    "mm": 1.0e-3,
    "cm": 1.0e-2,
    "um": 1.0e-6,
    "in": 0.0254,
    "ft": 0.3048,
}

_SPACING_REQUIRED = {
    "first_and_growth": {"first_height", "growth_rate"},
    "first_and_total": {"first_height", "total_thickness"},
    "total_and_growth": {"total_thickness", "growth_rate"},
    "last_and_growth": {"last_height", "growth_rate"},
}

_LENGTH_KEYS = {
    "base_size", "min_size", "max_size", "first_height", "last_height",
    "total_thickness", "minimum_thickness", "maximum_thickness",
    "min_cell_size", "target_cell_size", "max_chordal_error",
    "defeature_size", "boundary_size_extension", "curvature_min_size",
    "proximity_min_size", "base_cell_size", "snap_tolerance",
}

# These are verified compatibility projections, not a claim that every
# parameter in the user contract is implemented by every native route.
_COMMON_APPLIED = {
    "target.count", "target.mode", "target.tolerance", "sizing.mode",
    "sizing.base_size", "sizing.min_size", "sizing.max_size",
    "sizing.growth_rate", "sizing.combine", "quality.preset",
    "quality.max_skewness", "quality.max_non_orthogonality_deg",
    "quality.max_core_aspect_ratio", "boundary_layers.layers",
    "boundary_layers.spacing_mode", "boundary_layers.first_height",
    "boundary_layers.last_height", "boundary_layers.total_thickness",
    "boundary_layers.growth_rate", "surface.topology", "surface.algorithm",
}

_ENGINE_OPTION_ALIASES = {
    "native_tet": ("native_tet", "tet"),
    "native_hex": ("native_hex", "hex"),
    "native_poly": ("native_poly", "poly"),
    "native_tri": ("native_tri", "tri"),
    "strict_quad": ("strict_quad",),
    "tri_quad": ("tri_quad",),
}

_ENGINE_APPLIED = {
    "native_tet": {
        "seed_density", "max_iter", "target_cells", "sliver_quality_threshold",
        "enable_amips_smooth", "enable_chunked_delaunay", "enable_cdt_recovery",
        "max_collapses_per_iter", "recovery_iterations",
    },
    "native_hex": {
        "seed_density", "target_cells", "max_cells_per_axis", "snap_boundary",
        "preserve_features", "feature_angle_deg", "snap_iterations",
        "adaptive", "n_levels", "refinement_distance_factor",
        "enable_post_smooth", "post_smooth_iterations", "post_smooth_relax",
    },
    "native_poly": {
        "seed_density", "max_iter", "target_cells", "max_cells",
        "max_tet_cells", "n_lloyd", "auto_escalate", "auto_escalate_max",
        "bl_layers", "post_layers_num_layers",
    },
    "native_tri": set(),
    "strict_quad": set(),
    "tri_quad": set(),
}


@dataclass(frozen=True)
class NormalizationResult:
    config: dict[str, Any]
    report: dict[str, Any]
    warnings: tuple[str, ...] = ()


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _finite_number(value: Any, pointer: str, errors: list[str]) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        errors.append(f"{pointer}: expected a number")
        return None
    if not math.isfinite(result):
        errors.append(f"{pointer}: expected a finite number")
        return None
    return result


def _present(mapping: dict[str, Any], key: str) -> bool:
    return key in mapping and mapping[key] is not None


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _legacy_to_contract(legacy: dict[str, Any]) -> dict[str, Any]:
    """Convert the old flat Web/Qt keys without losing explicit zero values."""
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "input": {},
        "target": {"mode": "soft"},
        "sizing": {},
        "surface": {},
        "volume": {},
        "boundary_layers": [],
        "quality": {},
        "local_controls": [],
        "engine_options": {},
        "optimization": {},
        "execution": {},
        "output": {},
        "_compatibility": {"legacy_flat": True},
    }
    if legacy.get("max_cells") is not None:
        try:
            result["target"]["count"] = int(legacy["max_cells"])
        except (TypeError, ValueError):
            result["target"]["count"] = legacy["max_cells"]
    if legacy.get("target_cells") is not None:
        try:
            result["target"]["count"] = int(legacy["target_cells"])
        except (TypeError, ValueError):
            result["target"]["count"] = legacy["target_cells"]
    for old, new in (
        ("base_cell_size", "base_size"),
        ("element_size", "base_size"),
        ("min_cell_size", "min_size"),
        ("max_cell_size", "max_size"),
        ("sizing_growth_rate", "growth_rate"),
    ):
        if old in legacy and legacy[old] is not None and legacy[old] != "":
            result["sizing"][new] = legacy[old]
    if "quality_profile" in legacy:
        result["quality"]["preset"] = legacy["quality_profile"]
    elif "quality" in legacy and isinstance(legacy["quality"], str):
        result["quality"]["preset"] = legacy["quality"]
    if "bl_layers" in legacy and legacy["bl_layers"] not in (None, ""):
        entry: dict[str, Any] = {"layers": legacy["bl_layers"]}
        aliases = (
            ("bl_spacing_mode", "spacing_mode"),
            ("bl_first_height", "first_height"),
            ("bl_last_height", "last_height"),
            ("bl_total_thickness", "total_thickness"),
            ("bl_growth_ratio", "growth_rate"),
            ("bl_wall_face_groups", "wall_face_groups"),
            ("bl_wall_edge_groups", "wall_edge_groups"),
        )
        for old, new in aliases:
            if old in legacy and legacy[old] is not None and legacy[old] != "":
                entry[new] = legacy[old]
        result["boundary_layers"] = [entry]
    # Keep all old engine knobs available in the report and compatibility path.
    for key, value in legacy.items():
        if key not in result and key not in {"input_config", "input"}:
            result["execution"].setdefault("legacy_flat", {})[key] = copy.deepcopy(value)
    return result


def _convert_lengths(node: Any, factor: float, pointer: str, derived: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in list(node.items()):
            child = f"{pointer}.{key}" if pointer else key
            if key in _LENGTH_KEYS and isinstance(value, (int, float)) and value != 0:
                node[key] = float(value) * factor
                derived.append(child)
            else:
                _convert_lengths(value, factor, child, derived)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _convert_lengths(value, factor, f"{pointer}[{index}]", derived)



def _normalize_nested_bl_spacing(config: dict[str, Any], derived: list[str]) -> None:
    """Accept the documented nested BL form without changing the canonical form."""
    layers = config.get("boundary_layers", [])
    if not isinstance(layers, list):
        return
    aliases = {
        "mode": "spacing_mode",
        "first_height": "first_height",
        "last_height": "last_height",
        "total_thickness": "total_thickness",
        "growth_rate": "growth_rate",
        "target_y_plus": "target_y_plus",
        "height_field": "height_field",
    }
    for index, entry in enumerate(layers):
        if not isinstance(entry, dict) or not isinstance(entry.get("spacing"), dict):
            continue
        spacing = entry["spacing"]
        for source, destination in aliases.items():
            if destination not in entry and source in spacing:
                entry[destination] = copy.deepcopy(spacing[source])
                derived.append(f"boundary_layers[{index}].{destination}")


def _validate_bl(config: dict[str, Any], errors: list[str], ignored: list[str]) -> None:
    layers = config.get("boundary_layers", [])
    if layers is None:
        config["boundary_layers"] = []
        return
    if not isinstance(layers, list):
        errors.append("/boundary_layers: expected an array")
        return
    for index, entry in enumerate(layers):
        pointer = f"/boundary_layers/{index}"
        if not isinstance(entry, dict):
            errors.append(f"{pointer}: expected an object")
            continue
        raw_layers = entry.get("layers", 0)
        try:
            count = int(raw_layers)
        except (TypeError, ValueError):
            errors.append(f"{pointer}/layers: expected a non-negative integer")
            continue
        if count < 0:
            errors.append(f"{pointer}/layers: must be >= 0")
            continue
        entry["layers"] = count
        if count == 0:
            entry["status"] = "disabled_identity"
            entry["actual_layers"] = 0
            ignored.append(f"{pointer}/spacing")
            continue
        mode = str(entry.get("spacing_mode", "first_and_growth"))
        entry["spacing_mode"] = mode
        if mode in _SPACING_REQUIRED:
            required = _SPACING_REQUIRED[mode]
            present = {key for key in ("first_height", "last_height", "total_thickness", "growth_rate") if _present(entry, key)}
            if present != required:
                errors.append(
                    f"{pointer}: {mode} requires exactly {sorted(required)}; got {sorted(present)}"
                )
            for key in required:
                if key not in entry:
                    continue
                value = _finite_number(entry[key], f"{pointer}/{key}", errors)
                if value is not None:
                    if key == "growth_rate" and value < 1.0:
                        errors.append(f"{pointer}/{key}: must be >= 1")
                    elif key != "growth_rate" and value <= 0.0:
                        errors.append(f"{pointer}/{key}: must be > 0")
                    else:
                        entry[key] = value
        elif mode == "target_y_plus":
            if not _present(entry, "target_y_plus"):
                errors.append(f"{pointer}/target_y_plus: required for target_y_plus mode")
        elif mode == "height_field":
            if not _present(entry, "height_field"):
                errors.append(f"{pointer}/height_field: required for height_field mode")
        else:
            errors.append(f"{pointer}/spacing_mode: unsupported value {mode!r}")
        if not any(entry.get(key) for key in ("wall_face_groups", "wall_edge_groups", "selector", "physical_group", "patch")):
            # Existing flat callers historically mean all authoritative walls.
            if config.get("_compatibility", {}).get("legacy_flat"):
                entry["selector"] = {"scope": "all_authoritative_walls", "source": "legacy_compatibility"}
            else:
                errors.append(f"{pointer}: a wall selector is required when layers >= 1")


def _classify(config: dict[str, Any], engine: str, ignored: list[str], derived: list[str]) -> dict[str, list[str]]:
    applied: list[str] = []
    pending: list[str] = []
    unsupported: list[str] = []
    for key in _COMMON_APPLIED:
        parent, _, leaf = key.partition(".")
        if isinstance(config.get(parent), dict) and leaf in config[parent]:
            applied.append(key)
    options = config.get("engine_options", {})
    selected_options = []
    if isinstance(options, dict):
        for option_key in _ENGINE_OPTION_ALIASES.get(engine, (engine,)):
            selected = options.get(option_key, {})
            if isinstance(selected, dict):
                selected_options.append((option_key, selected))
    try:
        from core.native_option_capabilities import _KNOWN
        _known_engine_options = set(_ENGINE_APPLIED.get(engine, set())) | set(
            _KNOWN.get(engine, set())
        )
    except Exception:
        _known_engine_options = set(_ENGINE_APPLIED.get(engine, set()))
    for option_key, selected in selected_options:
        for key in selected:
            pointer = f"engine_options.{option_key}.{key}"
            (applied if key in _known_engine_options else unsupported).append(pointer)
    for section in ("input", "sizing", "surface", "volume", "quality", "optimization", "execution", "output"):
        values = config.get(section)
        if isinstance(values, dict):
            for key in values:
                pointer = f"{section}.{key}"
                if pointer not in applied and pointer not in derived:
                    pending.append(pointer)
    for index, entry in enumerate(config.get("boundary_layers", [])):
        if not isinstance(entry, dict):
            continue
        if entry.get("layers", 0) == 0:
            ignored.append(f"boundary_layers[{index}]")
        for key in entry:
            pointer = f"boundary_layers[{index}].{key}"
            if key not in {"status", "actual_layers"} and pointer not in applied:
                pending.append(pointer)
    for index, entry in enumerate(config.get("local_controls", [])):
        if isinstance(entry, dict):
            pending.append(f"local_controls[{index}]")
    return {
        "applied": sorted(set(applied)),
        "derived": sorted(set(derived)),
        "ignored_by_policy": sorted(set(ignored)),
        "pending": sorted(set(pending)),
        "unsupported": sorted(set(unsupported)),
    }


def normalize_input_contract(
    raw: dict[str, Any] | None,
    *,
    legacy: dict[str, Any] | None = None,
    engine: str = "native_tet",
    strict: bool = True,
) -> NormalizationResult:
    """Normalize and validate a user envelope without dropping any fields."""
    if raw is not None and not isinstance(raw, dict):
        raise ValueError("input_config must be a JSON object")
    config = copy.deepcopy(raw) if raw is not None else _legacy_to_contract(dict(legacy or {}))
    if raw is not None and legacy:
        config = _deep_merge(config, _legacy_to_contract(legacy))
    config.setdefault("schema_version", SCHEMA_VERSION)
    if str(config["schema_version"]) != SCHEMA_VERSION:
        raise ValueError(f"unsupported input schema version: {config['schema_version']!r}")
    for section in ("input", "target", "sizing", "surface", "volume", "quality", "optimization", "execution", "output"):
        if section not in config:
            config[section] = {}
        elif not isinstance(config[section], dict):
            raise ValueError(f"input_config.{section} must be an object")
    if not isinstance(config.get("local_controls", []), list):
        raise ValueError("input_config.local_controls must be an array")
    units = str(config["input"].get("units", "m")).lower()
    if units not in _UNIT_SCALE:
        raise ValueError(f"input.units must be one of {sorted(_UNIT_SCALE)}")
    factor = _UNIT_SCALE[units] * float(config["input"].get("scale_factor", 1.0))
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError("input.scale_factor must be finite and > 0")
    derived: list[str] = []
    _normalize_nested_bl_spacing(config, derived)
    _convert_lengths(config, factor, "", derived)
    config["input"]["units"] = "m"
    config["input"]["scale_factor"] = 1.0
    target = config["target"]
    target.setdefault("mode", "soft")
    if target.get("mode") != "soft":
        raise ValueError("target.mode must be 'soft' for quality-first meshing")
    if target.get("count") is not None:
        count = _finite_number(target["count"], "/target/count", [])
        if count is None or count < 0 or int(count) != count:
            raise ValueError("target.count must be a non-negative integer or null")
        target["count"] = int(count)
    errors: list[str] = []
    ignored: list[str] = []
    _validate_bl(config, errors, ignored)
    if errors and strict:
        raise ValueError("; ".join(errors))
    warnings = tuple(errors) if errors else ()
    classification = _classify(config, engine, ignored, derived)
    # Presence in the contract is not proof of kernel application. The
    # post-run native receipt is the only source for applied_verified.
    classification["accepted_pending"] = sorted(set(
        classification.get("accepted_pending", []) + classification.get("applied", [])
    ))
    classification["applied"] = []
    classification["applied_verified"] = []
    report = {
        "schema_version": SCHEMA_VERSION,
        "engine": engine,
        "requested_digest": _digest(raw if raw is not None else legacy or {}),
        "normalized_digest": _digest(config),
        "errors": list(errors),
        **classification,
    }
    return NormalizationResult(config=config, report=report, warnings=warnings)


def project_legacy_parameters(config: dict[str, Any], engine: str = "native_tet") -> dict[str, Any]:
    """Project verified common controls to the current strategy/native keys."""
    result: dict[str, Any] = {}
    target = config.get("target", {})
    sizing = config.get("sizing", {})
    if target.get("count") is not None:
        result["target_cells"] = int(target["count"])
        # The versioned contract's target is soft. Preserve the old flat
        # compatibility projection, but never turn a nested target into a hard
        # max_cells cap unless the user explicitly supplied one.
        compatibility = config.get("_compatibility", {})
        if isinstance(compatibility, dict) and compatibility.get("legacy_flat"):
            result["max_cells"] = int(target["count"])
        for hard_key in ("hard_max_cells", "max_cells"):
            if hard_key in target and target[hard_key] is not None:
                result["max_cells"] = int(target[hard_key])
    aliases = (
        ("base_size", "base_cell_size"),
        ("min_size", "min_cell_size"),
        ("max_size", "max_cell_size"),
        ("growth_rate", "sizing_growth_rate"),
    )
    for source, destination in aliases:
        if source in sizing:
            result[destination] = sizing[source]
    layers = config.get("boundary_layers", [])
    if layers:
        entry = layers[0]
        if isinstance(entry, dict):
            result["bl_layers"] = int(entry.get("layers", 0))
            result["cfmesh_bl_n_layers"] = int(entry.get("layers", 0))
            for source, destination in (
                ("first_height", "bl_first_height"),
                ("last_height", "bl_last_height"),
                ("total_thickness", "bl_total_thickness"),
                ("growth_rate", "bl_growth_ratio"),
                ("spacing_mode", "bl_spacing_mode"),
            ):
                if source in entry:
                    result[destination] = entry[source]
            # Preserve selectors and wall-edge controls in the actual post
            # layer parameter namespace. Previously these values survived
            # only in input_config and were absent from the BL runner.
            for source, destination in (
                ("wall_face_groups", "post_layers_wall_patch_names"),
                ("wall_edge_groups", "post_layers_wall_edge_groups"),
                ("excluded_groups", "post_layers_ignore_patch_names"),
                ("target_y_plus", "bl_target_y_plus"),
                ("height_field", "bl_height_field"),
                ("feature_angle_deg", "bl_feature_angle_deg"),
                ("collision_safety", "bl_collision_safety"),
                ("collision_buffer", "bl_collision_buffer"),
                ("maximum_layer_iterations", "bl_maximum_layer_iterations"),
                ("layer_failure_policy", "bl_layer_failure_policy"),
                ("max_thickness_to_medial_ratio", "post_layers_max_total_ratio"),
                ("normal_smoothing_iterations", "post_layers_n_smooth_normals"),
                ("direction_smoothing_iterations", "post_layers_n_smooth_surface_normals"),
                ("minimum_layers", "post_layers_at_bottleneck"),
                ("per_patch_layers", "post_layers_patch_overrides"),
                ("per_patch_first_height", "post_layers_patch_overrides"),
            ):
                if source in entry:
                    result[destination] = copy.deepcopy(entry[source])
            # Keep every remaining BL control in the explicit post-layer
            # namespace.  A downstream layer engine may reject a control, but
            # it can no longer disappear between the Electron contract and the
            # selected native route.
            for source, value in entry.items():
                if source in {"layers", "status", "actual_layers", "spacing"}:
                    continue
                result.setdefault(
                    f"post_layers_contract_{source}",
                    copy.deepcopy(value),
                )
    options = config.get("engine_options", {})
    if isinstance(options, dict):
        for option_key in _ENGINE_OPTION_ALIASES.get(engine, (engine,)):
            selected = options.get(option_key, {})
            if isinstance(selected, dict):
                result.update(selected)
    return result


def input_schema_document() -> dict[str, Any]:
    """Return server-owned UI metadata; the web client does not duplicate it."""
    field_catalog = [
        "input.units", "input.scale_factor", "input.geometry_tolerance",
        "input.sewing_tolerance", "input.repair_policy", "input.defeature_size",
        "input.remove_sliver_faces", "input.merge_coincident_vertices",
        "input.preserve_components", "input.preserve_features",
        "input.preserve_physical_groups", "input.closed_surface_required",
        "input.region_selection", "input.inside_points", "input.embedded_entities",
        "input.periodic_pairs", "input.symmetry_groups",
        "target.count", "target.hard_max_cells", "target.kind", "target.mode", "target.tolerance",
        "sizing.mode", "sizing.base_size", "sizing.min_size",
        "sizing.max_size", "sizing.growth_rate", "sizing.combine",
        "sizing.curvature.enabled", "sizing.curvature.normal_angle_deg",
        "sizing.curvature.elements_per_2pi", "sizing.curvature.min_size",
        "sizing.proximity.enabled", "sizing.proximity.cells_across_gap",
        "sizing.proximity.min_size", "sizing.geometry_approximation.max_chordal_error",
        "sizing.geometry_approximation.max_normal_deviation_deg",
        "sizing.anisotropy.enabled", "sizing.anisotropy.max_ratio",
        "sizing.anisotropy.metric_tensor_field",
        "sizing.boundary_size_extension", "sizing.metric_tensor_field",
        "sizing.curvature_enabled", "sizing.curvature_normal_angle_deg",
        "sizing.curvature_elements_per_2pi", "sizing.curvature_min_size",
        "sizing.proximity_enabled", "sizing.cells_across_gap", "sizing.proximity_min_size",
        "sizing.max_chordal_error", "sizing.max_surface_normal_deviation_deg",
        "sizing.anisotropy_enabled", "sizing.max_anisotropy_ratio",
        "sizing.size_field_combine",
        "surface.topology", "surface.algorithm", "surface.feature_angle_deg",
        "surface.preserve_feature_edges", "surface.preserve_patches", "surface.preserve_patch_boundaries",
        "surface.min_angle_deg", "surface.chordal_error",
        "surface.normal_deviation_deg", "surface.min_face_size",
        "surface.max_face_size", "surface.smoothing_iterations",
        "surface.optimization_iterations", "surface.edge_flip",
        "surface.split_collapse", "surface.cross_field", "surface.singularity_policy",
        "surface.smoothing_method", "surface.smoothing_relaxation",
        "quality.boundary_layer.max_metric_skewness",
        "quality.boundary_layer.max_metric_aspect_ratio",
        "quality.boundary_layer.max_wall_normal_deviation_deg",
        "quality.boundary_layer.failure_action",
        "surface.edge_flip_passes", "surface.split_collapse_passes",
        "surface.optimization_passes", "surface.preserve_physical_groups",
        "surface.surface_algorithm", "surface.surface_topology",
        "surface.min_triangle_angle_deg", "surface.max_chordal_error",
        "surface.max_normal_deviation_deg",
        "surface.project_vertices_to_source", "surface.quad_alignment",
        "surface.cross_field_smoothing", "surface.singularity_budget",
        "surface.patch_layout_mode", "surface.minimum_quad_quality",
        "surface.maximum_quad_warpage", "surface.allow_triangles",
        "surface.target_quad_fraction", "surface.minimum_quad_fraction",
        "surface.maximum_quad_fraction", "surface.transition_pattern",
        "surface.triangles_allowed_on", "surface.feature_aligned_quads",
        "volume.algorithm", "volume.element_order", "volume.base_size",
        "volume.min_size", "volume.max_size",
        "quality.preset", "quality.max_skewness",
        "quality.max_non_orthogonality_deg", "quality.max_core_aspect_ratio",
        "quality.min_mean_ratio", "quality.min_scaled_jacobian",
        "quality.min_determinant", "quality.max_face_warpage_deg",
        "quality.min_cell_volume", "quality.max_bl_metric_skewness",
        "quality.max_bl_metric_aspect_ratio", "quality.max_wall_normal_deviation_deg",
        "quality.failure_action",
        "quality.max_boundary_skewness", "quality.max_internal_skewness",
        "boundary_layers.entity_dimension", "boundary_layers.spacing", "boundary_layers.selector",
        "quality.min_face_area", "quality.max_concavity_deg", "quality.min_face_weight",
        "quality.min_volume_ratio", "quality.min_tet_dihedral_deg",
        "quality.max_tet_dihedral_deg", "quality.max_twist",
        "quality.min_normalized_determinant",
        "boundary_layers.layers", "boundary_layers.spacing_mode",
        "boundary_layers.first_height", "boundary_layers.last_height",
        "boundary_layers.total_thickness", "boundary_layers.growth_rate",
        "boundary_layers.relative_to_local_size", "boundary_layers.minimum_thickness",
        "boundary_layers.maximum_thickness", "boundary_layers.wall_face_groups",
        "boundary_layers.wall_edge_groups", "boundary_layers.excluded_groups",
        "boundary_layers.per_patch_layers", "boundary_layers.per_patch_first_height",
        "boundary_layers.adapt_wall_spacing", "boundary_layers.match_periodic_layers",
        "boundary_layers.feature_angle_deg", "boundary_layers.corner_policy",
        "boundary_layers.concave_corner_policy", "boundary_layers.convex_corner_policy",
        "boundary_layers.full_layers", "boundary_layers.minimum_layers",
        "boundary_layers.allow_local_layer_termination",
        "boundary_layers.termination_buffer_cells", "boundary_layers.collision_buffer",
        "boundary_layers.max_thickness_to_medial_ratio",
        "optimization.optimization_priority", "optimization.allow_boundary_motion",
        "optimization.preserve_topology", "optimization.preserve_source",
        "optimization.preserve_provenance",
        "optimization.allow_quality_degradation", "optimization.max_quality_regression",
        "boundary_layers.max_face_thickness_ratio", "boundary_layers.isotropic_stop_factor",
        "boundary_layers.transition_growth_rate", "boundary_layers.constant_first_layers",
        "boundary_layers.normal_smoothing_iterations",
        "boundary_layers.direction_smoothing_iterations",
        "boundary_layers.thickness_smoothing_iterations",
        "boundary_layers.smoothing_relaxation", "boundary_layers.maximum_layer_iterations",
        "boundary_layers.layer_failure_policy",
        "boundary_layers.target_y_plus", "boundary_layers.height_field",
        "local_controls", "engine_options.tet", "engine_options.hex",
        "engine_options.poly", "engine_options.tri", "engine_options.native_tri",
        "engine_options.strict_quad",
        "engine_options.tri_quad", "optimization.priority",
        "optimization.untangle", "optimization.smoothing", "optimization.node_relocation",
        "optimization.edge_flip", "optimization.split_collapse",
        "optimization.maximum_iterations", "execution.strict_release", "execution.deterministic",
        "execution.random_seed", "execution.threads", "execution.timeout_seconds",
        "execution.memory_limit", "execution.allow_algorithm_fallback",
        "execution.allow_product_fallback", "output.format", "output.binary",
        "output.partition_count", "output.preserve_ids",
        "output.write_quality_report", "output.write_provenance_report",
        "optimization.optimization_enabled", "optimization.untangle_iterations",
        "optimization.smoothing_iterations", "optimization.node_relocation_iterations",
        "optimization.edge_flip_iterations", "optimization.split_collapse_iterations",
        "optimization.maximum_total_iterations", "optimization.timeout_seconds",
        "optimization.memory_limit_mb", "optimization.fallback_policy",
        "execution.fallback_policy", "output.output_format", "output.binary_output",
        "output.write_failed_candidate_metrics",
    ]
    field_catalog.extend([
        "engine_options.tet.tet_algorithm", "engine_options.tet.cell_radius_edge_ratio_max",
        "engine_options.tet.min_tet_dihedral_deg", "engine_options.tet.max_tet_dihedral_deg",
        "engine_options.tet.sliver_removal", "engine_options.tet.sliver_threshold",
        "engine_options.tet.odt_iterations", "engine_options.tet.lloyd_iterations",
        "engine_options.tet.perturb_iterations", "engine_options.tet.exude_iterations",
        "engine_options.tet.feature_protection_radius", "engine_options.tet.preserve_surface_mesh",
        "engine_options.tet.boundary_recovery_policy",
        "engine_options.hex.hex_algorithm", "engine_options.hex.base_cell_size",
        "engine_options.hex.minimum_refinement_level", "engine_options.hex.maximum_refinement_level",
        "engine_options.hex.surface_refinement_level", "engine_options.hex.feature_refinement_level",
        "engine_options.hex.cells_between_refinement_levels", "engine_options.hex.snap_to_surface",
        "engine_options.hex.snap_tolerance", "engine_options.hex.snap_smoothing_iterations",
        "engine_options.hex.snap_relaxation_iterations",
        "engine_options.hex.minimum_cut_cell_volume_fraction", "engine_options.hex.minimum_hex_fraction",
        "engine_options.hex.allow_pyramids", "engine_options.hex.allow_prisms",
        "engine_options.hex.allow_split_hex", "engine_options.hex.inside_points",
        "engine_options.hex.region_seed_points",
        "engine_options.poly.poly_seed_mesh", "engine_options.poly.dualization_mode",
        "engine_options.poly.agglomeration_mode", "engine_options.poly.agglomeration_angle_deg",
        "engine_options.poly.minimum_faces_per_cell", "engine_options.poly.maximum_faces_per_cell",
        "engine_options.poly.maximum_cell_concavity_deg", "engine_options.poly.minimum_face_area",
        "engine_options.poly.centroidal_relaxation_iterations",
        "engine_options.poly.face_planarity_tolerance", "engine_options.poly.preserve_boundary_faces",
        "engine_options.poly.preserve_layer_cells", "engine_options.poly.target_count_tolerance",
        "engine_options.tri.tri_algorithm",
        "engine_options.native_tri.actual_surface",
        "engine_options.strict_quad.quad_alignment", "engine_options.strict_quad.cross_field_smoothing",
        "engine_options.strict_quad.singularity_budget", "engine_options.strict_quad.patch_layout_mode",
        "engine_options.strict_quad.minimum_quad_quality", "engine_options.strict_quad.maximum_quad_warpage",
        "engine_options.strict_quad.allow_triangles",
        "engine_options.tri_quad.target_quad_fraction", "engine_options.tri_quad.minimum_quad_fraction",
        "engine_options.tri_quad.maximum_quad_fraction", "engine_options.tri_quad.transition_pattern",
        "engine_options.tri_quad.triangles_allowed_on", "engine_options.tri_quad.feature_aligned_quads",
        "engine_options.tri_quad.minimum_quad_quality",
    ])
    # Native option cards are generated from the same capability registry that
    # produces post-run receipts; Electron therefore does not duplicate or
    # invent engine defaults.
    try:
        from core.native_option_capabilities import _KNOWN
    except Exception:  # pragma: no cover - schema remains usable if registry is unavailable
        _KNOWN = {}
    option_alias = {"native_tet": "tet", "native_hex": "hex", "native_poly": "poly"}
    for native_engine, keys in _KNOWN.items():
        alias = option_alias.get(native_engine)
        if alias:
            field_catalog.extend(f"engine_options.{alias}.{key}" for key in sorted(keys))
    integer_tokens = (
        "count", "layers", "iterations", "levels", "cells", "seed_density",
        "elements_per_2pi", "partition_count", "maximum", "n_lloyd",
    )
    boolean_tokens = (
        "enabled", "enable_", "use_", "preserve", "remove", "merge", "closed", "allow_",
        "deterministic", "strict_", "untangle", "smoothing", "relocation", "edge_flip",
        "split_collapse", "snap_boundary", "adaptive", "full_layers",
        "match_periodic", "adapt_wall", "optimization", "binary",
    )
    json_fields = {
        "input.region_selection", "input.inside_points", "input.embedded_entities",
        "input.periodic_pairs", "input.symmetry_groups", "sizing.metric_tensor_field",
        "sizing.anisotropy.metric_tensor_field", "boundary_layers.wall_face_groups",
        "boundary_layers.wall_edge_groups", "boundary_layers.excluded_groups",
        "boundary_layers.per_patch_layers", "boundary_layers.per_patch_first_height",
        "boundary_layers.height_field", "boundary_layers.spacing", "boundary_layers.selector", "local_controls",
        "engine_options.hex.inside_points", "engine_options.hex.region_seed_points",
        "engine_options.native_tri.actual_surface",
    }
    descriptors = []
    for path in field_catalog:
        parts = path.split('.')
        leaf = parts[-1]
        value_type = "boolean" if any(token in leaf for token in boolean_tokens) else (
            "integer" if any(token in leaf for token in integer_tokens) else "number"
        )
        control = "checkbox" if value_type == "boolean" else "number"
        if value_type == "number" and not any(token in leaf for token in (
            "size", "thickness", "ratio", "angle", "error", "volume",
            "factor", "distance", "relaxation", "skewness", "aspect",
            "deviation", "determinant", "ratio", "growth", "y_plus",
        )):
            control = "text"
            value_type = "string"
        if path in json_fields:
            control = "textarea"
            value_type = "json"
        descriptors.append({
            "pointer": "/" + "/".join(parts),
            "section": parts[0],
            "group": parts[1] if len(parts) > 1 else parts[0],
            "level": "basic" if parts[0] in {"target", "sizing", "quality", "boundary_layers"} else "advanced",
            "label": leaf.replace('_', ' '),
            "control": control,
            "value_type": value_type,
            "unit": "m" if any(token in leaf for token in ("size", "thickness", "height", "error", "volume")) else None,
            "minimum": 0 if value_type in {"number", "integer"} else None,
            "enum": None,
            "visible_when": [],
            "capability_key": path,
            "default_policy": "unset",
            "help": "unset = engine/source derived; value is applied only when the route reports support.",
        })
    return {
        "field_catalog": field_catalog,
        "field_descriptors": descriptors,
        "schema_version": SCHEMA_VERSION,
        "title": "AutoTessell native quality-first input contract",
        "target_modes": ["soft"],
        "units": sorted(_UNIT_SCALE),
        "spacing_modes": sorted((*_SPACING_REQUIRED, "target_y_plus", "height_field")),
        "sections": [
            {"key": key, "level": "advanced" if key not in {"target", "sizing", "quality", "boundary_layers"} else "basic"}
            for key in ("input", "target", "sizing", "surface", "volume", "boundary_layers", "quality", "local_controls", "engine_options", "optimization", "execution", "output")
        ],
        "template": {
            "schema_version": SCHEMA_VERSION,
            "target": {"mode": "soft", "count": None, "hard_max_cells": None, "tolerance": None},
            "sizing": {}, "surface": {}, "volume": {}, "boundary_layers": [],
            "quality": {}, "local_controls": [],
            "engine_options": {"tet": {}, "hex": {}, "poly": {}, "tri": {}, "native_tri": {}, "strict_quad": {}, "tri_quad": {}},
            "optimization": {}, "execution": {"strict_release": True}, "output": {},
        },
    }



