"""Tier 0: auto_tessell_core (geogram + CDT) 메쉬 생성기."""

from __future__ import annotations

import time
from pathlib import Path

from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier0_core"


class Tier0CoreGenerator:
    """geogram + CDT 기반 자체 테트라헤드럴 메쉬 생성기.

    auto_tessell_core C++ 확장 모듈을 사용한다.
    모듈이 빌드되지 않은 경우 ImportError로 graceful fail 처리한다.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        """Tier 0 메쉬 생성을 실행한다.

        Args:
            strategy: Strategist가 생성한 메쉬 전략.
            preprocessed_path: 전처리된 STL 또는 CAD 파일 경로.
            case_dir: OpenFOAM 케이스 디렉터리 경로.

        Returns:
            실행 결과를 담은 TierAttempt. 실패 시 status="failed".
        """
        t_start = time.monotonic()
        logger.info("tier0_core_start", preprocessed_path=str(preprocessed_path))

        # auto_tessell_core 모듈 import 시도
        try:
            import auto_tessell_core as atc  # noqa: F401
        except ImportError as exc:
            elapsed = time.monotonic() - t_start
            logger.warning(
                "tier0_core_import_failed",
                error=str(exc),
                hint="auto_tessell_core C++ 확장 미빌드. 'pip install -e .' 또는 cmake 빌드 필요.",
            )
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=(
                    f"auto_tessell_core 모듈 import 실패: {exc}. "
                    "C++ 확장을 빌드하거나 다른 Tier를 사용하세요."
                ),
            )

        # STL 파일 존재 확인
        if not preprocessed_path.exists():
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"전처리 파일을 찾을 수 없습니다: {preprocessed_path}",
            )

        # 메쉬 생성 실행
        try:
            quality = strategy.tier_specific_params.get("core_quality", 2.0)
            max_vertices = strategy.tier_specific_params.get("core_max_vertices", None)

            logger.info(
                "tier0_core_tetrahedralize",
                quality=quality,
                max_vertices=max_vertices,
            )

            result = atc.tetrahedralize_stl(  # type: ignore[name-defined]
                input_path=str(preprocessed_path),
                quality=quality,
                max_vertices=max_vertices,
            )
            result.write_openfoam(str(case_dir))

            elapsed = time.monotonic() - t_start
            logger.info("tier0_core_success", elapsed=elapsed)

            return TierAttempt(
                tier=TIER_NAME,
                status="success",
                time_seconds=elapsed,
            )

        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier0_core_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"Tier 0 실행 실패: {exc}",
            )
