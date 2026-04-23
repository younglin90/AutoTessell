"""beta70 — bench_v04_matrix drift-check 유닛 회귀.

`check_drift_against_baseline` 가 baseline 대비 성공률 저하를 올바르게 감지하는지
verify. slow 하지 않음 (mock JSON 만 사용).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.stl.bench_v04_matrix import (
    check_drift_against_baseline,
    compute_success_rate,
)


# ---------------------------------------------------------------------------
# compute_success_rate
# ---------------------------------------------------------------------------


def test_success_rate_all_pass() -> None:
    results = [
        {"polyMesh_created": True},
        {"polyMesh_created": True},
    ]
    assert compute_success_rate(results) == pytest.approx(1.0)


def test_success_rate_all_fail() -> None:
    results = [
        {"polyMesh_created": False},
        {"polyMesh_created": False},
    ]
    assert compute_success_rate(results) == pytest.approx(0.0)


def test_success_rate_mixed() -> None:
    results = [
        {"polyMesh_created": True},
        {"polyMesh_created": False},
        {"polyMesh_created": True},
        {"polyMesh_created": False},
    ]
    assert compute_success_rate(results) == pytest.approx(0.5)


def test_success_rate_empty_returns_zero() -> None:
    assert compute_success_rate([]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# check_drift_against_baseline
# ---------------------------------------------------------------------------


def _write_baseline(tmp: Path, results: list[dict]) -> Path:
    p = tmp / "baseline.json"
    p.write_text(json.dumps(results), encoding="utf-8")
    return p


def test_drift_check_identical_baseline_passes(tmp_path: Path) -> None:
    """baseline == current → delta 0, 허용."""
    results = [
        {"stl": "a.stl", "tier": "tet", "quality": "draft", "polyMesh_created": True},
    ]
    base = _write_baseline(tmp_path, results)
    ok, rep = check_drift_against_baseline(base, results)
    assert ok is True
    assert rep["delta"] == pytest.approx(0.0)


def test_drift_check_improvement_passes(tmp_path: Path) -> None:
    """current 가 baseline 보다 성공률 높음 → 허용."""
    base_results = [
        {"stl": "a.stl", "tier": "tet", "quality": "draft", "polyMesh_created": True},
        {"stl": "b.stl", "tier": "tet", "quality": "draft", "polyMesh_created": False},
    ]
    curr_results = [
        {"stl": "a.stl", "tier": "tet", "quality": "draft", "polyMesh_created": True},
        {"stl": "b.stl", "tier": "tet", "quality": "draft", "polyMesh_created": True},
    ]
    base = _write_baseline(tmp_path, base_results)
    ok, rep = check_drift_against_baseline(base, curr_results)
    assert ok is True
    assert rep["delta"] > 0
    assert rep["n_newly_passing"] == 1


def test_drift_check_small_regression_passes(tmp_path: Path) -> None:
    """5% 하락은 기본 허용치 (-10%) 내 → 허용."""
    base_results = [{"stl": f"{i}.stl", "tier": "tet", "quality": "draft",
                    "polyMesh_created": True} for i in range(20)]
    curr_results = list(base_results)
    curr_results[0] = {**curr_results[0], "polyMesh_created": False}
    base = _write_baseline(tmp_path, base_results)
    ok, rep = check_drift_against_baseline(base, curr_results)
    assert ok is True
    assert rep["delta"] == pytest.approx(-0.05, abs=1e-9)


def test_drift_check_large_regression_fails(tmp_path: Path) -> None:
    """50% 하락 → 허용치 (-10%) 초과 → fail."""
    base_results = [{"stl": f"{i}.stl", "tier": "tet", "quality": "draft",
                    "polyMesh_created": True} for i in range(10)]
    curr_results = list(base_results)
    for i in range(5):
        curr_results[i] = {**curr_results[i], "polyMesh_created": False}
    base = _write_baseline(tmp_path, base_results)
    ok, rep = check_drift_against_baseline(base, curr_results)
    assert ok is False
    assert rep["delta"] == pytest.approx(-0.5)
    assert rep["n_newly_failing"] == 5


def test_drift_check_custom_threshold(tmp_path: Path) -> None:
    """더 엄격한 threshold (-0.02) 로 5% 하락도 fail."""
    base_results = [{"stl": f"{i}.stl", "tier": "tet", "quality": "draft",
                    "polyMesh_created": True} for i in range(20)]
    curr_results = list(base_results)
    curr_results[0] = {**curr_results[0], "polyMesh_created": False}
    base = _write_baseline(tmp_path, base_results)
    ok, _ = check_drift_against_baseline(
        base, curr_results, min_success_rate_delta=-0.02,
    )
    assert ok is False


def test_drift_check_missing_baseline_returns_false(tmp_path: Path) -> None:
    """baseline 파일 없음 → (False, error)."""
    ok, rep = check_drift_against_baseline(tmp_path / "missing.json", [])
    assert ok is False
    assert "error" in rep


def test_drift_check_corrupt_baseline_returns_false(tmp_path: Path) -> None:
    """baseline JSON 파싱 실패 → (False, error)."""
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json", encoding="utf-8")
    ok, rep = check_drift_against_baseline(bad, [])
    assert ok is False
    assert "error" in rep
