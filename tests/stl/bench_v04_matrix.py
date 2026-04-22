"""v0.4 native_* 엔진 × 5 난이도 STL × 3 품질 매트릭스 실행 스크립트.

사용:
    python3 tests/stl/bench_v04_matrix.py [--limit N]          # 실행
    python3 tests/stl/bench_v04_matrix.py --diff               # 최근 2 run 비교

출력:
    stdout 에 결과 테이블 + 타임스탬프된 JSON 저장:
      tests/stl/bench_v04_YYYYMMDDTHHMMSS.json          (실행별 snapshot)
      tests/stl/bench_v04_result.json                   (latest pointer, copy)

각 조합에 대해 CLI 를 subprocess 로 호출해 실제 end-to-end 동작 검증.
OpenFOAM 가용 시 Evaluator 판정 포함, 불가 시 생성 성공 여부만.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


_REPO = Path(__file__).resolve().parents[2]
STL_DIR = _REPO / "tests" / "stl"

DIFFICULTIES = [
    ("01_easy", "01_easy_cube.stl"),
    ("02_medium", "02_medium_cylinder.stl"),
    ("03_hard", "03_hard_bracket.stl"),
    ("04_extreme", "04_extreme_gear.stl"),
    ("05_ultra", "05_ultra_knot.stl"),
]

ENGINES = [
    ("native_tet", "tet"),
    ("native_hex", "hex_dominant"),
    ("native_poly", "poly"),
]

QUALITIES = ["draft", "standard"]  # v0.4.0-beta4+: standard 확장


def _run_one(
    stl: Path, tier: str, mesh_type: str, quality: str, tmp_base: Path,
) -> dict:
    out = tmp_base / f"{stl.stem}_{tier}_{quality}"
    if out.exists():
        shutil.rmtree(out)
    cmd = [
        "python3", "-m", "cli.main", "run", str(stl),
        "-o", str(out),
        "--mesh-type", mesh_type,
        "--quality", quality,
        "--tier", tier,
        "--auto-retry", "off",
        "--prefer-native",
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_REPO) + os.pathsep + env.get("PYTHONPATH", "")
    t0 = time.perf_counter()
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=300, cwd=str(_REPO), env=env,
        )
        elapsed = time.perf_counter() - t0
        poly = out / "constant" / "polyMesh"
        poly_ok = (poly / "faces").exists()
        tail = (r.stdout or r.stderr).strip().splitlines()[-3:]
        return {
            "stl": stl.name, "tier": tier, "mesh_type": mesh_type,
            "quality": quality,
            "returncode": r.returncode,
            "polyMesh_created": poly_ok,
            "elapsed_s": round(elapsed, 2),
            "last_lines": tail,
        }
    except subprocess.TimeoutExpired:
        return {
            "stl": stl.name, "tier": tier, "mesh_type": mesh_type,
            "quality": quality,
            "returncode": -1,
            "polyMesh_created": False,
            "elapsed_s": round(time.perf_counter() - t0, 2),
            "last_lines": ["TIMEOUT"],
        }


def _print_table(results: list[dict]) -> None:
    # 각 (stl, engine) 조합 결과 한 줄
    print()
    print("| STL | Engine | Quality | polyMesh | time | rc |")
    print("|------|--------|---------|----------|------|----|")
    for r in results:
        mark = "✓" if r["polyMesh_created"] else "✗"
        print(
            f"| {r['stl']:<24s} | {r['tier']:<12s} | {r['quality']:<8s} "
            f"| {mark} | {r['elapsed_s']:>6.1f}s | {r['returncode']} |"
        )


# ---------------------------------------------------------------------------
# Time-series helpers (v0.4.0-beta16)
# ---------------------------------------------------------------------------


def _now_utc_stamp() -> str:
    """UTC 타임스탬프 ``YYYYMMDDTHHMMSS`` (파일명 호환)."""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S")


def save_results_timestamped(
    results: list[dict], stl_dir: Path, stamp: str | None = None,
) -> tuple[Path, Path]:
    """results 를 두 경로에 저장.

    1. ``bench_v04_<stamp>.json`` — 실행별 snapshot (time-series).
    2. ``bench_v04_result.json`` — latest pointer (snapshot 의 정확한 copy).

    Returns:
        (snapshot_path, latest_path).
    """
    stamp = stamp or _now_utc_stamp()
    snapshot = stl_dir / f"bench_v04_{stamp}.json"
    latest = stl_dir / "bench_v04_result.json"
    payload = json.dumps(results, indent=2)
    snapshot.write_text(payload, encoding="utf-8")
    latest.write_text(payload, encoding="utf-8")
    return snapshot, latest


def list_snapshots(stl_dir: Path) -> list[Path]:
    """``bench_v04_YYYYMMDDTHHMMSS.json`` snapshot 파일들을 최신순으로 반환."""
    files = sorted(
        (
            p for p in stl_dir.glob("bench_v04_*.json")
            if p.name != "bench_v04_result.json"
            and not p.stem.endswith("result")
        ),
        key=lambda p: p.stem,
        reverse=True,
    )
    return files


def _combo_key(r: dict) -> tuple[str, str, str]:
    return (str(r.get("stl", "")), str(r.get("tier", "")), str(r.get("quality", "")))


def compare_runs(prev: list[dict], curr: list[dict]) -> dict:
    """두 run 의 combo 단위 drift 계산.

    Returns:
        ``{"newly_passing": [...], "newly_failing": [...], "unchanged": [...]}``.
        각 entry 는 combo key tuple + 이전/현재 ``polyMesh_created`` / ``elapsed_s``.
    """
    prev_map = {_combo_key(r): r for r in prev}
    curr_map = {_combo_key(r): r for r in curr}
    all_keys = set(prev_map) | set(curr_map)

    newly_passing: list[dict] = []
    newly_failing: list[dict] = []
    unchanged: list[dict] = []
    for k in sorted(all_keys):
        p = prev_map.get(k)
        c = curr_map.get(k)
        entry = {
            "stl": k[0], "tier": k[1], "quality": k[2],
            "prev_pass": bool(p["polyMesh_created"]) if p else None,
            "curr_pass": bool(c["polyMesh_created"]) if c else None,
            "prev_time": float(p.get("elapsed_s", 0.0)) if p else None,
            "curr_time": float(c.get("elapsed_s", 0.0)) if c else None,
        }
        if p is None or c is None:
            # 한 쪽에만 있음 — 새로 추가 / 제거된 combo
            if c and entry["curr_pass"]:
                newly_passing.append(entry)
            elif p and entry["prev_pass"]:
                newly_failing.append(entry)  # 제거된 combo 는 "failing" 으로 간주
            else:
                unchanged.append(entry)
            continue
        if entry["prev_pass"] == entry["curr_pass"]:
            unchanged.append(entry)
        elif entry["curr_pass"]:
            newly_passing.append(entry)
        else:
            newly_failing.append(entry)

    return {
        "newly_passing": newly_passing,
        "newly_failing": newly_failing,
        "unchanged": unchanged,
    }


def _print_diff(diff: dict) -> None:
    np_ = diff["newly_passing"]
    nf = diff["newly_failing"]
    uc = diff["unchanged"]
    print(f"\n=== Diff: {len(np_)} newly passing, {len(nf)} newly failing, {len(uc)} unchanged ===")
    for section, items in (("newly_passing", np_), ("newly_failing", nf)):
        if not items:
            continue
        print(f"\n[{section}]")
        for e in items:
            prev = "—" if e["prev_pass"] is None else ("✓" if e["prev_pass"] else "✗")
            curr = "—" if e["curr_pass"] is None else ("✓" if e["curr_pass"] else "✗")
            print(f"  {e['stl']:<24s} {e['tier']:<12s} {e['quality']:<8s} {prev} → {curr}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="매트릭스 행 제한 (0 = 전부)")
    ap.add_argument("--diff", action="store_true",
                    help="실행 대신 최근 2 snapshot 의 drift 출력")
    args = ap.parse_args()

    if args.diff:
        snaps = list_snapshots(STL_DIR)
        if len(snaps) < 2:
            print(f"snapshot 이 {len(snaps)} 개뿐 — diff 불가 (≥2 필요)")
            return 1
        curr_p, prev_p = snaps[0], snaps[1]
        print(f"비교: {prev_p.name}  →  {curr_p.name}")
        prev = json.loads(prev_p.read_text(encoding="utf-8"))
        curr = json.loads(curr_p.read_text(encoding="utf-8"))
        diff = compare_runs(prev, curr)
        _print_diff(diff)
        return 0

    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="bench_v04_"))
    results: list[dict] = []
    combos = [
        (diff, stl, engine_name, mt, q)
        for diff, stl in DIFFICULTIES
        for engine_name, mt in ENGINES
        for q in QUALITIES
    ]
    if args.limit > 0:
        combos = combos[: args.limit]
    for diff, stl_name, engine_name, mt, q in combos:
        stl = STL_DIR / stl_name
        if not stl.exists():
            print(f"[SKIP] {stl_name} 없음")
            continue
        print(f"[RUN] {diff} × {engine_name} × {q}")
        res = _run_one(stl, engine_name, mt, q, tmp)
        res["difficulty"] = diff
        results.append(res)

    _print_table(results)

    snapshot, latest = save_results_timestamped(results, STL_DIR)
    print(f"\nSnapshot: {snapshot}")
    print(f"Latest:   {latest}")

    # 이전 snapshot 과 비교 (존재 시)
    snaps = list_snapshots(STL_DIR)
    if len(snaps) >= 2:
        prev = json.loads(snaps[1].read_text(encoding="utf-8"))
        diff = compare_runs(prev, results)
        _print_diff(diff)

    shutil.rmtree(tmp, ignore_errors=True)
    # 전체 성공률
    total = len(results)
    ok = sum(1 for r in results if r["polyMesh_created"])
    print(f"\n총 {total} 개 중 {ok} 개 polyMesh 생성 성공 "
          f"({100 * ok / max(total, 1):.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
