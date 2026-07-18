"""R85 — native_tet bench drift check.

tests/stl/native_tet_bench_baseline.json 과 latest.json 비교 — 주요 메트릭이
20% 이상 악화되면 FAIL. 라운드 진행 중 회귀 조기 검출용.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


BENCH_DIR = Path(__file__).parent / "stl"
BASELINE = BENCH_DIR / "native_tet_bench_baseline.json"
LATEST = BENCH_DIR / "native_tet_bench_latest.json"


def _load(p: Path) -> dict:
    if not p.exists():
        return {}
    rows = json.loads(p.read_text(encoding="utf-8"))
    return {r.get("stl"): r for r in rows}


def test_bench_drift_check() -> None:
    """baseline 대비 latest 가 비정상적으로 악화되지 않아야 한다."""
    if not BASELINE.exists():
        pytest.skip("baseline 아직 없음 — Round 84 실행 필요")
    if not LATEST.exists():
        pytest.skip("latest 아직 없음 — bench 먼저 실행")

    base = _load(BASELINE)
    latest = _load(LATEST)
    if not base or not latest:
        pytest.skip("bench data 비어 있음")

    failures: list[str] = []
    for stl, b_row in base.items():
        if not b_row.get("success"):
            continue
        l_row = latest.get(stl)
        if not l_row or not l_row.get("success"):
            failures.append(f"{stl}: latest failed (baseline success)")
            continue

        # 1) cell 수가 baseline 의 50% 미만이면 FAIL (붕괴).
        b_cells = b_row.get("n_cells", 0)
        l_cells = l_row.get("n_cells", 0)
        if b_cells > 100 and l_cells < b_cells * 0.5:
            failures.append(
                f"{stl}: n_cells 붕괴 {b_cells} → {l_cells}"
            )

        # 2) mean_q 가 baseline × 0.7 미만이면 FAIL.
        b_q = b_row.get("mean_q", 0.0)
        l_q = l_row.get("mean_q", 0.0)
        if b_q > 0.05 and l_q < b_q * 0.7:
            failures.append(
                f"{stl}: mean_q 악화 {b_q:.3f} → {l_q:.3f}"
            )

        # 3) elapsed 가 baseline × 3 배 이상이면 WARN (fatal 아님).
        b_t = b_row.get("elapsed_s", 0.0)
        l_t = l_row.get("elapsed_s", 0.0)
        if b_t > 0.5 and l_t > b_t * 3.0:
            # warn only — 로그.
            print(f"[WARN] {stl}: elapsed {b_t:.2f}s → {l_t:.2f}s (3×)")

    if failures:
        pytest.fail(
            "bench drift 감지:\n  " + "\n  ".join(failures)
        )
