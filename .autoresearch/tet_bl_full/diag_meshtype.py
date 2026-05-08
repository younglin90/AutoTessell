"""4 fails 에 대해 mesh_type 별 PASS 가능성 진단."""
from __future__ import annotations
import os
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")
os.environ.setdefault("AUTO_TESSELL_WILDMESH_USE_CACHED", "1")
import sys, json, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 4 잔여 fails
FAILS = [
    "hard_100029.stl",
    "extreme_1017013.stl",
    "extreme_1017014.stl",
    "extreme_102308.stl",
]

# 시도할 mesh_type × tier 조합
TRIES = [
    # (mesh_type, tier_hint, quality)
    ("hex_dominant", "tier15_cfmesh", "draft"),
    ("hex_dominant", "tier1_snappy", "draft"),
    ("poly", "tier_voro_poly", "draft"),
]


def run_one(stl: Path, mesh_type: str, tier: str, ql: str, n_layers: int, timeout: int = 240) -> dict:
    cmd = [sys.executable, "-c", f'''
import os, sys, json, time, tempfile
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")
os.environ.setdefault("AUTO_TESSELL_WILDMESH_USE_CACHED", "1")
sys.path.insert(0, "{ROOT}")
from pathlib import Path
from core.pipeline.orchestrator import PipelineOrchestrator
out = {{"stl": "{stl.name}", "mesh_type": "{mesh_type}", "tier": "{tier}", "ok": False, "verdict": "ERROR", "n_cells": 0, "max_skew": 0.0, "max_non_ortho": 0.0, "elapsed": 0.0, "err": ""}}
t0 = time.time()
try:
    with tempfile.TemporaryDirectory(prefix="ver_") as td:
        case = Path(td) / "case"
        tsp = {{"boundary_layers_enabled": True, "cfmesh_bl_n_layers": {n_layers}, "cfmesh_bl_thickness_ratio": 1.2}}
        res = PipelineOrchestrator().run(
            input_path=Path("{stl}"), output_dir=case,
            mesh_type="{mesh_type}", quality_level="{ql}",
            tier_hint="{tier}", write_of_case=False, tier_specific_params=tsp,
        )
        qr = getattr(res, "quality_report", None)
        es = getattr(qr, "evaluation_summary", None) if qr else None
        cm = getattr(es, "checkmesh", None) if es else None
        v = getattr(es, "verdict", None) if es else None
        out["verdict"] = str(getattr(v, "value", v)).upper() if v else "UNKNOWN"
        if cm is not None:
            out["n_cells"] = int(getattr(cm, "cells", 0) or 0)
            out["max_skew"] = float(getattr(cm, "max_skewness", 0.0) or 0.0)
            out["max_non_ortho"] = float(getattr(cm, "max_non_orthogonality", 0.0) or 0.0)
        out["ok"] = (out["verdict"] == "PASS")
except Exception as exc:
    out["err"] = f"{{type(exc).__name__}}: {{exc}}"[:200]
out["elapsed"] = round(time.time() - t0, 1)
print(json.dumps(out))
''']
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(ROOT))
        if proc.returncode != 0:
            return {"stl": stl.name, "mesh_type": mesh_type, "tier": tier, "ok": False, "verdict": "CRASH", "err": f"rc={proc.returncode}"[:80], "elapsed": timeout}
        for ln in reversed(proc.stdout.strip().splitlines()):
            ln = ln.strip()
            if ln.startswith("{") and ln.endswith("}"):
                try:
                    return json.loads(ln)
                except json.JSONDecodeError:
                    continue
        return {"stl": stl.name, "mesh_type": mesh_type, "tier": tier, "ok": False, "verdict": "NO_JSON", "err": "no_output", "elapsed": timeout}
    except subprocess.TimeoutExpired:
        return {"stl": stl.name, "mesh_type": mesh_type, "tier": tier, "ok": False, "verdict": "TIMEOUT", "err": f"timeout_{timeout}s", "elapsed": timeout}


def main() -> int:
    n_layers = 3
    print(f"{'STL':<28} {'mesh_type':<14} {'tier':<18} {'verdict':<8} {'cells':<7} {'skew':<6} {'t':<5}")
    print("-" * 80)
    results = []
    for stl_name in FAILS:
        stl = ROOT / "tests" / "stl" / "thingi10k_bench20" / stl_name
        if not stl.exists():
            print(f"{stl_name}: missing"); continue
        for mt, tier, ql in TRIES:
            r = run_one(stl, mt, tier, ql, n_layers)
            results.append(r)
            print(f"{r['stl'][:27]:<28} {r['mesh_type']:<14} {r['tier']:<18} "
                  f"{r['verdict'][:7]:<8} {r.get('n_cells',0):<7} "
                  f"{r.get('max_skew',0):<6.1f} {r.get('elapsed',0):<5.1f}"
                  + (f" | {r['err'][:50]}" if r.get('err') else ""))

    out_file = Path(__file__).parent / "meshtype_diag.json"
    out_file.write_text(json.dumps({"results": results}, indent=2))
    print(f"\nwrote {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
