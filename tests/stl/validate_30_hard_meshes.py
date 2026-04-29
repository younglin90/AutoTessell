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
    out = {
        "success": bool(r.success),
        "elapsed": round(time.perf_counter() - t0, 2),
        "n_cells": int(r.n_cells),
        "grade": r.quality_grade,
        "mean_q": float(getattr(r.quality, "mean_q", 0.0)) if r.quality else 0.0,
        # C-VAL-1 / beta2386 — integrity flag 노출 (tet 만 지원).
        "integrity_suspect": bool(getattr(r, "mesh_integrity_suspect", False)),
        "n_surface_v": int(V.shape[0]),
        # C-VAL-3 / beta2396 — input SI pre-mesh count (UUU2 결과).
        "n_self_intersect_pre": getattr(r, "n_self_intersect_pre", None),
    }
    # C-VAL-6 / beta2403 — BL pipeline 시도.
    if out["success"]:
        out.update(_try_bl_after_volume(td))
    return out


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
    out = {
        "success": bool(r.success),
        "elapsed": round(time.perf_counter() - t0, 2),
        "n_cells": int(getattr(r, "n_cells", 0)),
        "integrity_suspect": bool(getattr(r, "mesh_integrity_suspect", False)),
        "n_surface_v": int(V.shape[0]),
    }
    if out["success"]:
        out.update(_try_bl_after_volume(td))
    return out


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
    out = {
        "success": bool(r.success),
        "elapsed": round(time.perf_counter() - t0, 2),
        "n_cells": int(getattr(r, "n_cells", 0)),
        "integrity_suspect": bool(getattr(r, "mesh_integrity_suspect", False)),
        "n_surface_v": int(V.shape[0]),
    }
    if out["success"]:
        out.update(_try_bl_after_volume(td))
    return out


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


def _try_bl_after_volume(td: Path) -> dict:
    """C-VAL-6 / beta2403 — volume mesh 가 case_dir 에 있으면 BL 추가.

    success → {"bl_success": True, "bl_n_prism_cells": N, ...}.
    skip (BL 입력 invalid) → {"bl_success": False, "bl_skipped": "reason"}.
    """
    import time as _t
    try:
        from core.layers.native_bl import BLConfig, generate_native_bl
    except Exception as exc:
        return {"bl_success": False, "bl_skipped": f"import_fail:{str(exc)[:60]}"}
    case_dir = td / "c"
    if not (case_dir / "constant" / "polyMesh").exists():
        return {"bl_success": False, "bl_skipped": "no_polymesh"}
    t0 = _t.perf_counter()
    try:
        cfg = BLConfig(num_layers=3, first_thickness=0.0, growth_ratio=1.2)
        r = generate_native_bl(case_dir, config=cfg, engine_tag="validator")
        return {
            "bl_success": bool(r.success),
            "bl_elapsed": round(_t.perf_counter() - t0, 2),
            "bl_n_prism_cells": int(getattr(r, "n_prism_cells", 0)),
            "bl_n_wall_faces": int(getattr(r, "n_wall_faces", 0)),
            "bl_max_diff_rel": float(getattr(r, "wall_preserve_max_diff_rel", 0.0)),
        }
    except Exception as exc:
        return {
            "bl_success": False,
            "bl_elapsed": round(_t.perf_counter() - t0, 2),
            "bl_skipped": f"exc:{str(exc)[:80]}",
        }


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
            grade = r.get("grade", "")
            integrity = "[INTEGRITY?]" if r.get("integrity_suspect") else ""
            extra = f" grade={grade}" if grade else ""
            si_pre = r.get("n_self_intersect_pre")
            si_s = f" si={si_pre}" if isinstance(si_pre, int) and si_pre > 0 else ""
            err = r.get("exc") or r.get("load_error") or r.get("message")
            err_s = f" err={str(err)[:80]}" if err and not r.get("success") else ""
            # C-VAL-6 / beta2403 — BL 결과 표시.
            if "bl_success" in r:
                if r.get("bl_success"):
                    bl_s = f" +BL[prism={r.get('bl_n_prism_cells', 0)}]"
                else:
                    bl_s = f" +BL[skip:{(r.get('bl_skipped') or 'fail')[:40]}]"
            else:
                bl_s = ""
            print(
                f"  {engine_name}: {ok} cells={n_cells} t={elapsed}s{extra}{si_s} {integrity}{bl_s}{err_s}"
                .rstrip(),
            )

    n_pass = sum(1 for r in out_rows if r.get("success"))
    n_integrity_suspect = sum(1 for r in out_rows if r.get("integrity_suspect"))
    grade_counts: dict[str, int] = {}
    for r in out_rows:
        if r.get("grade"):
            grade_counts[r["grade"]] = grade_counts.get(r["grade"], 0) + 1
    # C-VAL-4 / beta2398 — tet 평균 cell count + 평균 mean_q 집계.
    tet_rows = [r for r in out_rows if r.get("engine") == "tet" and r.get("success")]
    avg_tet_cells = (
        sum(r.get("n_cells", 0) for r in tet_rows) / len(tet_rows)
        if tet_rows else 0.0
    )
    avg_tet_mq = (
        sum(r.get("mean_q", 0.0) for r in tet_rows) / len(tet_rows)
        if tet_rows else 0.0
    )
    summary = {
        "seed": seed,
        "n_meshes": n_meshes,
        "n_runs": len(out_rows),
        "n_pass": n_pass,
        "n_integrity_suspect": n_integrity_suspect,
        "grade_counts": grade_counts,
        "avg_tet_cells": round(avg_tet_cells, 1),
        "avg_tet_mq": round(avg_tet_mq, 4),
        "pass_rate": round(n_pass / max(1, len(out_rows)), 3),
        "rows": out_rows,
    }

    out_dir = _REPO_ROOT / "harness"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "validate_30_results.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\n=== 결과 ===")
    print(f"PASS: {n_pass}/{len(out_rows)} ({summary['pass_rate']*100:.1f}%)")
    if n_integrity_suspect > 0:
        print(f"INTEGRITY_SUSPECT (tet): {n_integrity_suspect}/{len(out_rows)}")
    if grade_counts:
        print(f"GRADES: {grade_counts}")
    print(f"AVG_TET cells={avg_tet_cells:.0f} mq={avg_tet_mq:.4f}")
    print(f"saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
