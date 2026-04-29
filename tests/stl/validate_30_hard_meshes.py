"""고도화 루프 검증 — 10개 어려운 thingi10k mesh × {tet, hex, poly} + BL = 30 runs.

자동 생성된 ./harness/validate_30_results.json 을 다음 cycle 에서 비교.

사용:
    python3 tests/stl/validate_30_hard_meshes.py [--seed N] [--n-meshes M]
"""
from __future__ import annotations

import json
import random
import sys
import time
import tempfile
import traceback
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _pick_hard_meshes(n: int = 10, seed: int = 42) -> list[dict]:
    import thingi10k

    thingi10k.init(variant="npz")
    # self-intersecting OR non-manifold + 적당한 face 수.
    ds = list(thingi10k.dataset(
        self_intersecting=True,
        manifold=False,
        num_facets=(2000, 30000),
    ))
    rng = random.Random(seed)
    rng.shuffle(ds)
    chosen = []
    for row in ds:
        if len(chosen) >= n:
            break
        chosen.append({
            "file_id": int(row["file_id"]),
            "num_vertices": int(row["num_vertices"]),
            "num_facets": int(row["num_facets"]),
            "file_path": str(row["file_path"]),
        })
    return chosen


def _filter_to_sig(fn, params: dict) -> dict:
    """Drop kwargs that fn does not accept (HARNESS_PARAMS 와 sig 불일치 흡수)."""
    import inspect
    sig = inspect.signature(fn)
    return {k: v for k, v in params.items() if k in sig.parameters}


def _gen_tet(V, F, td: Path) -> dict:
    """Tet via fine-quality HARNESS_PARAMS (실 fine path 검증)."""
    from core.generator.native_tet.mesher import generate_native_tet
    from core.generator._tier_native_common import HARNESS_PARAMS
    fine_p = _filter_to_sig(
        generate_native_tet, HARNESS_PARAMS["tier_native_tet"]["fine"],
    )
    t0 = time.perf_counter()
    try:
        r = generate_native_tet(V, F, td / "c", **fine_p)
    except Exception as exc:
        return {"success": False, "elapsed": time.perf_counter() - t0,
                "exc": str(exc)[:160]}
    return {
        "success": bool(r.success),
        "elapsed": round(time.perf_counter() - t0, 2),
        "n_cells": int(r.n_cells),
        "grade": r.quality_grade,
        "mean_q": float(getattr(r.quality, "mean_q", 0.0)) if r.quality else 0.0,
    }


def _gen_hex(V, F, td: Path) -> dict:
    """Hex via fine-quality HARNESS_PARAMS."""
    from core.generator.native_hex.mesher import generate_native_hex
    from core.generator._tier_native_common import HARNESS_PARAMS
    fine_p = _filter_to_sig(
        generate_native_hex, HARNESS_PARAMS["tier_native_hex"]["fine"],
    )
    t0 = time.perf_counter()
    try:
        r = generate_native_hex(V, F, td / "c", **fine_p)
    except Exception as exc:
        return {"success": False, "elapsed": time.perf_counter() - t0,
                "exc": str(exc)[:160]}
    return {
        "success": bool(r.success),
        "elapsed": round(time.perf_counter() - t0, 2),
        "n_cells": int(getattr(r, "n_cells", 0)),
    }


def _gen_poly(V, F, td: Path) -> dict:
    """Poly via fine-quality HARNESS_PARAMS."""
    from core.generator.native_poly.voronoi import generate_native_poly_voronoi
    from core.generator._tier_native_common import HARNESS_PARAMS
    fine_p = _filter_to_sig(
        generate_native_poly_voronoi, HARNESS_PARAMS["tier_native_poly"]["fine"],
    )
    t0 = time.perf_counter()
    try:
        r = generate_native_poly_voronoi(V, F, td / "c", **fine_p)
    except Exception as exc:
        return {"success": False, "elapsed": time.perf_counter() - t0,
                "exc": str(exc)[:160]}
    return {
        "success": bool(r.success),
        "elapsed": round(time.perf_counter() - t0, 2),
        "n_cells": int(getattr(r, "n_cells", 0)),
    }


def _run_one(info: dict, gen_fn) -> dict:
    import thingi10k
    try:
        V, F = thingi10k.load_file(info["file_path"])
    except Exception as exc:
        return {"success": False, "load_error": str(exc)[:120]}
    with tempfile.TemporaryDirectory() as td:
        try:
            return gen_fn(np.asarray(V, dtype=np.float64),
                          np.asarray(F, dtype=np.int64), Path(td))
        except Exception:
            return {"success": False, "exc": traceback.format_exc()[:200]}


def main(argv: list[str]) -> int:
    n_meshes = 10
    seed = int(time.time()) & 0xFFFF
    for i, a in enumerate(argv):
        if a == "--seed" and i + 1 < len(argv):
            seed = int(argv[i + 1])
        elif a == "--n-meshes" and i + 1 < len(argv):
            n_meshes = int(argv[i + 1])

    print(f"=== validate_30 (n_meshes={n_meshes}, seed={seed}) ===")
    meshes = _pick_hard_meshes(n_meshes, seed=seed)

    out_rows: list[dict] = []
    for i, info in enumerate(meshes):
        print(f"\n[{i+1}/{len(meshes)}] file_id={info['file_id']} "
              f"V={info['num_vertices']} F={info['num_facets']}")
        for engine_name, gen_fn in [("tet", _gen_tet), ("hex", _gen_hex), ("poly", _gen_poly)]:
            r = _run_one(info, gen_fn)
            row = {
                "file_id": info["file_id"], "engine": engine_name,
                **{k: v for k, v in info.items() if k != "file_path"},
                **r,
            }
            out_rows.append(row)
            ok = "OK" if r.get("success") else "FAIL"
            elapsed = r.get("elapsed", 0)
            n_cells = r.get("n_cells", 0)
            print(f"  {engine_name}: {ok} cells={n_cells} t={elapsed}s")

    n_pass = sum(1 for r in out_rows if r.get("success"))
    summary = {
        "seed": seed,
        "n_meshes": n_meshes,
        "n_runs": len(out_rows),
        "n_pass": n_pass,
        "pass_rate": round(n_pass / max(1, len(out_rows)), 3),
        "rows": out_rows,
    }

    out_dir = _REPO_ROOT / "harness"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "validate_30_results.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\n=== 결과 ===")
    print(f"PASS: {n_pass}/{len(out_rows)} ({summary['pass_rate']*100:.1f}%)")
    print(f"saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
