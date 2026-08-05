"""D8 / beta2600 — ML 적용 vs 미적용 mesh quality 비교.

같은 STL 을 두 번 mesh:
  1. baseline: 모든 ML/env flag OFF (default 거동).
  2. ml: AUTO_TESSELL_ML_SMOOTH_MODEL + AUTO_TESSELL_BL_PREDICT_MODEL +
        AUTO_TESSELL_CVT3D_QUALITY_WEIGHT + AUTO_TESSELL_LCR_AUTO_REDUCE 모두 ON.

결과: 두 mesh 의 grade/min_q/mean_q 비교 표.

Usage:
    python3 scripts/verify_ml_effect.py
    python3 scripts/verify_ml_effect.py --stl tests/stl/03_hard_bracket.stl
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


def run_mesh(stl_path: Path, env_overrides: dict[str, str]) -> dict:
    """run native_tet on stl with env overrides; return summary dict."""
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))
    from core.analyzer.readers.stl import read_stl
    from core.generator.native_tet.mesher import generate_native_tet
    from core.generator.native_tet.quality import tet_shape_quality

    # apply env.
    saved_env: dict[str, str | None] = {}
    for k, v in env_overrides.items():
        saved_env[k] = os.environ.get(k)
        os.environ[k] = v

    try:
        mesh = read_stl(str(stl_path))
        V = np.asarray(mesh.vertices, dtype=np.float64)
        F = np.asarray(mesh.faces, dtype=np.int64)
        with tempfile.TemporaryDirectory() as td:
            r = generate_native_tet(
                V, F, Path(td) / "case",
                seed_density=4,
                enable_phase_a=True, enable_phase_c=True,
                enable_amips_smooth=True,
            )
        if r.success and r.tets is not None and r.tet_points is not None and r.tets.shape[0] > 0:
            q = tet_shape_quality(np.asarray(r.tet_points), np.asarray(r.tets))
            return {
                "ok": True,
                "n_cells": int(r.tets.shape[0]),
                "min_q": float(q.min()),
                "mean_q": float(q.mean()),
                "p5": float(np.percentile(q, 5)),
                "elapsed": float(r.elapsed_s) if hasattr(r, "elapsed_s") else 0.0,
                "grade": getattr(r, "quality_grade", "?"),
            }
        return {"ok": False, "msg": getattr(r, "message", "fail")[:80]}
    finally:
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl", default="tests/stl/03_hard_bracket.stl")
    ap.add_argument("--ml-model", default="assets/models/ml_smooth_model.pt")
    ap.add_argument("--bl-model", default="assets/models/bl_predictor.pt")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    stl = repo / args.stl
    if not stl.exists():
        print(f"[ERR] STL not found: {stl}", file=sys.stderr)
        return 1

    print(f"[INFO] STL: {stl.relative_to(repo)}")

    # baseline: ML OFF.
    print(f"\n[1/2] baseline (ML OFF)")
    r_base = run_mesh(stl, {
        "AUTO_TESSELL_CVT3D_QUALITY_WEIGHT": "0",
        "AUTO_TESSELL_LCR_AUTO_REDUCE": "0",
    })

    # ML on path.
    ml_path = str((repo / args.ml_model).absolute())
    bl_path = str((repo / args.bl_model).absolute())
    ml_env = {
        "AUTO_TESSELL_CVT3D_QUALITY_WEIGHT": "1",
    }
    if Path(ml_path).exists():
        ml_env["AUTO_TESSELL_ML_SMOOTH_MODEL"] = ml_path
        print(f"[INFO] ML model: {ml_path}")
    else:
        print(f"[WARN] ML model not found: {ml_path}")
    if Path(bl_path).exists():
        ml_env["AUTO_TESSELL_BL_PREDICT_MODEL"] = bl_path
        print(f"[INFO] BL model: {bl_path}")

    print(f"\n[2/2] ml-on (CVT3D_QWEIGHT + ML_SMOOTH + BL_PREDICT)")
    r_ml = run_mesh(stl, ml_env)

    # 비교 표.
    print(f"\n{'='*64}")
    print(f"{'metric':<15s} {'baseline':>12s} {'ml-on':>12s} {'delta':>12s}")
    print(f"{'-'*64}")
    if r_base.get("ok") and r_ml.get("ok"):
        for k in ("n_cells", "min_q", "mean_q", "p5"):
            b = r_base[k]
            m = r_ml[k]
            d = m - b
            if k == "n_cells":
                print(f"{k:<15s} {b:>12d} {m:>12d} {d:>+12d}")
            else:
                print(f"{k:<15s} {b:>12.4f} {m:>12.4f} {d:>+12.4f}")
        print(f"{'grade':<15s} {r_base['grade']:>12s} {r_ml['grade']:>12s}")
    else:
        print(f"baseline ok={r_base.get('ok')}, ml-on ok={r_ml.get('ok')}")
        if not r_base.get("ok"):
            print(f"  baseline msg: {r_base.get('msg', '')}")
        if not r_ml.get("ok"):
            print(f"  ml-on msg: {r_ml.get('msg', '')}")
    print(f"{'='*64}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
