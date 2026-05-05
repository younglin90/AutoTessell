"""Sandia MeshKit tier — placeholder wrapper.

MeshKit 는 C++ 라이브러리이고 Python binding 이 제한적이라 AutoTessell 에
직접 통합하기 복잡하다. 설치 감지 후 가능한 경로로 메쉬 생성을 시도한다.

설치:
  - MOAB + CGM + Lasso + iGeom 선행 (source build 수 시간)
  - ``pip install pymoab`` 으로 MOAB Python 바인딩만 설치 가능
  - MeshKit 자체는 C++ 헤더만 제공 — executable CLI 도 제한적

현재 로직:
  1. ``pymoab`` 설치 확인 → 없으면 친절한 에러
  2. 있어도 MeshKit C++ 모듈(AF2D/AF3D/EBMesh) Python 미노출이라 구현 불가
     → 설치 가이드 메시지 반환
"""
from __future__ import annotations

import time
from pathlib import Path

from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

log = get_logger(__name__)

TIER_NAME = "tier_meshkit"


class TierMeshKitGenerator:
    """MeshKit 볼륨 메쉬 생성기 (placeholder)."""

    TIER_NAME = TIER_NAME

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        t_start = time.monotonic()
        log.info("tier_meshkit_start", case_dir=str(case_dir))
        try:
            import pymoab  # type: ignore
            _ = pymoab
            moab_ok = True
        except ImportError:
            moab_ok = False

        msg = (
            "Sandia MeshKit 는 C++ 라이브러리로 Python wrapper 가 제한적이라 "
            "AutoTessell 파이프라인 통합이 미완성입니다.\n"
            "\n"
            "설치 가이드:\n"
            "  1) pymoab (MOAB Python 바인딩) — `pip install pymoab` 또는\n"
            "     source: https://bitbucket.org/fathomteam/moab\n"
            "  2) MeshKit (C++ only) — https://bitbucket.org/fathomteam/meshkit\n"
            "     cmake build 수 시간 + 의존성 (MOAB / CGM / Lasso / iGeom)\n"
            "  3) MeshKit 의 AF2D/AF3D/EBMesh 알고리즘은 C++ API만 노출 —\n"
            "     Python 래퍼가 존재하지 않아 직접 통합 어려움.\n"
            "\n"
            f"현재 상태: pymoab={'설치됨' if moab_ok else '미설치'}"
        )
        log.warning("tier_meshkit_not_integrated")
        elapsed = time.monotonic() - t_start
        return TierAttempt(
            tier=self.TIER_NAME, status="failed",
            time_seconds=elapsed, error_message=msg,
        )
