"""Tier wrapper: native_tet MVP 엔진 + harness (Gen↔Eval)."""
from __future__ import annotations

from pathlib import Path

from core.generator._tier_native_common import run_native_tier
from core.generator.native_tet import (
    generate_native_tet,
    run_native_tet_harness,
)
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

log = get_logger(__name__)

TIER_NAME = "tier_native_tet"


def _runner(vertices, faces, case_dir, *, target_edge_length=None,
            seed_density=12, max_iter=2, **kwargs):
    """harness 우선, 완전 실패 시 기본 generate_native_tet 로 fallback.

    quality-specific 파라미터 (seed_density / max_iter) 는 run_native_tier 가
    HARNESS_PARAMS 테이블에서 주입. 직접 호출 시의 기본값은 standard 와 동일.

    beta2295: TetWild-lite Phase B/C / AMIPS / chunked / CDT / target_cells
    knobs 를 **kwargs 로 forward (이전엔 **_unused 가 silently drop).
    harness 는 이미 (beta310 부터) **kwargs 를 mesher 에 전달하도록 wired.

    The orchestrator forwards pipeline-level kwargs that aren't part
    of the volume-mesher API (``bl_layers``, ``post_layers_*``,
    ``checker_engine``, ``cad_engine``, etc).  Strip them here so
    they don't leak into ``generate_native_tet`` and trigger
    "unexpected keyword argument" failures (BLR-9c-d-r-1 fix).
    """
    _PIPELINE_ONLY_KEYS = {
        "bl_layers", "post_layers_engine", "post_layers_num_layers",
        "checker_engine", "cad_engine", "remesh_engine",
        "repair_engine", "postprocess_engine",
    }
    forward_kwargs = {
        k: v for k, v in kwargs.items()
        if k not in _PIPELINE_ONLY_KEYS
    }
    hres = run_native_tet_harness(
        vertices, faces, case_dir,
        target_edge_length=target_edge_length,
        seed_density=int(seed_density), max_iter=int(max_iter),
        **forward_kwargs,
    )
    if hres.success or hres.n_cells > 0:
        return hres
    # 완전 실패 → 기본 경로로 한 번 더
    return generate_native_tet(
        vertices, faces, case_dir,
        target_edge_length=target_edge_length,
        seed_density=int(seed_density),
        **forward_kwargs,
    )


class TierNativeTetGenerator:
    """AutoTessell 자체 tet 엔진 (scipy Delaunay + envelope check)."""

    TIER_NAME = TIER_NAME

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        return run_native_tier(
            _runner, self.TIER_NAME,
            strategy, preprocessed_path, case_dir,
        )
