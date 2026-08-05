"""Default-off orchestration from v2 CAD witness to the C++ shared-front stack."""

from __future__ import annotations

from typing import Any, Mapping

from core.utils.native_extensions import import_native_extension


def plan_brep_shared_surface_wall_edge_front(
    evidence: Mapping[str, Any],
    *,
    requested_layers: int,
    candidates: list[Mapping[str, Any]],
    raw_planner_kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    """Run C++ witness preflight before the existing C++ quality stack."""

    witness_kernel = import_native_extension("native_brep_front_evidence_v2")
    front_kernel = import_native_extension("native_surface_bl_front_shared")

    witness_plan = witness_kernel.plan_brep_shared_surface_wall_edge_front(
        dict(evidence), requested_layers, list(candidates)
    )
    if not witness_plan.get("accepted"):
        return witness_plan
    if requested_layers == 0:
        return witness_plan
    raw_plan = front_kernel.plan_shared_surface_wall_edge_front(
        **dict(raw_planner_kwargs)
    )
    if raw_plan.get("accepted") is not True or raw_plan.get("status") != "candidate_plan_ready":
        return {
            "accepted": False,
            "status": "refused_brep_shared_front",
            "reason": "quality_stack_rollback",
            "requested_layers": requested_layers,
            "actual_layers": 0,
            "generated_vertices": [],
            "generated_faces": [],
            "provenance": [],
            "source_immutable": True,
            "atomic_rollback": True,
            "witness": witness_plan,
            "quality_stack": raw_plan,
            "runtime_route": "default_off",
        }
    result = dict(raw_plan)
    result["brep_witness_transaction"] = witness_plan
    result["runtime_route"] = "default_off_brep_diagnostic"
    result["source_immutable"] = True
    result["atomic_rollback"] = True
    return result
