"""Tier wrapper for native_hex MVP 엔진."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from core.generator._tier_native_common import run_native_tier
from core.generator.native_hex import NativeHexResult, generate_native_hex
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

log = get_logger(__name__)

TIER_NAME = "tier_native_hex"


def _runner(
    vertices: NDArray[np.float64],
    faces: NDArray[np.int64],
    case_dir: Path,
    *,
    target_edge_length: float | None = None,
    seed_density: int = 16,
    **kwargs: Any,
) -> NativeHexResult:
    """Run the native uniform-grid engine and label its actual route.

    ``native_hex`` has no harness or alternate fallback in this tier.  Keep the
    call transparent so every quality-aware parameter injected by
    :func:`run_native_tier` reaches ``generate_native_hex`` unchanged.
    """
    forwarded_seed_density = int(seed_density)
    result = generate_native_hex(
        vertices,
        faces,
        case_dir,
        target_edge_length=target_edge_length,
        seed_density=forwarded_seed_density,
        **kwargs,
    )
    setattr(result, "route", "hex_uniform_grid")
    setattr(result, "contract", "native_hex")
    setattr(result, "contract_details", {"seed_density": forwarded_seed_density})
    return result


class TierNativeHexGenerator:
    """AutoTessell 자체 hex-dominant 엔진 (uniform grid + inside filter)."""

    TIER_NAME = TIER_NAME

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        # seed_density 는 HARNESS_PARAMS 에서 quality-aware 로 주입 — caller
        # override 필요 시 extra_kwargs 전달.
        return run_native_tier(
            _runner,
            self.TIER_NAME,
            strategy,
            preprocessed_path,
            case_dir,
        )
