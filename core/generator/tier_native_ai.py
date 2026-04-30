"""Tier wrapper: native_ai MVP — AI-assisted volume mesh.

현재 (skeleton, beta2552): mesh_type 별 기존 native_* engine 으로 위임.
향후 AI-V1~V4 카드 추가 시 ML 통합.
"""
from __future__ import annotations

from pathlib import Path

from core.generator._tier_native_common import run_native_tier
from core.generator.native_ai import (
    AIVolumeConfig,
    generate_native_ai_volume,
)
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

log = get_logger(__name__)

TIER_NAME = "tier_native_ai"


def _runner(vertices, faces, case_dir, *, target_edge_length=None,
            seed_density=8, mesh_type="tet", quality_level="standard",
            **kwargs):
    """native_ai dispatch — mesh_type 에 따라 tet/hex/poly 위임."""
    cfg = AIVolumeConfig(
        mesh_type=mesh_type,
        quality_level=quality_level,
        seed_density=int(seed_density),
        enable_bl=bool(kwargs.get("enable_bl", True)),
        bl_num_layers=int(kwargs.get("bl_num_layers", 3)),
        bl_first_thickness=float(kwargs.get("bl_first_thickness", 0.0)),
        ai_smoothing=bool(kwargs.get("ai_smoothing", False)),
        ai_surface_repair=bool(kwargs.get("ai_surface_repair", False)),
        ai_collision_predict=bool(kwargs.get("ai_collision_predict", False)),
    )
    return generate_native_ai_volume(vertices, faces, Path(case_dir), cfg)


class TierNativeAIGenerator:
    """AutoTessell 자체 AI volume mesh 엔진 (현재 skeleton — 기존 native_* 위임)."""

    TIER_NAME = TIER_NAME

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        # mesh_type 은 strategy 에서 추출.
        mesh_type = getattr(strategy, "mesh_type", "tet")
        if mesh_type not in ("tet", "hex", "poly"):
            mesh_type = "tet"
        return run_native_tier(
            _runner, self.TIER_NAME,
            strategy, preprocessed_path, case_dir,
            mesh_type=mesh_type,
        )
