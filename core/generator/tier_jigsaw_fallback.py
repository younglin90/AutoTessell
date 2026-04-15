"""Tier JIGSAW Fallback: tier_jigsaw의 coarse 모드 래퍼.

jigsaw와 jigsaw_fallback의 차이는 hmax_scale 파라미터뿐이다.
이 클래스는 하위 호환성을 위해 유지되며 내부적으로 TierJigsawGenerator에 위임한다.
"""

from __future__ import annotations

from pathlib import Path

from core.generator.tier_jigsaw import TierJigsawGenerator
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier_jigsaw_fallback"


class TierJigsawFallbackGenerator(TierJigsawGenerator):
    """tier_jigsaw의 fallback 래퍼 (하위 호환성 유지).

    tier_jigsaw와 동일하게 jigsaw_hmax_scale=1.0을 기본값으로 주입한다.
    과거에는 2.0(coarse)을 사용했으나 단순 형상에서 찌그러진 셀이 발생해 1.0으로 변경.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        # hmax_scale=1.0: jigsaw_fallback은 이제 jigsaw와 동일한 해상도 사용
        # (과거 2.0은 단순 형상에서 찌그러진 셀을 유발했음)
        params = dict(strategy.tier_specific_params)
        params.setdefault("jigsaw_hmax_scale", 1.0)
        strategy = strategy.model_copy(update={"tier_specific_params": params})
        result = super().run(strategy, preprocessed_path, case_dir)
        # tier 이름을 fallback으로 교정해 로그 일관성 유지
        if result.tier == "tier_jigsaw":
            result = result.model_copy(update={"tier": TIER_NAME})
        return result
