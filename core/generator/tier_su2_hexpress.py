"""SU2 HexPress tier — placeholder wrapper.

HexPress 는 SU2 suite 의 내부 hex-dominant mesher. SU2 자체가 PyPI 에 없고
source build 필요 (meson / ninja). HexPress 모듈은 ``tools/hex_mesher`` 내부에
있어서 standalone CLI 도 아니다.

설치:
  git clone https://github.com/su2code/SU2
  ./meson.py build && ninja -C build install

직접 통합 대신 ``SU2_CFD`` binary 및 Python API (pysu2) 유무를 감지 후
친절한 메시지로 처리한다.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

log = get_logger(__name__)

TIER_NAME = "tier_su2_hexpress"


class TierSU2HexpressGenerator:
    """SU2 HexPress 볼륨 메쉬 생성기 (placeholder)."""

    TIER_NAME = TIER_NAME

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        t_start = time.monotonic()
        log.info("tier_su2_hexpress_start", case_dir=str(case_dir))

        su2_found = shutil.which("SU2_CFD") is not None
        try:
            import pysu2  # type: ignore
            _ = pysu2
            pysu2_found = True
        except ImportError:
            pysu2_found = False

        msg = (
            "SU2 HexPress 는 SU2 suite 내부 도구(tools/hex_mesher)로 "
            "standalone CLI 가 아니고 SU2 를 source build 해야 합니다.\n"
            "\n"
            "설치 가이드:\n"
            "  git clone https://github.com/su2code/SU2\n"
            "  cd SU2\n"
            "  ./meson.py build -Denable-autodiff=true\n"
            "  ninja -C build install\n"
            "  # HexPress: tools/hex_mesher/ 내부 스크립트\n"
            "\n"
            "Python API (pysu2) 통합 필요:\n"
            "  설치 후 ``from pysu2 import CSinglezoneDriver`` 가능 시\n"
            "  AutoTessell 파이프라인 래퍼 추가 작업 필요.\n"
            "\n"
            f"현재 상태: SU2_CFD={'발견' if su2_found else '미발견'}, "
            f"pysu2={'설치' if pysu2_found else '미설치'}"
        )
        log.warning("tier_su2_hexpress_not_integrated",
                    su2_found=su2_found, pysu2_found=pysu2_found)
        elapsed = time.monotonic() - t_start
        return TierAttempt(
            tier=self.TIER_NAME, status="failed",
            time_seconds=elapsed, error_message=msg,
        )
