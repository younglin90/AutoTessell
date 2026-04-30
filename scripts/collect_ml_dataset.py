"""D1 / beta2594 — ML dataset 자동 수집 스크립트.

35 test STL 파일을 native_tet 으로 mesh 생성 → tet sample 추출 → npz 저장.
이후 D2 (train_quality_predictor) 가 이 dataset 으로 학습.

Usage:
    python3 scripts/collect_ml_dataset.py
    python3 scripts/collect_ml_dataset.py --n-samples-per-mesh 200 --output models/ml_dataset.npz

Output: models/ml_dataset.npz with keys:
    features: (N, 20) — extract_tet_features 출력.
    qualities: (N,) — Klingner mean-ratio quality (0-1).
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stl-glob", default="tests/**/*.stl",
        help="STL 파일 glob pattern (relative to repo root).",
    )
    ap.add_argument(
        "--stl-dir", default=None,
        help="대신 사용할 절대 STL 디렉터리 (override --stl-glob).",
    )
    ap.add_argument(
        "--output", default="models/ml_dataset.npz",
        help="output .npz 경로.",
    )
    ap.add_argument(
        "--n-samples-per-mesh", type=int, default=200,
        help="mesh 당 추출할 tet sample 수.",
    )
    ap.add_argument(
        "--max-meshes", type=int, default=50,
        help="처리할 최대 mesh 수.",
    )
    ap.add_argument(
        "--seed-density", type=int, default=4,
        help="native_tet seed_density.",
    )
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    out_path = repo / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.stl_dir:
        stl_files = sorted(Path(args.stl_dir).glob("*.stl"))[: args.max_meshes]
    else:
        stl_files = sorted(repo.glob(args.stl_glob))[: args.max_meshes]
    if not stl_files:
        print(f"[ERR] no STL files matched: {args.stl_glob}", file=sys.stderr)
        return 1
    print(f"[INFO] {len(stl_files)} STL files found")

    sys.path.insert(0, str(repo))
    from core.analyzer.readers.stl import read_stl
    from core.generator.native_tet.mesher import generate_native_tet
    from core.generator.native_ai.training_data import generate_dataset_from_meshes

    mesh_pts: list[np.ndarray] = []
    mesh_tets: list[np.ndarray] = []
    skipped = 0

    t_start = time.perf_counter()
    for i, stl in enumerate(stl_files):
        try:
            mesh = read_stl(str(stl))
            V = np.asarray(mesh.vertices, dtype=np.float64)
            F = np.asarray(mesh.faces, dtype=np.int64)
        except Exception as exc:
            print(f"[SKIP] {stl.name}: read failed ({exc!s:.60})")
            skipped += 1
            continue
        if V.shape[0] < 4 or F.shape[0] < 4:
            skipped += 1
            continue
        try:
            with tempfile.TemporaryDirectory() as td:
                r = generate_native_tet(
                    V, F, Path(td) / "case",
                    seed_density=args.seed_density,
                    enable_phase_a=True,
                    enable_phase_c=True,
                    enable_amips_smooth=True,
                )
                if (
                    r.success
                    and getattr(r, "tets", None) is not None
                    and getattr(r, "tet_points", None) is not None
                    and r.tets.shape[0] > 50
                ):
                    mesh_pts.append(np.asarray(r.tet_points, dtype=np.float64))
                    mesh_tets.append(np.asarray(r.tets, dtype=np.int64))
                    print(f"[OK] {i+1}/{len(stl_files)} {stl.name}: {r.tets.shape[0]} tets")
                else:
                    print(f"[FAIL] {stl.name}: native_tet success={r.success}, tets={getattr(r, 'tets', None)}")
                    skipped += 1
        except Exception as exc:
            print(f"[ERR] {stl.name}: {exc!s:.60}")
            skipped += 1

    if not mesh_pts:
        print("[ERR] no successful mesh generated", file=sys.stderr)
        return 2

    print(f"[INFO] {len(mesh_pts)} meshes successful, {skipped} skipped")
    print(f"[INFO] generating dataset → {out_path}")

    r1 = generate_dataset_from_meshes(
        str(out_path), mesh_pts, mesh_tets,
        samples_per_mesh=args.n_samples_per_mesh,
    )
    elapsed = time.perf_counter() - t_start
    if not r1.success:
        print(f"[ERR] dataset gen failed: {r1.message}", file=sys.stderr)
        return 3

    print(f"[DONE] {r1.n_samples} samples saved to {out_path}")
    print(f"       elapsed {elapsed:.1f}s, {r1.n_samples / max(elapsed, 1e-9):.1f} samples/s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
