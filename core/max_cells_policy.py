"""max-cells 정책 단일 소스."""

from __future__ import annotations

MAX_BG_CELLS_INT32: dict[str, int] = {
    "draft": 500_000,
    "standard": 5_000_000,
    "fine": 200_000_000,
}

MAX_BG_CELLS_INT64: dict[str, int] = {
    "draft": 2_000_000,
    "standard": 50_000_000,
    "fine": 1_500_000_000,
}


def resolve_max_bg_cells_cap(quality_level: str, label_bits: int) -> int:
    """quality/label 조합에 대한 최대 배경 셀 수 cap을 반환한다."""
    limits = MAX_BG_CELLS_INT64 if label_bits >= 64 else MAX_BG_CELLS_INT32
    return limits.get(quality_level, limits["standard"])
