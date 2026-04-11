"""사용자 친화적 에러 메시지 + 해결 가이드.

파이프라인에서 발생하는 주요 에러를 감지하고 해결 방법을 제시한다.
"""

from __future__ import annotations


class AutoTessellError(Exception):
    """Auto-Tessell 기본 에러. 사용자 친화적 메시지 포함."""

    def __init__(self, message: str, hint: str = "", details: str = "") -> None:
        self.hint = hint
        self.details = details
        super().__init__(message)

    def rich_message(self) -> str:
        parts = [f"[bold red]Error:[/bold red] {self}"]
        if self.hint:
            parts.append(f"[yellow]Hint:[/yellow] {self.hint}")
        if self.details:
            parts.append(f"[dim]{self.details}[/dim]")
        return "\n".join(parts)


def format_missing_dependency_message(
    dependency: str,
    fallback: str,
    action: str,
    *,
    detail: str = "",
) -> str:
    """미설치 의존성 안내 메시지를 표준 포맷으로 생성한다."""
    msg = f"{dependency} unavailable; fallback={fallback}; action={action}"
    if detail:
        return f"{msg}; detail={detail}"
    return msg


# ---------------------------------------------------------------------------
# 에러 진단 + 해결 가이드
# ---------------------------------------------------------------------------

_ERROR_GUIDES: dict[str, dict[str, str]] = {
    "FileNotFoundError": {
        "pattern": "stl|step|obj|ply",
        "message": "입력 파일을 찾을 수 없습니다.",
        "hint": "파일 경로를 확인하세요. 상대 경로는 현재 디렉터리 기준입니다.",
    },
    "cadquery_import": {
        "pattern": "cadquery",
        "message": "STEP/IGES 파일을 처리하려면 cadquery가 필요합니다.",
        "hint": "pip install cadquery",
    },
    "netgen_import": {
        "pattern": "netgen",
        "message": "Netgen 메쉬 생성기를 사용하려면 netgen-mesher가 필요합니다.",
        "hint": "pip install netgen-mesher",
    },
    "pytetwild_import": {
        "pattern": "pytetwild",
        "message": "TetWild 메쉬 생성기를 사용하려면 pytetwild가 필요합니다.",
        "hint": "pip install pytetwild",
    },
    "openfoam_not_found": {
        "pattern": "openfoam|checkMesh|blockMesh|snappy",
        "message": "OpenFOAM이 설치되지 않았거나 PATH에 없습니다.",
        "hint": "OpenFOAM 없이도 Draft/Standard 품질은 동작합니다. Fine 품질(snappyHexMesh)에만 필요합니다.",
    },
    "memory_error": {
        "pattern": "MemoryError|memory",
        "message": "메모리 부족. 입력 메쉬가 너무 크거나 셀 크기가 너무 작습니다.",
        "hint": "--quality draft 또는 --element-size 값을 늘려보세요.",
    },
    "non_watertight": {
        "pattern": "watertight|manifold",
        "message": "입력 메쉬가 watertight하지 않습니다. 자동 수리를 시도합니다.",
        "hint": "심한 경우 --allow-ai-fallback 옵션으로 AI 표면 재생성을 시도할 수 있습니다.",
    },
    "all_tiers_failed": {
        "pattern": "All.*tier.*fail|모든.*Tier.*실패",
        "message": "모든 메쉬 생성 엔진이 실패했습니다.",
        "hint": "1) --quality draft로 낮춰보세요\n"
                "2) 입력 파일 품질을 확인하세요 (watertight? manifold?)\n"
                "3) --element-size 값을 늘려보세요",
    },
}


def diagnose_error(error: Exception) -> str:
    """에러를 진단하고 사용자 친화적 메시지를 반환한다."""
    import re

    error_str = str(error).lower()
    error_type = type(error).__name__

    for _key, guide in _ERROR_GUIDES.items():
        pattern = guide["pattern"]
        if re.search(pattern, error_str, re.IGNORECASE) or re.search(pattern, error_type, re.IGNORECASE):
            return f"{guide['message']}\n  Hint: {guide['hint']}"

    return f"{error_type}: {error}"
