"""Runtime projection for the versioned native-engine input contract.

The input contract is intentionally larger than any one mesher API.  This
module is the small, explicit bridge between that contract and the arguments
which the native wrappers really consume.  It never treats a visible schema
field as applied: callers add a field to ``applied`` only when they actually
put the projected value on the selected native route.
"""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass, field
from typing import Any

from core.native_option_capabilities import _KNOWN, canonical_engine


_OPTION_ALIASES = {
    "native_tet": ("native_tet", "tet"),
    "native_hex": ("native_hex", "hex"),
    "native_poly": ("native_poly", "poly"),
    "native_tri": ("native_tri", "tri"),
    "strict_quad": ("strict_quad",),
    "tri_quad": ("tri_quad",),
}


@dataclass
class NativeRuntimeProjection:
    """Resolved native arguments and truthful contract-application evidence."""

    engine: str
    runner_kwargs: dict[str, Any] = field(default_factory=dict)
    applied: dict[str, Any] = field(default_factory=dict)
    ignored: dict[str, Any] = field(default_factory=dict)
    pending: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    size_min: float | None = None
    size_max: float | None = None
    explicit_base_size: bool = False
    quality_limits: dict[str, tuple[str, float]] = field(default_factory=dict)
    quality_violations: list[dict[str, Any]] = field(default_factory=list)

    def mark_applied(self, pointer: str, value: Any) -> None:
        self.applied[pointer] = copy.deepcopy(value)


def _pointer(parts: list[str]) -> str:
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _finite_positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0.0 else None


def _selected_options(config: dict[str, Any], engine: str) -> tuple[str, dict[str, Any]]:
    options = config.get("engine_options", {})
    if not isinstance(options, dict):
        return "", {}
    selected_name = ""
    selected: dict[str, Any] = {}
    for name in _OPTION_ALIASES.get(engine, (engine,)):
        value = options.get(name)
        if isinstance(value, dict):
            # The canonical namespace wins when both legacy and canonical
            # aliases are present; the normalized contract keeps both intact.
            if not selected_name or name == engine:
                selected_name = name
            selected.update(copy.deepcopy(value))
    return selected_name, selected


def resolve_native_runtime(config: dict[str, Any] | None, engine: str) -> NativeRuntimeProjection:
    """Project only controls that have a concrete native-wrapper consumer.

    The full envelope still travels as ``input_config``.  Values with no
    consumer remain in the receipt as ``accepted_pending`` instead of being
    silently dropped or accidentally mapped to an unrelated knob.
    """

    selected_engine = canonical_engine(engine)
    projection = NativeRuntimeProjection(engine=selected_engine)
    if not isinstance(config, dict):
        return projection

    target = config.get("target", {})
    if isinstance(target, dict):
        count = target.get("count")
        if isinstance(count, int) and count > 0:
            projection.runner_kwargs["target_cells"] = count
            projection.mark_applied("/target/count", count)
        hard_max = target.get("hard_max_cells")
        if isinstance(hard_max, int) and hard_max > 0:
            projection.runner_kwargs["max_cells"] = hard_max
            projection.mark_applied("/target/hard_max_cells", hard_max)

    sizing = config.get("sizing", {})
    if isinstance(sizing, dict):
        base = _finite_positive(sizing.get("base_size"))
        if base is not None:
            projection.runner_kwargs["target_edge_length"] = base
            projection.explicit_base_size = True
            projection.mark_applied("/sizing/base_size", base)
        minimums = [
            ("min_size", sizing.get("min_size"), "/sizing/min_size"),
            ("curvature.min_size", (sizing.get("curvature") or {}).get("min_size") if isinstance(sizing.get("curvature"), dict) else None, "/sizing/curvature/min_size"),
            ("proximity.min_size", (sizing.get("proximity") or {}).get("min_size") if isinstance(sizing.get("proximity"), dict) else None, "/sizing/proximity/min_size"),
        ]
        for _name, value, pointer in minimums:
            number = _finite_positive(value)
            if number is not None:
                projection.size_min = max(projection.size_min or 0.0, number)
                projection.mark_applied(pointer, number)
        maximum = _finite_positive(sizing.get("max_size"))
        if maximum is not None:
            projection.size_max = maximum if projection.size_max is None else min(projection.size_max, maximum)
            projection.mark_applied("/sizing/max_size", maximum)

        optimization = config.get("optimization", {})
        if isinstance(optimization, dict):
            smooth = optimization.get("smoothing_iterations")
            if smooth is None:
                smooth = optimization.get("smoothing")
            try:
                smooth_i = int(smooth)
            except (TypeError, ValueError):
                smooth_i = -1
            if smooth_i >= 0:
                if selected_engine == "native_tet":
                    projection.runner_kwargs["smooth_iterations"] = smooth_i
                    projection.mark_applied("/optimization/smoothing_iterations", smooth_i)
                elif selected_engine == "native_hex":
                    projection.runner_kwargs["enable_post_smooth"] = smooth_i > 0
                    projection.runner_kwargs["post_smooth_iterations"] = smooth_i
                    projection.mark_applied("/optimization/smoothing_iterations", smooth_i)
                elif selected_engine == "native_poly":
                    projection.runner_kwargs["smooth_iters"] = smooth_i
                    projection.mark_applied("/optimization/smoothing_iterations", smooth_i)

    quality = config.get("quality", {})
    if isinstance(quality, dict):
        for key, metric in (
            ("max_skewness", "max_skewness"),
            ("max_non_orthogonality_deg", "max_non_orthogonality_deg"),
            ("max_core_aspect_ratio", "max_aspect_ratio"),
        ):
            limit = _finite_positive(quality.get(key))
            if limit is not None:
                projection.quality_limits[metric] = (
                    f"/quality/{key}",
                    limit,
                )

    engine_namespace, selected = _selected_options(config, selected_engine)
    known = _KNOWN.get(selected_engine, set())
    for key, value in selected.items():
        pointer = _pointer(["engine_options", engine_namespace or selected_engine, key])
        if key in known:
            projection.runner_kwargs[key] = copy.deepcopy(value)
            projection.mark_applied(pointer, value)
        else:
            projection.unsupported.append(pointer)

    # BL=0 is a real no-op.  Its spacing values must not leak into a layer
    # generator, but the layer count itself is consumed by the orchestrator.
    layers = config.get("boundary_layers", [])
    if isinstance(layers, list):
        for index, entry in enumerate(layers):
            if not isinstance(entry, dict):
                continue
            base_pointer = f"/boundary_layers/{index}"
            try:
                count = int(entry.get("layers", 0))
            except (TypeError, ValueError):
                count = 0
            if count == 0:
                projection.ignored[base_pointer] = "disabled_identity"

    # Record all remaining user fields as pending.  This is deliberately
    # computed from the normalized envelope, so a newly added UI field cannot
    # disappear from the application report without a test noticing it.
    def visit(value: Any, parts: list[str]) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"schema_version", "status", "actual_layers", "_compatibility"}:
                    continue
                visit(child, parts + [str(key)])
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, parts + [str(index)])
            return
        pointer = _pointer(parts)
        if pointer in projection.applied or pointer in projection.ignored or pointer in projection.unsupported:
            return
        projection.pending.append(pointer)

    visit(config, [])
    projection.pending = sorted(set(projection.pending))
    projection.unsupported = sorted(set(projection.unsupported))
    return projection


def contract_receipt(
    config: dict[str, Any] | None,
    projection: NativeRuntimeProjection,
    *,
    success: bool,
    result: Any,
) -> dict[str, Any]:
    """Build a post-run receipt for every explicit contract leaf."""

    records: list[dict[str, Any]] = []
    requested: dict[str, Any] = {}

    def collect(value: Any, parts: list[str]) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"schema_version", "status", "actual_layers", "_compatibility"}:
                    continue
                collect(child, parts + [str(key)])
        elif isinstance(value, list):
            for index, child in enumerate(value):
                collect(child, parts + [str(index)])
        else:
            requested[_pointer(parts)] = copy.deepcopy(value)

    if isinstance(config, dict):
        collect(config, [])
    applied = set(projection.applied)
    ignored = set(projection.ignored)
    unsupported = set(projection.unsupported)
    for pointer, value in sorted(requested.items()):
        if any(pointer == parent or pointer.startswith(parent + "/") for parent in ignored):
            status = "ignored_by_policy"
            effective = None
        elif pointer in unsupported:
            status = "unsupported"
            effective = None
        elif pointer in applied:
            status = "applied_verified" if success else "rejected"
            effective = copy.deepcopy(projection.applied[pointer]) if success else None
        else:
            status = "accepted_pending"
            effective = None
        records.append({
            "pointer": pointer,
            "requested": value,
            "effective": effective,
            "status": status,
            "kernel_receipt": {
                "result_success": bool(success),
                "result_type": type(result).__name__,
                "result_route": getattr(result, "route", None),
            },
        })
    return {
        "engine": projection.engine,
        "records": records,
        "applied_verified": [r["pointer"] for r in records if r["status"] == "applied_verified"],
        "accepted_pending": [r["pointer"] for r in records if r["status"] == "accepted_pending"],
        "ignored_by_policy": sorted(set(projection.ignored) | {
            r["pointer"] for r in records if r["status"] == "ignored_by_policy"
        }),
        "unsupported": [r["pointer"] for r in records if r["status"] == "unsupported"],
        "rejected": [r["pointer"] for r in records if r["status"] == "rejected"],
        "quality_gate": {
            "status": (
                "rejected" if projection.quality_violations
                else "pass" if any(
                    metric in projection.quality_limits
                    and any(
                        record["pointer"] == projection.quality_limits[metric][0]
                        and record["status"] == "applied_verified"
                        for record in records
                    )
                    for metric in projection.quality_limits
                )
                else "not_evaluated"
            ),
            "violations": copy.deepcopy(projection.quality_violations),
        },
        "effective_digest": __import__("hashlib").sha256(
            json.dumps({k: projection.applied[k] for k in sorted(applied)}, sort_keys=True, default=str).encode()
        ).hexdigest(),
    }


__all__ = ["NativeRuntimeProjection", "resolve_native_runtime", "contract_receipt"]
