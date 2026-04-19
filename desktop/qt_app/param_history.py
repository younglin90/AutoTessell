"""파라미터 스냅샷 히스토리 — 최대 5개. "⟲ 이전 값" 버튼 지원.

사용자가 epsilon 0.001 → 0.002 → 0.0005 식으로 튜닝하는 경우
"이전 설정으로 되돌리기" 가 필요. Ctrl+Z 대체.

저장소: ~/.autotessell/param_history.json
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

_HISTORY_DIR = Path.home() / ".autotessell"
_HISTORY_FILE = _HISTORY_DIR / "param_history.json"
_MAX_SNAPSHOTS = 5


def load() -> list[dict]:
    """스냅샷 리스트 반환. 최신이 맨 앞."""
    if not _HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [s for s in data if isinstance(s, dict)][:_MAX_SNAPSHOTS]
    except Exception:
        pass
    return []


def push(snapshot: dict) -> list[dict]:
    """새 스냅샷을 맨 앞에 추가. 같은 내용이면 중복 제거. 최대 5개."""
    if not isinstance(snapshot, dict) or not snapshot:
        return load()
    existing = load()
    # 완전히 동일한 스냅샷이면 중복 제거
    existing = [s for s in existing if s != snapshot]
    existing.insert(0, deepcopy(snapshot))
    existing = existing[:_MAX_SNAPSHOTS]
    _save(existing)
    return existing


def peek() -> dict | None:
    """가장 최근 스냅샷 조회 (pop 하지 않음)."""
    entries = load()
    return entries[0] if entries else None


def pop_previous() -> dict | None:
    """현재 바로 이전 스냅샷을 pop해서 반환 + 파일에 반영.

    현재 활성 파라미터와 구분이 어려우므로 단순히 [0] 제거하고 [1] 을 반환한다.
    빈 경우 None.
    """
    entries = load()
    if len(entries) < 2:
        return None
    previous = entries[1]  # 되돌아갈 값
    # 인덱스 0은 "현재"이므로 pop, previous를 맨 앞으로
    entries = entries[1:]
    _save(entries)
    return previous


def clear() -> None:
    try:
        if _HISTORY_FILE.exists():
            _HISTORY_FILE.unlink()
    except Exception:
        pass


def _save(entries: list[dict]) -> None:
    try:
        _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        _HISTORY_FILE.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass
