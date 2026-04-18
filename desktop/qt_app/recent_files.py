"""최근 파일 기록 — ~/.autotessell/recent.json 영속화.

5개 고정 슬롯. 가장 최근이 맨 앞. 중복은 자동 제거.
"""
from __future__ import annotations

import json
from pathlib import Path

_RECENT_DIR = Path.home() / ".autotessell"
_RECENT_FILE = _RECENT_DIR / "recent.json"
_MAX_ENTRIES = 5


def load() -> list[str]:
    """최근 파일 경로 리스트 반환. 존재하지 않으면 빈 리스트."""
    if not _RECENT_FILE.exists():
        return []
    try:
        data = json.loads(_RECENT_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            # 존재하지 않는 경로는 자동 제거
            return [p for p in data if isinstance(p, str) and Path(p).exists()][:_MAX_ENTRIES]
    except Exception:
        pass
    return []


def add(path: str | Path) -> list[str]:
    """경로 추가 (중복 제거, 맨 앞에 삽입, 최대 5개). 갱신된 리스트 반환."""
    p = str(Path(path).expanduser().resolve())
    entries = load()
    # 중복 제거
    entries = [e for e in entries if e != p]
    entries.insert(0, p)
    entries = entries[:_MAX_ENTRIES]
    _save(entries)
    return entries


def clear() -> None:
    """최근 파일 기록 전체 삭제."""
    _save([])


def _save(entries: list[str]) -> None:
    try:
        _RECENT_DIR.mkdir(parents=True, exist_ok=True)
        _RECENT_FILE.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
