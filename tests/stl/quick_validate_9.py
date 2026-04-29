"""C-VAL-7 / beta2406 — 빠른 9-run validator (3 mesh × {tet+BL, hex+BL, poly+BL}).

validate_30_hard_meshes.py 가 너무 느려 cycle 별 빠른 회귀 (≤ 5분).

사용:
    python3 tests/stl/quick_validate_9.py [--seed N]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.stl.validate_30_hard_meshes import (  # noqa: E402
    _gen_tet, _gen_hex, _gen_poly, _pick_hard_meshes, _run_one,
)


def main(argv: list[str]) -> int:
    n = 3
    seed = 42
    for i, a in enumerate(argv):
        if a == "--seed" and i + 1 < len(argv):
            seed = int(argv[i + 1])
        elif a == "--n" and i + 1 < len(argv):
            n = int(argv[i + 1])

    print(f"=== quick_validate_9 (n={n}, seed={seed}) ===")
    meshes = _pick_hard_meshes(n, seed=seed)

    out_rows: list[dict] = []
    t_total = time.perf_counter()
    for i, info in enumerate(meshes):
        print(f"\n[{i+1}/{len(meshes)}] file_id={info['file_id']} "
              f"V={info['num_vertices']} F={info['num_facets']}")
        for engine_name, gen_fn in [("tet", _gen_tet), ("hex", _gen_hex), ("poly", _gen_poly)]:
            r = _run_one(info, gen_fn)
            row = {"file_id": info["file_id"], "engine": engine_name, **r}
            out_rows.append(row)
            ok = "OK" if r.get("success") else "FAIL"
            elapsed = r.get("elapsed", 0)
            n_cells = r.get("n_cells", 0)
            grade = r.get("grade", "")
            integrity = "[INTEGRITY?]" if r.get("integrity_suspect") else ""
            extra = f" grade={grade}" if grade else ""
            bl_s = ""
            if "bl_success" in r:
                if r.get("bl_success"):
                    bl_s = f" +BL[prism={r.get('bl_n_prism_cells', 0)}]"
                else:
                    bl_s = f" +BL[skip:{(r.get('bl_skipped') or 'fail')[:30]}]"
            print(
                f"  {engine_name}: {ok} cells={n_cells} t={elapsed}s{extra} {integrity}{bl_s}"
                .rstrip(),
            )

    elapsed_total = time.perf_counter() - t_total
    n_pass = sum(1 for r in out_rows if r.get("success"))
    n_bl_pass = sum(1 for r in out_rows if r.get("bl_success"))
    summary = {
        "seed": seed,
        "n_meshes": n,
        "n_runs": len(out_rows),
        "n_pass": n_pass,
        "n_bl_pass": n_bl_pass,
        "elapsed_total_s": round(elapsed_total, 1),
        "rows": out_rows,
    }
    out_dir = _REPO_ROOT / "harness"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "quick_validate_9_results.json"
    out_path.write_text(json.dumps(summary, indent=2))

    print(f"\n=== 결과 ===")
    print(f"PASS: {n_pass}/{len(out_rows)}, BL: {n_bl_pass}/{len(out_rows)}")
    print(f"total elapsed: {elapsed_total:.1f}s")
    print(f"saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
