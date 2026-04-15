"""Tier 0: auto_tessell_core / tessell_mesh (geogram + CDT) 메쉬 생성기."""

from __future__ import annotations

import time
from pathlib import Path

from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier0_core"


class Tier0CoreGenerator:
    """geogram + CDT 기반 자체 테트라헤드럴 메쉬 생성기.

    auto_tessell_core 또는 tessell_mesh C++ 확장 모듈을 사용한다.
    모듈이 빌드되지 않은 경우 ImportError로 graceful fail 처리한다.
    """

    @staticmethod
    def _import_core_module():
        """Tier0 C++ 확장 모듈을 import한다."""
        def _check_module(atc, name):
            """모듈에 tetrahedralize_stl 메서드가 있는지 확인한다."""
            if not hasattr(atc, "tetrahedralize_stl"):
                raise ImportError(
                    f"{name} 모듈에 tetrahedralize_stl이 없습니다 "
                    f"(available: {[a for a in dir(atc) if not a.startswith('_')]}). "
                    "C++ 확장을 다시 빌드하세요."
                )
            return atc, name

        try:
            import auto_tessell_core as atc  # type: ignore[import-not-found]
            return _check_module(atc, "auto_tessell_core")
        except ImportError as exc_auto:
            try:
                import tessell_mesh as atc  # type: ignore[import-not-found]
                return _check_module(atc, "tessell_mesh")
            except ImportError as exc_tessell:
                try:
                    from backend.mesh import tessell_mesh as atc  # type: ignore[import-not-found]
                    return _check_module(atc, "backend.mesh.tessell_mesh")
                except ImportError as exc_backend:
                    raise ImportError(
                        "auto_tessell_core/tessell_mesh 모듈 import 실패. "
                        "C++ 확장을 빌드하거나 다른 Tier를 사용하세요. "
                        f"auto_tessell_core={exc_auto}; "
                        f"tessell_mesh={exc_tessell}; "
                        f"backend.mesh.tessell_mesh={exc_backend}"
                    ) from exc_backend

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

        # Tier0 C++ 모듈 import 시도 (auto_tessell_core -> tessell_mesh)
        try:
            atc, module_name = self._import_core_module()
        except ImportError as exc:
            elapsed = time.monotonic() - t_start
            logger.warning(
                "tier0_core_import_failed",
                error=str(exc),
                hint="Tier0 C++ 확장 미빌드. 'cd tessell-mesh && ./build.sh' 후 재시도.",
            )
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=(
                    f"Tier0 모듈 import 실패: {exc}. "
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
                module=module_name,
                quality=quality,
                max_vertices=max_vertices,
            )

            tetra = atc.tetrahedralize_stl

            # 바인딩마다 시그니처가 달라서 호출 패턴을 순차 시도한다.
            call_errors: list[str] = []
            result = None

            # 1) pybind tessell_mesh 형태: tetrahedralize_stl(stl_path, quality=...)
            try:
                result = tetra(str(preprocessed_path), quality=quality)
                if max_vertices is not None:
                    logger.debug(
                        "tier0_core_param_ignored",
                        param="max_vertices",
                        module=module_name,
                        reason="binding_not_supported",
                    )
            except TypeError as exc:
                call_errors.append(f"pattern1={exc}")

            # 2) auto_tessell_core 형태: tetrahedralize_stl(input_path=..., quality=..., max_vertices=...)
            if result is None:
                try:
                    result = tetra(
                        input_path=str(preprocessed_path),
                        quality=quality,
                        max_vertices=max_vertices,
                    )
                except TypeError as exc:
                    call_errors.append(f"pattern2={exc}")

            if result is None:
                raise RuntimeError("tetrahedralize_stl 호출 실패: " + " | ".join(call_errors))

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
