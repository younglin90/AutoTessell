"""Generator 5-Tier 파이프라인 오케스트레이터."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from core.generator.tier0_2d_meshpy import Tier2DMeshPyGenerator
from core.generator.tier0_core import Tier0CoreGenerator
from core.generator.tier05_netgen import Tier05NetgenGenerator
from core.generator.tier1_snappy import Tier1SnappyGenerator
from core.generator.tier2_tetwild import Tier2TetWildGenerator
from core.generator.tier15_cfmesh import Tier15CfMeshGenerator
from core.generator.tier_classy_blocks import TierClassyBlocksGenerator
from core.generator.tier_hex_classy_blocks import TierHexClassyBlocksGenerator
from core.generator.tier_jigsaw import TierJigsawGenerator
from core.generator.tier_jigsaw_fallback import TierJigsawFallbackGenerator
from core.generator.tier_meshpy import TierMeshPyGenerator
from core.generator.tier_wildmesh import TierWildMeshGenerator
from core.generator.polyhedral import PolyhedralGenerator
from core.generator.tier_gmsh_hex import TierGmshHexGenerator
from core.generator.tier_cinolib_hex import TierCinolibHexGenerator
from core.generator.tier_voro_poly import TierVoroPolyGenerator
from core.generator.tier_hohqmesh import TierHOHQMeshGenerator
from core.generator.tier_mmg3d import TierMMG3DGenerator
from core.generator.tier_robust_hex import TierRobustHexGenerator
from core.generator.tier_algohex import TierAlgoHexGenerator
from core.schemas import ExecutionSummary, GeneratorLog, MeshStrategy, TierAttempt
from core.utils.logging import get_logger
from core.utils.openfoam_utils import get_openfoam_label_size

logger = get_logger(__name__)

# Tier 이름 → 클래스 매핑
_TIER_REGISTRY: dict[str, type] = {
    "tier0_2d_meshpy": Tier2DMeshPyGenerator,
    "tier0_core": Tier0CoreGenerator,
    "tier05_netgen": Tier05NetgenGenerator,
    "tier1_snappy": Tier1SnappyGenerator,
    "tier15_cfmesh": Tier15CfMeshGenerator,
    "tier2_tetwild": Tier2TetWildGenerator,
    "tier_meshpy": TierMeshPyGenerator,
    "tier_hex_classy_blocks": TierHexClassyBlocksGenerator,
    "tier_polyhedral": PolyhedralGenerator,
    "tier_classy_blocks": TierClassyBlocksGenerator,
    "tier_jigsaw": TierJigsawGenerator,
    "tier_jigsaw_fallback": TierJigsawFallbackGenerator,
    "tier_wildmesh": TierWildMeshGenerator,
    "tier_gmsh_hex": TierGmshHexGenerator,
    "tier_cinolib_hex": TierCinolibHexGenerator,
    "tier_voro_poly": TierVoroPolyGenerator,
    "tier_hohqmesh": TierHOHQMeshGenerator,
    "tier_mmg3d": TierMMG3DGenerator,
    "tier_robust_hex": TierRobustHexGenerator,
    "tier_algohex": TierAlgoHexGenerator,
}

# CLI --tier 별칭 → 정규 Tier 이름
_TIER_ALIASES: dict[str, str] = {
    "2d": "tier0_2d_meshpy",
    "hex": "tier_hex_classy_blocks",
    "polyhedral": "tier_polyhedral",
    "core": "tier0_core",
    "netgen": "tier05_netgen",
    "snappy": "tier1_snappy",
    "cfmesh": "tier15_cfmesh",
    "tetwild": "tier2_tetwild",
    "meshpy": "tier_meshpy",
    "classy_blocks": "tier_classy_blocks",
    "jigsaw": "tier_jigsaw",
    "jigsaw_fallback": "tier_jigsaw_fallback",
    "wildmesh": "tier_wildmesh",
    "gmsh_hex": "tier_gmsh_hex",
    "cinolib_hex": "tier_cinolib_hex",
    # 정규 이름 자체도 허용
    "tier0_2d_meshpy": "tier0_2d_meshpy",
    "tier0_core": "tier0_core",
    "tier05_netgen": "tier05_netgen",
    "tier1_snappy": "tier1_snappy",
    "tier15_cfmesh": "tier15_cfmesh",
    "tier2_tetwild": "tier2_tetwild",
    "tier_meshpy": "tier_meshpy",
    "tier_hex_classy_blocks": "tier_hex_classy_blocks",
    "tier_polyhedral": "tier_polyhedral",
    "tier_classy_blocks": "tier_classy_blocks",
    "tier_jigsaw": "tier_jigsaw",
    "tier_jigsaw_fallback": "tier_jigsaw_fallback",
    "tier_wildmesh": "tier_wildmesh",
    "tier_gmsh_hex": "tier_gmsh_hex",
    "tier_cinolib_hex": "tier_cinolib_hex",
    "voro_poly": "tier_voro_poly",
    "voro": "tier_voro_poly",
    "hohqmesh": "tier_hohqmesh",
    "hohq": "tier_hohqmesh",
    "tier_voro_poly": "tier_voro_poly",
    "tier_hohqmesh": "tier_hohqmesh",
    "mmg3d": "tier_mmg3d",
    "mmg": "tier_mmg3d",
    "tier_mmg3d": "tier_mmg3d",
    "robust_hex": "tier_robust_hex",
    "robust_hex_mesh": "tier_robust_hex",
    "tier_robust_hex": "tier_robust_hex",
    "algohex": "tier_algohex",
    "algo_hex": "tier_algohex",
    "tier_algohex": "tier_algohex",
}


def _resolve_tier(tier_name: str) -> str:
    """Tier 이름 또는 별칭을 정규 이름으로 변환한다."""
    resolved = _TIER_ALIASES.get(tier_name, tier_name)
    if resolved not in _TIER_REGISTRY:
        logger.warning("unknown_tier", tier=tier_name, fallback=resolved)
    return resolved


def _clean_work_dir(case_dir: Path) -> None:
    """케이스 디렉터리 내 생성 파일을 정리한다.

    다음 항목을 삭제한다:
    - constant/polyMesh/ (메쉬 출력)
    - constant/triSurface/ (복사된 STL)
    - system/ (Dict 파일들)
    - 시간 디렉터리 (0/, 0.orig/ 등 숫자로 시작하는 것들)
    - 임시 메쉬 파일 (*.msh, *.mesh)
    """
    patterns_to_remove = [
        case_dir / "constant" / "polyMesh",
        case_dir / "constant" / "triSurface",
        case_dir / "system",
    ]

    for path in patterns_to_remove:
        if path.exists():
            shutil.rmtree(str(path))
            logger.debug("cleaned_dir", path=str(path))

    # 시간 디렉터리 정리
    if case_dir.exists():
        for child in case_dir.iterdir():
            if child.is_dir() and child.name.replace(".", "", 1).isdigit():
                shutil.rmtree(str(child))
                logger.debug("cleaned_time_dir", path=str(child))

        # 임시 메쉬 파일 정리
        for pattern in ["*.msh", "*.mesh"]:
            for f in case_dir.glob(pattern):
                f.unlink()
                logger.debug("cleaned_file", path=str(f))

    logger.info("work_dir_cleaned", case_dir=str(case_dir))


def _run_tier(
    tier_name: str,
    strategy: MeshStrategy,
    preprocessed_path: Path,
    case_dir: Path,
) -> TierAttempt:
    """지정된 Tier를 실행한다.

    Args:
        tier_name: 정규 Tier 이름.
        strategy: 메쉬 전략.
        preprocessed_path: 전처리된 파일 경로.
        case_dir: 케이스 디렉터리.

    Returns:
        TierAttempt 결과.
    """
    generator_class = _TIER_REGISTRY.get(tier_name)

    if generator_class is None:
        logger.error("unknown_tier_in_registry", tier=tier_name)
        return TierAttempt(
            tier=tier_name,
            status="failed",
            time_seconds=0.0,
            error_message=f"알 수 없는 Tier: '{tier_name}'. "
                         f"유효한 Tier: {list(_TIER_REGISTRY.keys())}",
        )

    logger.info("running_tier", tier=tier_name)
    generator = generator_class()

    result: TierAttempt = generator.run(
        strategy=strategy,
        preprocessed_path=preprocessed_path,
        case_dir=case_dir,
    )
    return result


class MeshGenerator:
    """5-Tier 메쉬 생성 파이프라인 오케스트레이터.

    selected_tier로 시작하여 실패 시 fallback_tiers 순서로 시도한다.
    모든 Tier가 실패해도 GeneratorLog를 반환하며 전체 프로세스를 중단하지 않는다.
    """

    def _get_tier_order(self, strategy: MeshStrategy) -> list[str]:
        """quality_level에 따라 Tier 실행 순서를 반환한다.

        strategy.selected_tier가 "auto"가 아닌 명시적 Tier인 경우에는
        selected_tier + fallback_tiers 순서를 그대로 사용한다.
        "auto"인 경우에는 quality_level 기반 기본 순서를 사용한다.

        Args:
            strategy: 메쉬 전략.

        Returns:
            정규화된 Tier 이름 목록 (중복 없이 순서대로).
        """
        quality_level = getattr(strategy, "quality_level", "standard")
        # QualityLevel enum이면 .value를 사용, 문자열이면 그대로
        if hasattr(quality_level, "value"):
            quality_level = quality_level.value

        # selected_tier가 명시적으로 지정된 경우 (auto 아님) → 해당 Tier만 실행, fallback 없음
        auto_mode = strategy.selected_tier.lower() in ("auto", "")
        if not auto_mode:
            return [_resolve_tier(strategy.selected_tier)]

        # Auto 모드: quality_level 기반 기본 순서
        if quality_level == "draft":
            # 속도 우선: TetWild coarse → JIGSAW fallback → Netgen
            tier_names = ["tier2_tetwild", "tier_jigsaw", "tier05_netgen"]
        elif quality_level == "fine":
            # 품질 우선: classy_blocks(구조 Hex) → cfMesh → snappy(BL) → Netgen → TetWild
            # 단, OpenFOAM label=32 환경에서는 snappy를 뒤로 미뤄 대형 셀 한계를 완화한다.
            label_bits = get_openfoam_label_size()
            if label_bits >= 64:
                tier_names = [
                    "tier_classy_blocks",
                    "tier15_cfmesh",
                    "tier1_snappy",
                    "tier05_netgen",
                    "tier2_tetwild",
                ]
            else:
                logger.warning(
                    "fine_tier_order_demoted_snappy_for_int32",
                    label_bits=label_bits,
                )
                tier_names = [
                    "tier_classy_blocks",
                    "tier15_cfmesh",
                    "tier05_netgen",
                    "tier2_tetwild",
                    "tier1_snappy",
                ]
        else:  # standard
            # 균형: Netgen → MeshPy TetGen fallback → cfMesh → TetWild
            tier_names = ["tier05_netgen", "tier_meshpy", "tier15_cfmesh", "tier2_tetwild"]

        return tier_names

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> GeneratorLog:
        """메쉬 생성 파이프라인을 실행한다.

        Args:
            strategy: Strategist가 생성한 메쉬 전략.
                - selected_tier: 먼저 시도할 Tier. "auto"이면 quality_level 기반 순서.
                - fallback_tiers: selected_tier 실패 시 순서대로 시도.
                - quality_level: Draft/Standard/Fine 품질 레벨.
            preprocessed_path: 전처리된 STL 또는 CAD 파일 경로.
            case_dir: OpenFOAM 케이스 디렉터리 경로.

        Returns:
            GeneratorLog: 모든 Tier 시도 이력을 담은 로그.
                모든 Tier 실패 시에도 반환 (status="failed").
        """
        t_pipeline_start = time.monotonic()

        case_dir.mkdir(parents=True, exist_ok=True)

        # quality_level 추출
        quality_level = getattr(strategy, "quality_level", "standard")
        if hasattr(quality_level, "value"):
            quality_level = quality_level.value

        # Tier 실행 순서 결정
        tier_sequence = self._get_tier_order(strategy)

        # 중복 제거 (순서 유지)
        seen: set[str] = set()
        unique_tiers: list[str] = []
        for t in tier_sequence:
            if t not in seen:
                seen.add(t)
                unique_tiers.append(t)

        logger.info(
            "pipeline_start",
            quality_level=quality_level,
            selected_tier=strategy.selected_tier,
            fallback_tiers=strategy.fallback_tiers,
            tier_sequence=unique_tiers,
            case_dir=str(case_dir),
        )

        tiers_attempted: list[TierAttempt] = []
        successful_tier: str | None = None

        for i, tier_name in enumerate(unique_tiers):
            is_fallback = i > 0
            logger.info(
                "tier_attempt",
                tier=tier_name,
                attempt_number=i + 1,
                is_fallback=is_fallback,
                total_tiers=len(unique_tiers),
            )

            # Tier 시도 전 work_dir 초기화 (첫 번째 Tier 포함)
            _clean_work_dir(case_dir)

            # Tier 실행
            attempt = _run_tier(tier_name, strategy, preprocessed_path, case_dir)
            tiers_attempted.append(attempt)

            if attempt.status == "success":
                successful_tier = tier_name
                logger.info(
                    "tier_succeeded",
                    tier=tier_name,
                    elapsed=attempt.time_seconds,
                )
                break
            else:
                next_t = unique_tiers[i + 1] if i + 1 < len(unique_tiers) else "none"
                if next_t == "none":
                    logger.warning(
                        "tier_failed_no_fallback",
                        tier=tier_name,
                        error=attempt.error_message,
                    )
                else:
                    logger.warning(
                        "tier_failed_trying_fallback",
                        tier=tier_name,
                        error=attempt.error_message,
                        next_tier=next_t,
                    )

        total_elapsed = time.monotonic() - t_pipeline_start
        poly_mesh_dir = case_dir / "constant" / "polyMesh"
        output_dir = str(poly_mesh_dir)

        if successful_tier is None:
            logger.error(
                "all_tiers_failed",
                tiers_attempted=[a.tier for a in tiers_attempted],
                total_elapsed=total_elapsed,
            )
        else:
            logger.info(
                "pipeline_complete",
                successful_tier=successful_tier,
                total_elapsed=total_elapsed,
                output_dir=output_dir,
            )

        return GeneratorLog(
            execution_summary=ExecutionSummary(
                selected_tier=strategy.selected_tier,
                tiers_attempted=tiers_attempted,
                output_dir=output_dir,
                total_time_seconds=total_elapsed,
                quality_level=quality_level,
            )
        )
