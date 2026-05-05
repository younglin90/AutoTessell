"""Thingi10K 의 self_intersecting + non-manifold 5개에 대한 native_tet 측정.

사용:
    python3 tests/stl/bench_thingi10k_hard.py
"""
from __future__ import annotations

import json
import sys
import time
import warnings
import tempfile
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

# repo root 를 sys.path 에 추가 (tests/stl/ 하위에서 실행 시).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _pick_hard_meshes(n: int = 5) -> list[dict]:
    import thingi10k

    thingi10k.init(variant="npz")
    ds = thingi10k.dataset(
        self_intersecting=True,
        manifold=False,
        num_facets=(5000, 50000),
    )
    chosen = []
    for i, row in enumerate(ds):
        if len(chosen) >= n:
            break
        chosen.append({
            "file_id": int(row["file_id"]),
            "num_vertices": int(row["num_vertices"]),
            "num_facets": int(row["num_facets"]),
            "self_intersecting": bool(row["self_intersecting"]),
            "vertex_manifold": bool(row.get("vertex_manifold", True)),
            "edge_manifold": bool(row.get("edge_manifold", True)),
            "closed": bool(row.get("closed", False)),
            "num_components": int(row.get("num_components", 1)),
            "file_path": str(row["file_path"]),
        })
    return chosen


def _run_native_tet(V: np.ndarray, F: np.ndarray) -> dict:
    from core.generator.native_tet.mesher import generate_native_tet

    with tempfile.TemporaryDirectory() as td:
        t0 = time.perf_counter()
        try:
            r = generate_native_tet(
                V, F, Path(td) / "c", seed_density=8,
                enable_phase_a=True,
                enable_phase_b=True, local_ops_iterations=1, flip_iterations=1,
                enable_cdt_recovery=True,
                cdt_recovery_max_cycles=4, cdt_recovery_outer_iter=3,
                cdt_recovery_target_ratio=0.9,
                score_weight_area=0.5, score_weight_cdt=0.2, score_weight_mq=0.3,
                max_input_vertices=200000,
            )
        except Exception as exc:
            return {"success": False, "exc": str(exc)[:200],
                    "elapsed": time.perf_counter() - t0}
        elapsed = time.perf_counter() - t0
        if not r.success:
            return {"success": False, "message": r.message[:200],
                    "elapsed": elapsed}
        mq = float(getattr(r.quality, "mean_q", 0.0)) if r.quality else 0.0
        return {
            "success": True,
            "elapsed": elapsed,
            "n_cells": int(r.n_cells),
            "n_points": int(r.n_points),
            "grade": r.quality_grade,
            "plane_coverage": float(r.plane_coverage),
            "plane_area_coverage": float(r.plane_area_coverage),
            "cdt_ratio": float(r.cdt_ratio),
            "mean_q": mq,
        }


def main():
    print("=== Thingi10K hard mesh 5선 — self-intersecting + non-manifold ===")
    meshes = _pick_hard_meshes(5)
    if not meshes:
        print("dataset 0 — 다른 필터 필요")
        return

    import thingi10k

    rows: list[dict] = []
    for i, info in enumerate(meshes):
        print(f"\n[{i+1}/{len(meshes)}] file_id={info['file_id']} "
              f"V={info['num_vertices']} F={info['num_facets']}")
        try:
            V, F = thingi10k.load_file(info["file_path"])
            print(f"  loaded V={V.shape} F={F.shape}")
        except Exception as exc:
            print(f"  load fail: {exc}")
            rows.append({**info, "load_error": str(exc)[:200]})
            continue
        result = _run_native_tet(V.astype(np.float64), F.astype(np.int64))
        rows.append({**info, **result})
        if result["success"]:
            print(f"  → grade={result['grade']} cells={result['n_cells']} "
                  f"area={round(result['plane_area_coverage'], 3)} "
                  f"cdt={round(result['cdt_ratio'], 3)} "
                  f"mq={round(result['mean_q'], 3)} "
                  f"t={round(result['elapsed'], 1)}s")
        else:
            err = result.get("message") or result.get("exc", "")
            print(f"  → FAIL: {err[:120]}")

    out_path = Path(__file__).parent / "bench_thingi10k_hard_result.json"
    out_path.write_text(json.dumps(rows, indent=2))
    print(f"\n결과 저장: {out_path}")
    print(f"\n=== 요약 ===")
    n_success = sum(1 for r in rows if r.get("success"))
    print(f"success: {n_success}/{len(rows)}")
    grades: dict[str, int] = {}
    for r in rows:
        if r.get("success"):
            g = r.get("grade", "?")
            grades[g] = grades.get(g, 0) + 1
    print(f"grades : {grades}")


if __name__ == "__main__":
    main()
