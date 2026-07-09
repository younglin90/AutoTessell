"""다중 케이스 × mesh_type 실전 품질 매트릭스 벤치.

여러 STL(난이도 스펙트럼)에 대해 웹 GUI 와 동일한 경로
(_build_run_kwargs → orchestrator.run, N/BL 포함)로 메쉬를 생성하고
skewness / non-orthogonality / negative volume / aspect ratio / min volume
등을 판정한다.

각 케이스는 **자식 프로세스**로 격리 실행 (pytetwild segfault·행 방지,
per-case 타임아웃).  결과는 JSONL 로 체크포인트.

Usage:
    python tests/bench_quality_matrix.py                # 전체 매트릭스
    python tests/bench_quality_matrix.py --only tet     # 특정 타입만
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

N_TARGET = 15000
BL_LAYERS = 2
TIMEOUT = 420  # per-case [s]

CASES: list[tuple[str, str]] = [
    ("cube",     "tests/stl/01_easy_cube.stl"),
    ("cylinder", "tests/stl/02_medium_cylinder.stl"),
    ("bracket",  "tests/stl/03_hard_bracket.stl"),
    ("torus2",   "tests/benchmarks/high_genus_dual_torus.stl"),
    # --- garbage 표면 스트레스 (쓰레기 입력 강건성) ---
    ("broken",    "tests/benchmarks/broken_sphere.stl"),
    ("sliver",    "tests/benchmarks/degenerate_faces_sliver_triangles.stl"),
    ("skewflat",  "tests/benchmarks/highly_skewed_mesh_flat_triangles.stl"),
    ("openhemi",  "tests/benchmarks/hemisphere_open.stl"),
    ("selfx",     "tests/benchmarks/self_intersecting_crossed_planes.stl"),
    ("nonmani",   "tests/benchmarks/nonmanifold_disconnected.stl"),
    ("fivesph",   "tests/benchmarks/five_disconnected_spheres.stl"),
    ("needle",    "tests/benchmarks/extreme_aspect_ratio_needle.stl"),
]
MESH_TYPES = ["tet", "hex_dominant", "poly"]

# draft 품질 기준 (strategy_planner 의 draft targets 와 동일)
LIMITS = {
    "max_non_orthogonality": 85.0,
    "max_skewness": 8.0,
    "max_aspect_ratio": 500.0,
}

_CHILD_CODE = r"""
import json, sys, tempfile, warnings
warnings.filterwarnings("ignore")
for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
from pathlib import Path
sys.path.insert(0, sys.argv[4])
from desktop.default_env import apply_default_env
apply_default_env()
from desktop.server import _build_run_kwargs
from core.pipeline.orchestrator import PipelineOrchestrator

stl, mt, n_bl = sys.argv[1], sys.argv[2], sys.argv[3]
n_target, bl = (int(x) for x in n_bl.split(","))
kwargs = _build_run_kwargs("draft", "auto", mt, 1, {"max_cells": n_target, "bl_layers": bl})
td = tempfile.mkdtemp(prefix=f"qmx_{mt}_")
import time as _t
t0 = _t.perf_counter()
res = PipelineOrchestrator().run(Path(stl), Path(td) / "case", **kwargs)
elapsed = _t.perf_counter() - t0

out = {"success": bool(res.success), "elapsed": round(elapsed, 1), "error": res.error}
try:
    tier = None
    for a in res.generator_log.execution_summary.tiers_attempted or []:
        if a.status == "success":
            tier = a.tier
            break
    out["tier"] = tier
except Exception:
    out["tier"] = None
qr = res.quality_report
if qr is not None:
    es = qr.evaluation_summary
    cm = es.checkmesh
    v = es.verdict
    out["verdict"] = v.value if hasattr(v, "value") else str(v)
    for f in ("cells", "faces", "points", "max_non_orthogonality",
              "avg_non_orthogonality", "max_skewness", "max_aspect_ratio",
              "min_face_area", "min_cell_volume", "negative_volumes",
              "severely_non_ortho_faces", "failed_checks", "mesh_ok"):
        out[f] = getattr(cm, f, None)
print("###RESULT### " + json.dumps(out))
"""


def run_case(stl: Path, mt: str) -> dict:
    cmd = [sys.executable, "-c", _CHILD_CODE, str(stl), mt,
           f"{N_TARGET},{BL_LAYERS}", str(ROOT)]
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=TIMEOUT, cwd=str(ROOT),
        )
        for line in reversed((proc.stdout or "").splitlines()):
            if line.startswith("###RESULT### "):
                return json.loads(line[len("###RESULT### "):])
        tail = ((proc.stderr or "") + (proc.stdout or ""))[-400:]
        return {"success": False, "error": f"no result (rc={proc.returncode}): {tail}",
                "elapsed": round(time.perf_counter() - t0, 1)}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"TIMEOUT {TIMEOUT}s",
                "elapsed": TIMEOUT}


def judge(r: dict) -> tuple[bool, list[str]]:
    """품질 판정 — (전체 OK 여부, 실패 사유 리스트)."""
    fails: list[str] = []
    if not r.get("success"):
        return False, [f"generation failed: {str(r.get('error'))[:120]}"]
    if r.get("verdict") not in ("PASS", "PASS_WITH_WARNINGS"):
        fails.append(f"verdict={r.get('verdict')}")
    if (r.get("negative_volumes") or 0) != 0:
        fails.append(f"negative_volumes={r['negative_volumes']}")
    mcv = r.get("min_cell_volume")
    if mcv is not None and mcv <= 0:
        fails.append(f"min_cell_volume={mcv:.3e}")
    for key, lim in LIMITS.items():
        val = r.get(key)
        if val is not None and val > lim:
            fails.append(f"{key}={val:.2f}>{lim}")
    if r.get("mesh_ok") is False:
        fails.append("mesh_ok=False")
    cells = r.get("cells") or 0
    if not (0.3 * N_TARGET <= cells <= 3.0 * N_TARGET):
        fails.append(f"cells={cells} out of [0.3N,3N]")
    return not fails, fails


def main() -> int:
    only = None
    case_filter = None
    append = "--append" in sys.argv
    for i, a in enumerate(sys.argv):
        if a == "--only" and i + 1 < len(sys.argv):
            only = sys.argv[i + 1].split(",")
        if a == "--cases" and i + 1 < len(sys.argv):
            case_filter = sys.argv[i + 1].split(",")
    types = [t for t in MESH_TYPES if only is None or t in only]
    global CASES
    if case_filter:
        CASES = [(n, p) for n, p in CASES if n in case_filter]

    jsonl = ROOT / "tests" / "bench_quality_matrix_results.jsonl"
    if not append:
        jsonl.write_text("", encoding="utf-8")
    results: list[dict] = []

    print(f"=== 품질 매트릭스: {len(CASES)} STL × {types} · N={N_TARGET} BL={BL_LAYERS} ===",
          flush=True)
    for name, rel in CASES:
        stl = ROOT / rel
        if not stl.exists():
            print(f"-- {name}: STL 없음, 건너뜀", flush=True)
            continue
        for mt in types:
            r = run_case(stl, mt)
            r.update({"case": name, "mesh_type": mt})
            ok, fails = judge(r)
            r["quality_ok"] = ok
            r["quality_fails"] = fails
            results.append(r)
            with jsonl.open("a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            mark = "OK " if ok else "BAD"
            print(
                f"[{mark}] {name:9s} {mt:12s} tier={str(r.get('tier'))[:20]:20s} "
                f"cells={r.get('cells') or 0:>6} "
                f"skew={_f(r.get('max_skewness')):>6} "
                f"nonOrtho={_f(r.get('max_non_orthogonality')):>6} "
                f"negVol={r.get('negative_volumes')!s:>4} "
                f"aspect={_f(r.get('max_aspect_ratio')):>8} "
                f"minVol={_e(r.get('min_cell_volume')):>9} "
                f"({r.get('elapsed')}s)"
                + (f"  ← {'; '.join(fails)}" if fails else ""),
                flush=True,
            )

    n_ok = sum(1 for r in results if r["quality_ok"])
    print(f"\nRESULT: {n_ok}/{len(results)} OK", flush=True)
    for r in results:
        if not r["quality_ok"]:
            print(f"  - {r['case']}/{r['mesh_type']}: {'; '.join(r['quality_fails'])}",
                  flush=True)
    return 0 if n_ok == len(results) else 1


def _f(v):  # noqa: ANN001
    return f"{v:.2f}" if isinstance(v, (int, float)) else "-"


def _e(v):  # noqa: ANN001
    return f"{v:.2e}" if isinstance(v, (int, float)) else "-"


if __name__ == "__main__":
    raise SystemExit(main())
