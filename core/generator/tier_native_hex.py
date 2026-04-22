"""Tier wrapper for native_hex MVP 엔진."""
from __future__ import annotations

from pathlib import Path

from core.generator._tier_native_common import run_native_tier
from core.generator.native_hex import generate_native_hex
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

log = get_logger(__name__)

TIER_NAME = "tier_native_hex"


class TierNativeHexGenerator:
    """AutoTessell 자체 hex-dominant 엔진 (uniform grid + inside filter)."""

    TIER_NAME = TIER_NAME

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        return run_native_tier(
            generate_native_hex, self.TIER_NAME,
            strategy, preprocessed_path, case_dir,
            extra_kwargs={"seed_density": 16},
        )
