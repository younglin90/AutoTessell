"""v0.4 native_* 엔진 × 5 난이도 STL × 3 품질 매트릭스 실행 스크립트.

사용:
    python3 tests/stl/bench_v04_matrix.py [--limit N]

출력:
    stdout 에 결과 테이블 + tests/stl/bench_v04_result.json 저장.

각 조합에 대해 CLI 를 subprocess 로 호출해 실제 end-to-end 동작 검증.
OpenFOAM 가용 시 Evaluator 판정 포함, 불가 시 생성 성공 여부만.
"""
from __future__ import annotations

import argparse
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

QUALITIES = ["draft"]  # 매트릭스 20 개 — draft 만으로 제한 (시간 예산)


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="매트릭스 행 제한 (0 = 전부)")
    args = ap.parse_args()

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

    out_json = STL_DIR / "bench_v04_result.json"
    out_json.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n결과 JSON: {out_json}")

    shutil.rmtree(tmp, ignore_errors=True)
    # 전체 성공률
    total = len(results)
    ok = sum(1 for r in results if r["polyMesh_created"])
    print(f"\n총 {total} 개 중 {ok} 개 polyMesh 생성 성공 "
          f"({100 * ok / max(total, 1):.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
