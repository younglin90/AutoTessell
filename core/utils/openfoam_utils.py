"""OpenFOAM 유틸리티 실행 래퍼."""

from __future__ import annotations

import os
import shlex
import subprocess
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


def _normalize_openfoam_arg(arg: str) -> tuple[str, str | None]:
    """OpenFOAM CLI 인자를 shell-safe path 기준으로 정규화한다."""
    if arg.startswith("-"):
        return arg, None
    return _to_wsl_linux_path(arg)


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

    탐색 순서: OPENFOAM_DIR 환경변수 → 알려진 설치 경로들.
    """
    # 1. 환경변수 우선
    env_dir = os.environ.get("OPENFOAM_DIR")
    if env_dir:
        bashrc = Path(env_dir) / "etc" / "bashrc"
        if bashrc.exists():
            return bashrc

    # 2. 알려진 설치 경로들 (최신 버전부터 탐색)
    search_dirs = [
        "/usr/lib/openfoam",       # Debian/Ubuntu apt 설치
        "/opt",                    # 수동 설치
    ]
    for base in search_dirs:
        base_path = Path(base)
        if not base_path.exists():
            continue
        # openfoam* 디렉터리를 역순 정렬 (최신 버전 우선)
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

    OpenFOAM 설치 경로를 자동 탐색하여 bashrc를 source한 뒤 실행한다.
    탐색 순서: OPENFOAM_DIR 환경변수 → /usr/lib/openfoam/ → /opt/openfoam*.

    Args:
        utility: 실행할 유틸리티 이름 (예: "blockMesh", "snappyHexMesh").
        case_dir: OpenFOAM 케이스 디렉터리 경로.
        args: 추가 CLI 인자 목록.

    Returns:
        subprocess.CompletedProcess 객체.

    Raises:
        FileNotFoundError: OpenFOAM bashrc를 찾을 수 없을 때.
        OpenFOAMError: 유틸리티 실행 실패 또는 returncode != 0.
    """
    bashrc_path = _find_openfoam_bashrc()
    if bashrc_path is None:
        raise FileNotFoundError(
            f"{utility} 실행 불가: OpenFOAM bashrc를 찾을 수 없습니다. "
            "OPENFOAM_DIR 환경변수를 설정하거나 OpenFOAM을 설치하세요."
        )

    bashrc_shell, bashrc_distro = _to_wsl_linux_path(bashrc_path)
    case_dir_shell, case_distro = _to_wsl_linux_path(case_dir)
    source_cmd = f"source {shlex.quote(bashrc_shell)}"

    # 각 인자를 개별적으로 quote 처리하여 공백/특수문자 대응
    safe_parts = [shlex.quote(utility), "-case", shlex.quote(case_dir_shell)]
    arg_distros: list[str] = []
    if args:
        for arg in args:
            normalized_arg, distro = _normalize_openfoam_arg(arg)
            safe_parts.append(shlex.quote(normalized_arg))
            if distro:
                arg_distros.append(distro)

    full_cmd = f"{source_cmd} && {' '.join(safe_parts)}"
    target_distro = (
        case_distro
        or bashrc_distro
        or (arg_distros[0] if arg_distros else None)
        or os.environ.get("WSL_DISTRO_NAME")
        or "Ubuntu"
    )

    logger.info(
        "running_openfoam_utility",
        utility=utility,
        case_dir=case_dir_shell,
        args=args,
        bashrc=bashrc_shell,
    )

    try:
        if os.name == "nt":
            run_cmd = ["wsl", "-d", target_distro, "bash", "-lc", full_cmd]
        else:
            run_cmd = ["bash", "-c", full_cmd]
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
