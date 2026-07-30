"""Tier wrapper for native_poly 엔진.

harness (tet→poly dual + Evaluator) 기본, 실패 시 scipy Voronoi fallback.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from core.generator._tier_native_common import run_native_tier
from core.generator.native_poly import (
    generate_native_poly_voronoi,
    run_native_poly_harness,
)
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

log = get_logger(__name__)

TIER_NAME = "tier_native_poly"


def _runner(
    vertices,
    faces,
    case_dir,
    *,
    target_edge_length=None,
    seed_density=10,
    max_iter=3,
    n_lloyd=2,
    auto_escalate=True,
    auto_escalate_max=4,
    target_cells=None,
    max_cells=None,
    bl_layers=0,
    post_layers_num_layers=0,
    boolean_input_paths: Sequence[str] | None = None,
    boolean_union_input_paths: Sequence[str] | None = None,
    **_unused,
):
    """harness 우선, 실패 시 scipy Voronoi fallback.

    quality-specific 파라미터는 run_native_tier 가 HARNESS_PARAMS 에서 주입.

    beta2294: voronoi fallback 의 n_lloyd / auto_escalate / auto_escalate_max
    파라미터를 명시 forward (이전엔 **_unused 로 silently dropped).
    """
    _cell_budget = int(max_cells or target_cells or 0)
    _n_layers = int(post_layers_num_layers or bl_layers or 0)
    if _cell_budget > 0 and _n_layers > 0:
        log.info(
            "native_poly_budget_prefers_hex_base",
            target_cells=int(target_cells or 0),
            max_cells=int(max_cells or 0),
            bl_layers=int(_n_layers),
        )
        return generate_native_poly_voronoi(
            vertices,
            faces,
            case_dir,
            target_edge_length=target_edge_length,
            seed_density=int(seed_density),
            n_lloyd=int(n_lloyd),
            auto_escalate=bool(auto_escalate),
            auto_escalate_max=int(auto_escalate_max),
            target_cells=target_cells,
            max_cells=max_cells,
            bl_layers=int(_n_layers),
            prefer_hex_for_budget=True,
        )

    boundary_face_classifier = None
    ordered_source_paths = boolean_input_paths or boolean_union_input_paths
    if ordered_source_paths and len(ordered_source_paths) >= 2:
        try:
            from core.utils.boundary_provenance import (  # noqa: PLC0415
                SourceSurfacePatchClassifier,
            )

            boundary_face_classifier = SourceSurfacePatchClassifier(list(ordered_source_paths))
        except Exception as exc:
            log.warning(
                "native_poly_boundary_provenance_classifier_unavailable",
                error=str(exc)[:160],
            )

    hres = run_native_poly_harness(
        vertices,
        faces,
        case_dir,
        target_edge_length=target_edge_length,
        target_cells=target_cells,
        seed_density=int(seed_density),
        max_iter=int(max_iter),
        boundary_face_classifier=boundary_face_classifier,
    )
    if hres.success:
        return hres
    if hres.message.startswith((
        "target_primal_vertex_floor_unmet:",
        "target_poly_budget_unreachable:",
    )):
        log.warning(
            "native_poly_target_contract_refused",
            message=hres.message,
        )
        return hres
    log.warning(
        "native_poly_harness_fail_falling_back_to_voronoi",
        message=hres.message,
    )
    return generate_native_poly_voronoi(
        vertices,
        faces,
        case_dir,
        target_edge_length=target_edge_length,
        seed_density=int(seed_density),
        n_lloyd=int(n_lloyd),
        auto_escalate=bool(auto_escalate),
        auto_escalate_max=int(auto_escalate_max),
        target_cells=target_cells,
        max_cells=max_cells,
        bl_layers=int(_n_layers),
    )


class TierNativePolyGenerator:
    """AutoTessell 자체 polyhedral 엔진."""

    TIER_NAME = TIER_NAME

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        return run_native_tier(
            _runner,
            self.TIER_NAME,
            strategy,
            preprocessed_path,
            case_dir,
        )
