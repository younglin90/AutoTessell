"""native_tet 만 sequential bench (P4-C pytetwild fallback 활성).

beta2240 — P4-D 의 worker fork-segfault 회피용 별도 script.
4 tier × 5 mesh = 20 measurements × tet+BL.
P4-C ON (env AUTO_TESSELL_P4C_PYTETWILD=1).
worker pool 안 씀 (sequential) → pytetwild fork 충돌 회피.
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
import tempfile
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# P4-C 활성 (main process — fork 안 함, segfault 위험 X).
os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "1"

from tests.stl.bench_difficulty_tiers import _select_meshes, _try_bl  # noqa: E402


def _run_tet(V: np.ndarray, F: np.ndarray) -> dict:
    out: dict = {"engine": "tet", "with_bl": True}
    with tempfile.TemporaryDirectory() as td:
        case = Path(td) / "c"
        t0 = time.perf_counter()
        try:
            from core.generator.native_tet.mesher import generate_native_tet
            r = generate_native_tet(
                V, F, case, seed_density=8,
                enable_phase_a=True, enable_phase_b=False,
                enable_phase_c=True, enable_amips_smooth=True,
            )
            out["success"] = bool(r.success)
            out["n_cells"] = int(getattr(r, "n_cells", 0))
            out["grade"] = str(getattr(r, "quality_grade", "?"))
            _q = getattr(r, "quality", None)
            out["mq"] = float(getattr(_q, "mean_q", -1.0)) if _q else -1.0
            if not r.success:
                out["message"] = str(getattr(r, "message", ""))[:120]
            out["elapsed"] = round(time.perf_counter() - t0, 2)
            if out.get("success"):
                bl = _try_bl(case, n_layers=3, engine_tag="tet")
                out.update(bl)
        except Exception as exc:
            out["success"] = False
            out["exc"] = str(exc)[:200]
            out["elapsed"] = round(time.perf_counter() - t0, 2)
    return out


def main():
    print("=== native_tet P4-C sequential bench (4 tier × 5 mesh + BL) ===\n", flush=True)
    tiers = _select_meshes()
    all_meshes = []
    for tier_name, ms in tiers.items():
        all_meshes.extend(ms)
    print(f"total {len(all_meshes)} mesh, P4-C={os.environ.get('AUTO_TESSELL_P4C_PYTETWILD')}\n",
          flush=True)

    import thingi10k as _t10k
    rows = []
    t_start = time.perf_counter()
    for i, info in enumerate(all_meshes):
        V, F = _t10k.load_file(info["file_path"])
        V = V.astype(np.float64); F = F.astype(np.int64)
        r = _run_tet(V, F)
        row = {**info, **r}
        rows.append(row)
        tag = "tet+BL"
        if r.get("success"):
            parts = [
                f"grade={r.get('grade','?')}",
                f"cells={r.get('n_cells','-')}",
                f"mq={round(r.get('mq', -1), 3)}",
                f"t={r.get('elapsed','-')}s",
            ]
            if r.get("bl_success"):
                parts.append(f"BL=OK p={r.get('bl_n_prism_cells','?')}")
            elif "bl_success" in r:
                parts.append("BL=FAIL")
            print(f"  [{i+1:2}/{len(all_meshes)}] [{info['tier']:8}] "
                  f"fid={info['file_id']:8} {tag}: " + " ".join(parts),
                  flush=True)
        else:
            msg = r.get("message") or r.get("exc") or "fail"
            print(f"  [{i+1:2}/{len(all_meshes)}] [{info['tier']:8}] "
                  f"fid={info['file_id']:8} {tag}: FAIL {msg[:80]}",
                  flush=True)

    elapsed = round(time.perf_counter() - t_start, 1)
    print(f"\ntotal time: {elapsed}s ({elapsed/60:.1f}min)\n", flush=True)

    print("=== Tier × Engine 합격 표 (tet, sequential P4-C) ===\n", flush=True)
    for tier in ["easy", "medium", "hard", "extreme"]:
        tier_rows = [r for r in rows if r.get("tier") == tier]
        n_total = len(tier_rows)
        n_ok = sum(1 for r in tier_rows if r.get("success"))
        n_a = sum(1 for r in tier_rows if r.get("grade") == "A")
        n_b = sum(1 for r in tier_rows if r.get("grade") == "B")
        n_bl = sum(1 for r in tier_rows if r.get("bl_success"))
        n_p4c = sum(1 for r in tier_rows if r.get("grade") in ("A", "B") and r.get("success"))
        print(f"  {tier:8} | OK={n_ok}/{n_total} A={n_a}/5 B={n_b}/5 | BL OK={n_bl}/5",
              flush=True)

    out_path = Path(__file__).parent / "bench_tet_p4c_result.json"
    out_path.write_text(json.dumps(rows, default=str, ensure_ascii=False, indent=1))
    print(f"\n결과 저장: {out_path}", flush=True)


if __name__ == "__main__":
    main()
