"""실행 이력 기록 — ~/.autotessell/history.jsonl 추가만.

각 파이프라인 완료 시 한 줄씩 추가. 절대 삭제/편집 안 함 (감사 용도).
최대 1000 줄 넘으면 앞쪽 잘라냄 (~100KB 상한).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

_HISTORY_DIR = Path.home() / ".autotessell"
_HISTORY_FILE = _HISTORY_DIR / "history.jsonl"
_MAX_ENTRIES = 1000


@dataclass
class HistoryEntry:
    timestamp: str               # ISO 8601
    input_file: str
    output_dir: str
    quality_level: str
    tier_used: str
    success: bool
    elapsed_seconds: float
    n_cells: int = 0
    max_aspect_ratio: float | None = None
    max_skewness: float | None = None
    max_non_orthogonality: float | None = None
    error: str | None = None


def record(entry: HistoryEntry) -> None:
    """이력 한 줄 추가."""
    try:
        _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        with _HISTORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        _trim_if_needed()
    except Exception:
        pass


def load_all() -> list[HistoryEntry]:
    """모든 이력 읽기 — 최신순 정렬."""
    if not _HISTORY_FILE.exists():
        return []
    entries: list[HistoryEntry] = []
    try:
        with _HISTORY_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entries.append(HistoryEntry(**data))
                except Exception:
                    continue
    except Exception:
        return []
    # 최신이 먼저
    entries.reverse()
    return entries


def clear() -> None:
    """이력 파일 전체 삭제."""
    try:
        if _HISTORY_FILE.exists():
            _HISTORY_FILE.unlink()
    except Exception:
        pass


def _trim_if_needed() -> None:
    if not _HISTORY_FILE.exists():
        return
    try:
        lines = _HISTORY_FILE.read_text(encoding="utf-8").splitlines()
        if len(lines) > _MAX_ENTRIES:
            lines = lines[-_MAX_ENTRIES:]
            _HISTORY_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def make_entry_from_result(
    input_file: str | Path,
    output_dir: str | Path,
    quality_level: str,
    result: object,
) -> HistoryEntry:
    """PipelineResult 객체에서 HistoryEntry 생성."""
    quality_report = getattr(result, "quality_report", None)
    check_mesh = getattr(quality_report, "check_mesh", None) if quality_report else None
    generator_log = getattr(result, "generator_log", None)
    summary = getattr(generator_log, "execution_summary", None) if generator_log else None

    return HistoryEntry(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        input_file=str(input_file),
        output_dir=str(output_dir),
        quality_level=quality_level,
        tier_used=getattr(summary, "selected_tier", "") if summary else "",
        success=bool(getattr(result, "success", False)),
        elapsed_seconds=float(getattr(result, "total_time_seconds", 0.0) or 0.0),
        n_cells=int(getattr(check_mesh, "cells", 0) or 0),
        max_aspect_ratio=getattr(check_mesh, "max_aspect_ratio", None),
        max_skewness=getattr(check_mesh, "max_skewness", None),
        max_non_orthogonality=getattr(check_mesh, "max_non_orthogonality", None),
        error=getattr(result, "error", None),
    )
