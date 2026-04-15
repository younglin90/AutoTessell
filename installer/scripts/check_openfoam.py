"""OpenFOAM 설치 상태 확인 및 안내 스크립트.

인스톨러 post_install 단계에서 실행된다.
ESI OpenFOAM for Windows가 설치되어 있지 않으면 설치 안내를 표시한다.
"""

from __future__ import annotations

import sys
from pathlib import Path


def check_esi_openfoam_windows() -> tuple[bool, str]:
    """ESI OpenFOAM for Windows 설치 여부를 확인한다."""
    import os

    base_dirs = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "OpenFOAM",
        Path(r"C:\OpenFOAM"),
    ]
    for base in base_dirs:
        if not base.exists():
            continue
        try:
            for ver_dir in sorted(base.iterdir(), reverse=True):
                bashrc = ver_dir / "etc" / "bashrc"
                bash_exe = ver_dir / "msys64" / "usr" / "bin" / "bash.exe"
                if bashrc.exists() and bash_exe.exists():
                    return True, str(ver_dir)
        except Exception:
            continue
    return False, ""


def check_wsl_openfoam() -> bool:
    """WSL2에 OpenFOAM이 설치되어 있는지 확인한다."""
    for wsl_base in (
        Path(r"\\wsl.localhost\Ubuntu\usr\lib\openfoam"),
        Path(r"\\wsl$\Ubuntu\usr\lib\openfoam"),
    ):
        try:
            if wsl_base.exists():
                return True
        except Exception:
            pass
    return False


def main() -> None:
    print("\n[AutoTessell] OpenFOAM 감지")

    if sys.platform != "win32":
        print("  Windows 환경이 아님, 건너뜀")
        return

    found_esi, esi_path = check_esi_openfoam_windows()
    found_wsl = check_wsl_openfoam()

    if found_esi:
        print(f"  ESI OpenFOAM for Windows: 발견 ({esi_path})")
        print("  snappyHexMesh / cfMesh Tier 사용 가능")
        return

    if found_wsl:
        print("  WSL2 OpenFOAM: 발견")
        print("  snappyHexMesh / cfMesh Tier는 WSL2를 통해 실행됩니다")
        return

    print("  OpenFOAM: 미설치")
    print()
    print("  ┌─────────────────────────────────────────────────────────────┐")
    print("  │  snappyHexMesh / cfMesh Tier를 사용하려면 OpenFOAM이        │")
    print("  │  필요합니다. 다음 중 하나를 설치하세요:                     │")
    print("  │                                                             │")
    print("  │  방법 1 (권장): ESI OpenFOAM for Windows                   │")
    print("  │    https://openfoam.com/download/windows                   │")
    print("  │                                                             │")
    print("  │  방법 2: WSL2 + Ubuntu + OpenFOAM                          │")
    print("  │    wsl --install                                            │")
    print("  │    apt install openfoam2406                                │")
    print("  │                                                             │")
    print("  │  OpenFOAM 없이도 14개 이상의 메쉬 생성 엔진이 동작합니다.   │")
    print("  └─────────────────────────────────────────────────────────────┘")
    print()

    # GUI 팝업 (가능한 경우)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            0,
            (
                "AutoTessell 설치가 완료되었습니다.\n\n"
                "snappyHexMesh / cfMesh Tier를 사용하려면 OpenFOAM이 필요합니다.\n\n"
                "권장: ESI OpenFOAM for Windows 설치\n"
                "https://openfoam.com/download/windows\n\n"
                "OpenFOAM 없이도 14개 이상의 메쉬 엔진을 바로 사용할 수 있습니다."
            ),
            "AutoTessell — OpenFOAM 안내",
            0x40,  # MB_ICONINFORMATION
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()
