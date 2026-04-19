"""PySide6 + PyVistaQt 기반 Qt GUI 모듈."""
from __future__ import annotations


# matplotlib 한글 폰트 fallback — histogram/report의 "셀 수", "갱신 중" 같은
# 한글 레이블이 "Glyph missing" 경고로 깨지는 것을 방지.
# 설치된 폰트 중 먼저 발견되는 것이 사용됨.
def _try_register_windows_fonts() -> None:
    """WSL 환경에서 /mnt/c/Windows/Fonts 의 Korean 폰트를 matplotlib에 등록."""
    try:
        from pathlib import Path

        from matplotlib import font_manager

        win_fonts_dir = Path("/mnt/c/Windows/Fonts")
        if not win_fonts_dir.exists():
            return
        # Korean-capable fonts (Malgun Gothic, etc.)
        for pattern in ("malgun*.ttf", "batang*.ttc", "gulim*.ttc"):
            for p in win_fonts_dir.glob(pattern):
                try:
                    font_manager.fontManager.addfont(str(p))
                except Exception:
                    pass
    except Exception:
        pass


def _configure_matplotlib_fonts() -> None:
    try:
        import matplotlib

        _try_register_windows_fonts()

        _korean_sans = [
            "Pretendard", "Malgun Gothic", "NanumGothic", "AppleGothic",
            "Noto Sans CJK KR", "DejaVu Sans",
        ]
        # monospace 패밀리에도 한국어 지원 폰트 (완전 지원 안 되도 sans fallback 허용)
        _korean_mono = [
            "D2Coding", "Noto Sans Mono CJK KR", "NanumGothicCoding",
            "Pretendard", "Malgun Gothic",  # sans로 한글 처리
            "DejaVu Sans Mono", "DejaVu Sans",
        ]

        def _merge(existing: list[str], preferred: list[str]) -> list[str]:
            merged: list[str] = []
            for f in preferred:
                if f not in merged:
                    merged.append(f)
            for f in existing:
                if f not in merged:
                    merged.append(f)
            return merged

        matplotlib.rcParams["font.sans-serif"] = _merge(
            list(matplotlib.rcParams.get("font.sans-serif", [])), _korean_sans
        )
        matplotlib.rcParams["font.monospace"] = _merge(
            list(matplotlib.rcParams.get("font.monospace", [])), _korean_mono
        )
        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass


_configure_matplotlib_fonts()

__all__ = ["AutoTessellWindow", "PipelineWorker"]
