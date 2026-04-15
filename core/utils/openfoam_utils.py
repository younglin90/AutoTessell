"""OpenFOAM 유틸리티 실행 래퍼.

Windows 지원
------------
Windows에서 OpenFOAM을 실행하는 두 가지 방법을 지원한다.

1. ESI OpenFOAM for Windows (권장)
   openfoam.com에서 제공하는 MSYS2 기반 Windows 네이티브 인스톨러.
   설치 후 ``C:\\Program Files\\OpenFOAM\\v<버전>\\`` 에 위치하며
   내부 MSYS2 bash를 통해 snappyHexMesh/cfMesh 등을 직접 실행한다.

2. WSL2 + Linux OpenFOAM (fallback)
   ESI Windows 버전이 없을 때 WSL2를 통해 Linux OpenFOAM을 실행한다.
   ``wsl -d <distro> bash -lc "source ... && snappyHexMesh"`` 방식.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from core.utils.logging import get_logger

logger = get_logger(__name__)


class OpenFOAMError(RuntimeError):
    """OpenFOAM 유틸리티 실행 실패 시 발생."""

    def __init__(
        self,
        utility: str,
        returncode: int,
        stdout: str,
        stderr: str,
    ) -> None:
        self.utility = utility
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(
            f"OpenFOAM utility '{utility}' failed with returncode={returncode}.\n"
            f"stderr: {stderr[:500]}"
        )


def _normalize_shell_path(value: str | Path) -> str:
    """bash 명령에서 사용할 수 있도록 경로 구분자를 정규화한다."""
    return str(value).replace("\\", "/")


def _to_wsl_linux_path(value: str | Path) -> tuple[str, str | None]:
    """WSL UNC 경로를 Linux 경로로 변환한다.

    Returns:
        (normalized_path, distro_name_or_none)
    """
    normalized = _normalize_shell_path(value)
    lowered = normalized.lower()

    for prefix in ("//wsl.localhost/", "//wsl$/"):
        if lowered.startswith(prefix):
            rest = normalized[len(prefix):]
            parts = [p for p in rest.split("/") if p]
            if len(parts) >= 2:
                distro = parts[0]
                linux_path = "/" + "/".join(parts[1:])
                return linux_path, distro
    return normalized, None


def _to_msys_path(value: str | Path) -> str:
    """Windows 절대 경로를 MSYS2 경로 형식으로 변환한다.

    예) ``C:\\Program Files\\OpenFOAM`` → ``/c/Program Files/OpenFOAM``
    """
    p = str(value).replace("\\", "/")
    # C:/foo → /c/foo
    if len(p) >= 2 and p[1] == ":":
        p = "/" + p[0].lower() + p[2:]
    return p


def _normalize_openfoam_arg(arg: str) -> tuple[str, str | None]:
    """OpenFOAM CLI 인자를 shell-safe path 기준으로 정규화한다."""
    if arg.startswith("-"):
        return arg, None
    return _to_wsl_linux_path(arg)


# ---------------------------------------------------------------------------
# ESI OpenFOAM for Windows 감지
# ---------------------------------------------------------------------------

def _find_esi_openfoam_windows() -> tuple[Path, Path] | None:
    """ESI OpenFOAM for Windows (MSYS2 기반) 설치 경로를 찾는다.

    Returns:
        (bashrc_path, msys_bash_path) 또는 None.

    ESI 설치 구조::

        C:\\Program Files\\OpenFOAM\\
        └── v2406\\          ← 버전 디렉터리
            ├── etc\\bashrc  ← OpenFOAM 환경 설정
            └── msys64\\
                └── usr\\bin\\bash.exe  ← MSYS2 bash
    """
    if sys.platform != "win32":
        return None

    base_dirs = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "OpenFOAM",
        Path(r"C:\OpenFOAM"),
        Path(r"C:\Program Files\ESI\OpenFOAM"),
    ]
    env_dir = os.environ.get("OPENFOAM_DIR")
    if env_dir:
        base_dirs.insert(0, Path(env_dir).parent)

    for base in base_dirs:
        if not base.exists():
            continue
        try:
            candidates = sorted(base.iterdir(), reverse=True)
        except PermissionError:
            continue
        for ver_dir in candidates:
            if not ver_dir.is_dir():
                continue
            bashrc = ver_dir / "etc" / "bashrc"
            bash_exe = ver_dir / "msys64" / "usr" / "bin" / "bash.exe"
            if bashrc.exists() and bash_exe.exists():
                logger.info(
                    "esi_openfoam_windows_found",
                    version_dir=str(ver_dir),
                    bash=str(bash_exe),
                )
                return bashrc, bash_exe

    return None


def get_openfoam_label_size() -> int:
    """OpenFOAM의 label 크기(비트)를 감지한다. 32 또는 64 반환. 미설치 시 0."""
    bashrc = _find_openfoam_bashrc()
    if bashrc is None:
        return 0
    # platforms 디렉터리에서 Int32/Int64 확인
    of_dir = bashrc.parent.parent
    platforms = of_dir / "platforms"
    if platforms.exists():
        names = [d.name for d in platforms.iterdir()]
        # Int32/Int64가 공존하는 경우(멀티 빌드)에는 Int64를 우선한다.
        if any("Int64" in name for name in names):
            return 64
        if any("Int32" in name for name in names):
            return 32
    return 32  # default assumption


def _find_openfoam_bashrc() -> Path | None:
    """OpenFOAM bashrc 경로를 자동 탐색한다.

    탐색 순서:
      1. OPENFOAM_DIR 환경변수
      2. Windows: ESI OpenFOAM for Windows (``C:\\Program Files\\OpenFOAM\\``)
      3. Linux: 알려진 설치 경로 (``/usr/lib/openfoam/``, ``/opt/``)
    """
    # 1. 환경변수 우선
    env_dir = os.environ.get("OPENFOAM_DIR")
    if env_dir:
        bashrc = Path(env_dir) / "etc" / "bashrc"
        if bashrc.exists():
            return bashrc

    # 2. Windows: ESI OpenFOAM for Windows
    if sys.platform == "win32":
        esi = _find_esi_openfoam_windows()
        if esi is not None:
            return esi[0]
        return None  # Windows에서 ESI 없으면 WSL fallback은 run_openfoam에서 처리

    # 3. Linux: 알려진 설치 경로들 (최신 버전부터 탐색)
    search_dirs = [
        "/usr/lib/openfoam",       # Debian/Ubuntu apt 설치
        "/opt",                    # 수동 설치
    ]
    for base in search_dirs:
        base_path = Path(base)
        if not base_path.exists():
            continue
        candidates = sorted(base_path.glob("openfoam*"), reverse=True)
        for candidate in candidates:
            bashrc = candidate / "etc" / "bashrc"
            if bashrc.exists():
                return bashrc

    return None


def run_openfoam(
    utility: str,
    case_dir: Path,
    args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """OpenFOAM 유틸리티를 실행한다.

    Windows에서는 다음 순서로 실행 방법을 결정한다.

    1. ESI OpenFOAM for Windows 감지 → MSYS2 bash로 직접 실행
    2. ESI 없음 → WSL2를 통해 Linux OpenFOAM 실행

    Args:
        utility: 실행할 유틸리티 이름 (예: "blockMesh", "snappyHexMesh").
        case_dir: OpenFOAM 케이스 디렉터리 경로.
        args: 추가 CLI 인자 목록.

    Returns:
        subprocess.CompletedProcess 객체.

    Raises:
        FileNotFoundError: OpenFOAM을 찾을 수 없을 때.
        OpenFOAMError: 유틸리티 실행 실패 또는 returncode != 0.
    """
    # ── Windows 분기 ────────────────────────────────────────────────────────
    if sys.platform == "win32":
        return _run_openfoam_windows(utility, case_dir, args)

    # ── Linux/macOS 분기 ────────────────────────────────────────────────────
    bashrc_path = _find_openfoam_bashrc()
    if bashrc_path is None:
        raise FileNotFoundError(
            f"{utility} 실행 불가: OpenFOAM bashrc를 찾을 수 없습니다. "
            "OPENFOAM_DIR 환경변수를 설정하거나 OpenFOAM을 설치하세요."
        )

    bashrc_shell, _ = _to_wsl_linux_path(bashrc_path)
    case_dir_shell, _ = _to_wsl_linux_path(case_dir)
    source_cmd = f"source {shlex.quote(bashrc_shell)}"
    safe_parts = [shlex.quote(utility), "-case", shlex.quote(case_dir_shell)]
    if args:
        for arg in args:
            normalized_arg, _ = _normalize_openfoam_arg(arg)
            safe_parts.append(shlex.quote(normalized_arg))

    full_cmd = f"{source_cmd} && {' '.join(safe_parts)}"
    run_cmd = ["bash", "-c", full_cmd]

    logger.info(
        "running_openfoam_utility",
        utility=utility,
        case_dir=case_dir_shell,
        args=args,
        bashrc=bashrc_shell,
    )
    return _execute(utility, run_cmd)


def _run_openfoam_windows(
    utility: str,
    case_dir: Path,
    args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Windows에서 OpenFOAM 유틸리티를 실행한다.

    ESI OpenFOAM for Windows (MSYS2 bash) 우선, 없으면 WSL2 fallback.
    """
    esi = _find_esi_openfoam_windows()

    if esi is not None:
        # ESI OpenFOAM for Windows: MSYS2 bash를 통해 실행
        bashrc_path, bash_exe = esi
        msys_bashrc = _to_msys_path(bashrc_path)
        msys_case = _to_msys_path(case_dir)
        safe_parts = [shlex.quote(utility), "-case", shlex.quote(msys_case)]
        if args:
            for arg in args:
                if arg.startswith("-"):
                    safe_parts.append(shlex.quote(arg))
                else:
                    safe_parts.append(shlex.quote(_to_msys_path(arg)))
        full_cmd = f"source {shlex.quote(msys_bashrc)} && {' '.join(safe_parts)}"
        run_cmd = [str(bash_exe), "-lc", full_cmd]
        logger.info(
            "running_openfoam_utility",
            utility=utility,
            backend="esi_windows_msys2",
            case_dir=msys_case,
            bash=str(bash_exe),
        )
    else:
        # WSL2 fallback
        bashrc_path_wsl: Path | None = None
        # WSL 내부의 bashrc를 탐색 (\\wsl.localhost\Ubuntu\... 경로)
        for wsl_base in (
            Path(r"\\wsl.localhost\Ubuntu\usr\lib\openfoam"),
            Path(r"\\wsl$\Ubuntu\usr\lib\openfoam"),
            Path(r"\\wsl.localhost\Ubuntu\opt"),
        ):
            if wsl_base.exists():
                for candidate in sorted(wsl_base.glob("openfoam*"), reverse=True):
                    rc = candidate / "etc" / "bashrc"
                    if rc.exists():
                        bashrc_path_wsl = rc
                        break
            if bashrc_path_wsl:
                break

        if bashrc_path_wsl is None:
            raise FileNotFoundError(
                f"{utility} 실행 불가: Windows에서 OpenFOAM을 찾을 수 없습니다.\n"
                "해결 방법:\n"
                "  1. ESI OpenFOAM for Windows 설치: https://openfoam.com/download/windows\n"
                "  2. 또는 WSL2에 OpenFOAM 설치 후 재시도"
            )

        bashrc_shell, bashrc_distro = _to_wsl_linux_path(bashrc_path_wsl)
        case_dir_shell, case_distro = _to_wsl_linux_path(case_dir)
        target_distro = (
            case_distro
            or bashrc_distro
            or os.environ.get("WSL_DISTRO_NAME")
            or "Ubuntu"
        )
        safe_parts = [shlex.quote(utility), "-case", shlex.quote(case_dir_shell)]
        if args:
            for arg in args:
                normalized_arg, _ = _normalize_openfoam_arg(arg)
                safe_parts.append(shlex.quote(normalized_arg))
        full_cmd = (
            f"source {shlex.quote(bashrc_shell)} && {' '.join(safe_parts)}"
        )
        run_cmd = ["wsl", "-d", target_distro, "bash", "-lc", full_cmd]
        logger.info(
            "running_openfoam_utility",
            utility=utility,
            backend="wsl2",
            distro=target_distro,
            case_dir=case_dir_shell,
        )

    return _execute(utility, run_cmd)


def _execute(
    utility: str,
    run_cmd: list[str],
) -> subprocess.CompletedProcess[str]:
    """subprocess를 실행하고 결과를 반환한다."""
    try:
        result = subprocess.run(
            run_cmd,
            capture_output=True,
            text=True,
            timeout=3600,
        )
    except FileNotFoundError as exc:
        raise OpenFOAMError(
            utility=utility,
            returncode=-1,
            stdout="",
            stderr=str(exc),
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise OpenFOAMError(
            utility=utility,
            returncode=-2,
            stdout="",
            stderr=f"Timeout after 3600s: {exc}",
        ) from exc

    if result.returncode != 0:
        logger.warning(
            "openfoam_utility_failed",
            utility=utility,
            returncode=result.returncode,
            stderr=result.stderr[:500],
        )
        raise OpenFOAMError(
            utility=utility,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    logger.info(
        "openfoam_utility_success",
        utility=utility,
        returncode=result.returncode,
    )
    return result
