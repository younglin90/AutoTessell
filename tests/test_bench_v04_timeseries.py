"""bench_v04_matrix time-series 저장 + diff 회귀 테스트 (v0.4.0-beta16)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# tests/stl 디렉터리를 sys.path 에 추가해 bench_v04_matrix 모듈 import 가능하게
_STL_DIR = _REPO / "tests" / "stl"
if str(_STL_DIR) not in sys.path:
    sys.path.insert(0, str(_STL_DIR))

import bench_v04_matrix as bvm  # type: ignore[import-not-found]  # noqa: E402


def _sample_run(label: str, tier: str, mt: str, q: str, ok: bool, t: float) -> dict:
    return {
        "stl": label,
        "tier": tier,
        "mesh_type": mt,
        "quality": q,
        "returncode": 0 if ok else 1,
        "polyMesh_created": ok,
        "elapsed_s": t,
        "last_lines": ["OK" if ok else "FAIL"],
        "difficulty": label.split("_")[0],
    }


def test_save_results_timestamped_writes_both_files(tmp_path: Path) -> None:
    """save_results_timestamped 가 snapshot + latest 두 파일에 같은 내용을 쓴다."""
    results = [
        _sample_run("01_easy_cube.stl", "native_tet", "tet", "draft", True, 10.0),
        _sample_run("02_medium.stl", "native_hex", "hex_dominant", "draft", False, 30.0),
    ]
    snap, latest = bvm.save_results_timestamped(results, tmp_path, stamp="20260423T120000")
    assert snap.exists()
    assert latest.exists()
    assert snap.name == "bench_v04_20260423T120000.json"
    assert latest.name == "bench_v04_result.json"
    snap_data = json.loads(snap.read_text())
    latest_data = json.loads(latest.read_text())
    assert snap_data == latest_data
    assert snap_data == results


def test_list_snapshots_excludes_result_and_sorts_newest_first(tmp_path: Path) -> None:
    """list_snapshots 가 bench_v04_result.json 을 제외하고 최신순 정렬."""
    # 여러 snapshot 생성 (suffix 만 다름)
    (tmp_path / "bench_v04_20260101T000000.json").write_text("[]")
    (tmp_path / "bench_v04_20260423T120000.json").write_text("[]")
    (tmp_path / "bench_v04_20260201T000000.json").write_text("[]")
    (tmp_path / "bench_v04_result.json").write_text("[]")

    snaps = bvm.list_snapshots(tmp_path)
    names = [p.name for p in snaps]
    assert "bench_v04_result.json" not in names
    # 최신순: 20260423 > 20260201 > 20260101
    assert names[0] == "bench_v04_20260423T120000.json"
    assert names[-1] == "bench_v04_20260101T000000.json"
    assert len(snaps) == 3


def test_compare_runs_detects_newly_passing_and_failing() -> None:
    """compare_runs 가 PASS→FAIL / FAIL→PASS / 유지 을 올바르게 분류."""
    prev = [
        _sample_run("01.stl", "native_tet", "tet", "draft", True, 10.0),
        _sample_run("02.stl", "native_hex", "hex_dominant", "draft", False, 30.0),
        _sample_run("03.stl", "native_poly", "poly", "draft", True, 5.0),
    ]
    curr = [
        _sample_run("01.stl", "native_tet", "tet", "draft", False, 12.0),  # PASS → FAIL
        _sample_run("02.stl", "native_hex", "hex_dominant", "draft", True, 25.0),  # FAIL → PASS
        _sample_run("03.stl", "native_poly", "poly", "draft", True, 6.0),  # 유지 (PASS)
    ]
    diff = bvm.compare_runs(prev, curr)
    assert len(diff["newly_failing"]) == 1
    assert diff["newly_failing"][0]["stl"] == "01.stl"
    assert diff["newly_failing"][0]["prev_pass"] is True
    assert diff["newly_failing"][0]["curr_pass"] is False

    assert len(diff["newly_passing"]) == 1
    assert diff["newly_passing"][0]["stl"] == "02.stl"

    assert len(diff["unchanged"]) == 1
    assert diff["unchanged"][0]["stl"] == "03.stl"


def test_compare_runs_handles_added_and_removed_combos() -> None:
    """한 쪽에만 존재하는 combo 처리: 추가된 PASS 는 newly_passing, 제거된 PASS 는
    newly_failing 으로 간주."""
    prev = [
        _sample_run("01.stl", "native_tet", "tet", "draft", True, 10.0),
    ]
    curr = [
        _sample_run("01.stl", "native_tet", "tet", "draft", True, 10.0),
        _sample_run("new.stl", "native_hex", "hex_dominant", "draft", True, 20.0),
    ]
    diff = bvm.compare_runs(prev, curr)
    # 새 combo 가 PASS 로 추가
    assert any(e["stl"] == "new.stl" for e in diff["newly_passing"])

    # 역방향: combo 제거 (PASS → 없음)
    diff2 = bvm.compare_runs(curr, prev)
    failing_stls = [e["stl"] for e in diff2["newly_failing"]]
    assert "new.stl" in failing_stls


@pytest.mark.parametrize("stamp", [None, "20260423T153000"])
def test_save_results_timestamped_respects_custom_stamp(
    tmp_path: Path, stamp: str | None,
) -> None:
    """stamp 파라미터가 None 이면 현재 UTC, 지정 시 그 값 사용."""
    results = [_sample_run("x.stl", "native_tet", "tet", "draft", True, 1.0)]
    snap, _ = bvm.save_results_timestamped(results, tmp_path, stamp=stamp)
    if stamp is None:
        # bench_v04_YYYYMMDDTHHMMSS.json 패턴만 확인
        assert snap.stem.startswith("bench_v04_")
        assert len(snap.stem) == len("bench_v04_") + 15  # YYYYMMDDTHHMMSS = 15
    else:
        assert snap.name == f"bench_v04_{stamp}.json"
