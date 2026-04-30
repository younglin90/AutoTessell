"""D5 / beta2596 — BL collision dataset 자동 수집.

STL → native_tet → wall vertex/face 추출 → bl_collision_features → npz.
이후 D6 (train_bl_collision_predictor) 가 학습.

Usage:
    python3 scripts/collect_bl_dataset.py
    python3 scripts/collect_bl_dataset.py --stl-dir /tmp/ml_train_stls

Output: models/bl_dataset.npz with keys: features (N, 12), gaps (N,).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl-dir", default="/tmp/ml_train_stls")
    ap.add_argument("--output", default="models/bl_dataset.npz")
    ap.add_argument("--max-meshes", type=int, default=20)
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))

    from core.analyzer.readers.stl import read_stl
    from core.generator.native_ai.bl_collision_data import generate_bl_collision_dataset

    stl_files = sorted(Path(args.stl_dir).glob("*.stl"))[: args.max_meshes]
    if not stl_files:
        print(f"[ERR] no STL in {args.stl_dir}", file=sys.stderr)
        return 1
    print(f"[INFO] {len(stl_files)} STL files")

    points_list: list[np.ndarray] = []
    wall_v_list: list[np.ndarray] = []
    wall_fv_list: list[np.ndarray] = []
    for stl in stl_files:
        try:
            mesh = read_stl(str(stl))
            V = np.asarray(mesh.vertices, dtype=np.float64)
            F = np.asarray(mesh.faces, dtype=np.int64)
        except Exception as exc:
            print(f"[SKIP] {stl.name}: {exc!s:.60}")
            continue
        if V.shape[0] < 4 or F.shape[0] < 4:
            continue
        # surface mesh = wall (all surface vertices/faces).
        wall_v = np.arange(V.shape[0], dtype=np.int64)
        wall_fv = F.astype(np.int64)
        points_list.append(V)
        wall_v_list.append(wall_v)
        wall_fv_list.append(wall_fv)
        print(f"[OK] {stl.name}: V={V.shape[0]}, F={F.shape[0]}")

    if not points_list:
        print("[ERR] no usable mesh", file=sys.stderr)
        return 2

    out = repo / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    r = generate_bl_collision_dataset(
        str(out), points_list, wall_v_list, wall_fv_list,
    )
    if not r.success:
        print(f"[ERR] dataset gen: {r.message}", file=sys.stderr)
        return 3
    print(f"[DONE] {r.n_samples} BL collision samples → {out}")
    print(f"       elapsed {r.elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
