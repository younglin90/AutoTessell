"""Thingi10K hard mesh 5선 × 3 native engine × BL on/off.

D (beta1760) — ProcessPoolExecutor 병렬화 + per-cell timeout.

각 측정 (mesh × engine × BL) 을 독립 worker process 에서 실행.
N_workers=4 default. 각 cell 60s timeout 으로 hang 방지.
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# worker functions (top-level — pickleable)
# ---------------------------------------------------------------------------

def _try_bl(case_dir, n_layers: int = 3, engine_tag: str = "generic") -> dict:
    try:
        from core.layers.native_bl import generate_native_bl, BLConfig
        cfg = BLConfig(
            num_layers=int(n_layers),
            growth_ratio=1.2,
            first_thickness=0.001,
            collision_safety=True,
            feature_lock=True,
        )
        r = generate_native_bl(case_dir, cfg, engine_tag=engine_tag)
        return {
            "bl_success": bool(r.success),
            "bl_n_prism_cells": int(r.n_prism_cells),
            "bl_n_wall_faces": int(r.n_wall_faces),
            "bl_total_thickness": float(r.total_thickness),
            "bl_elapsed": float(r.elapsed),
            "bl_message": str(r.message)[:120],
        }
    except Exception as exc:
        return {"bl_success": False, "bl_exc": str(exc)[:120]}


def _worker_run(payload: tuple) -> dict:
    """단일 (V, F, engine, with_bl) 측정 — ProcessPool worker.

    main 에서 V/F 미리 로드해 numpy bytes 로 전달. worker 에서 thingi10k
    init 안 함 (process 죽는 원인).
    """
    V_bytes, V_shape, F_bytes, F_shape, engine, with_bl = payload
    sys.path.insert(0, str(_REPO_ROOT))
    import warnings as _w
    _w.filterwarnings("ignore")

    V = np.frombuffer(V_bytes, dtype=np.float64).reshape(V_shape)
    F = np.frombuffer(F_bytes, dtype=np.int64).reshape(F_shape)

    out: dict = {"engine": engine, "with_bl": with_bl}

    with tempfile.TemporaryDirectory() as td:
        case = Path(td) / "c"
        t0 = time.perf_counter()

        try:
            if engine == "tet":
                from core.generator.native_tet.mesher import generate_native_tet
                r = generate_native_tet(
                    V, F, case, seed_density=8,
                    enable_phase_a=True, enable_phase_b=False,
                    enable_cdt_recovery=False,
                    max_input_vertices=200000,
                )
                if r.success:
                    out.update({
                        "success": True,
                        "n_cells": int(r.n_cells),
                        "grade": r.quality_grade,
                        "plane_area": float(r.plane_area_coverage),
                        "cdt": float(r.cdt_ratio),
                        "mq": float(getattr(r.quality, "mean_q", 0.0)) if r.quality else 0.0,
                    })
                else:
                    out["success"] = False
                    out["message"] = r.message[:150]

            elif engine == "hex":
                from core.generator.native_hex.mesher import generate_native_hex
                r = generate_native_hex(
                    V, F, case, seed_density=12,
                    snap_boundary=True, snap_iterations=2,
                    max_cells_per_axis=40,
                )
                if r.success:
                    out.update({
                        "success": True,
                        "n_cells": int(r.n_cells),
                        "grade": r.quality_grade,
                        "max_no_deg": float(r.max_non_orthogonality_deg),
                        "max_skew": float(r.max_skewness),
                    })
                else:
                    out["success"] = False
                    out["message"] = r.message[:150]

            elif engine == "poly":
                from core.generator.native_poly.voronoi import generate_native_poly_voronoi
                r = generate_native_poly_voronoi(
                    V, F, case, seed_density=10, auto_escalate=True,
                )
                if r.success:
                    out.update({
                        "success": True,
                        "n_cells": int(r.n_cells),
                        "grade": r.quality_grade,
                        "max_no_deg": float(r.max_non_orthogonality_deg),
                        "max_skew": float(r.max_skewness),
                        "fpc": float(r.avg_faces_per_cell),
                    })
                else:
                    out["success"] = False
                    out["message"] = r.message[:150]

            else:
                out["success"] = False
                out["message"] = f"unknown engine {engine}"

            out["elapsed"] = round(time.perf_counter() - t0, 2)

            if with_bl and out.get("success"):
                out.update(_try_bl(case, n_layers=2 if engine == "tet" else 3,
                                   engine_tag=engine))

        except Exception as exc:
            out["success"] = False
            out["exc"] = str(exc)[:150]
            out["elapsed"] = round(time.perf_counter() - t0, 2)

    return out


def _pick_hard(n: int = 5) -> list[dict]:
    """beta1800 — 측정 가능한 크기 (≤ 3000 face) 의 hard mesh 선별.

    Thingi10K 의 self-intersecting + non-manifold mesh 중 face <= 3000
    인 것만 → bench 가 합리적 시간 안에 끝나도록.
    """
    import thingi10k
    thingi10k.init(variant="npz")
    ds = thingi10k.dataset(
        self_intersecting=True, manifold=False,
        num_facets=(500, 3000),
    )
    out = []
    for i, row in enumerate(ds):
        if len(out) >= n:
            break
        out.append({
            "file_id": int(row["file_id"]),
            "num_vertices": int(row["num_vertices"]),
            "num_facets": int(row["num_facets"]),
            "num_components": int(row.get("num_components", 1)),
            "closed": bool(row.get("closed", False)),
            "file_path": str(row["file_path"]),
        })
    return out


def main():
    print("=== Thingi10K hard 5 × 3 engines × BL (parallel) ===\n", flush=True)
    meshes = _pick_hard(5)
    if not meshes:
        print("dataset 0")
        return

    for i, info in enumerate(meshes):
        print(f"  [{i+1}/5] file_id={info['file_id']} V={info['num_vertices']} "
              f"F={info['num_facets']} comps={info['num_components']} "
              f"closed={info['closed']}", flush=True)
    print(flush=True)

    # main 에서 V/F 미리 로드 (worker 에서 thingi10k init 호출 시 segfault).
    import thingi10k as _t10k
    loaded: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for info in meshes:
        V, F = _t10k.load_file(info["file_path"])
        loaded[info["file_id"]] = (
            V.astype(np.float64), F.astype(np.int64),
        )

    # 30 jobs.
    jobs = []
    for info in meshes:
        V, F = loaded[info["file_id"]]
        V_bytes = V.tobytes(); V_shape = V.shape
        F_bytes = F.tobytes(); F_shape = F.shape
        for engine in ("tet", "hex", "poly"):
            for bl in (False, True):
                jobs.append((info, engine, bl,
                             (V_bytes, V_shape, F_bytes, F_shape, engine, bl)))

    n_workers = min(4, max(1, (os.cpu_count() or 1) // 2))
    per_cell_timeout = 90.0  # 60s 보다 약간 여유.
    print(f"workers={n_workers} per_cell_timeout={per_cell_timeout}s "
          f"jobs={len(jobs)}", flush=True)

    rows: list[dict] = []
    t_start = time.perf_counter()

    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        future_map = {}
        for (info, engine, bl, payload) in jobs:
            fut = pool.submit(_worker_run, payload)
            future_map[fut] = (info, engine, bl)

        for fut in as_completed(future_map.keys(), timeout=None):
            info, engine, bl = future_map[fut]
            tag = f"{engine}{'+BL' if bl else ''}"
            try:
                r = fut.result(timeout=per_cell_timeout)
            except FuturesTimeout:
                r = {"engine": engine, "with_bl": bl, "success": False,
                     "timeout": True, "elapsed": per_cell_timeout}
            except Exception as exc:
                r = {"engine": engine, "with_bl": bl, "success": False,
                     "exc": str(exc)[:120]}
            rows.append({**info, **r})

            if r.get("success"):
                parts = [f"grade={r.get('grade', '?')}",
                         f"cells={r.get('n_cells', '-')}",
                         f"t={r.get('elapsed', '-')}s"]
                if "max_no_deg" in r:
                    parts.append(f"no={round(r['max_no_deg'], 1)}°")
                if "max_skew" in r:
                    parts.append(f"sk={round(r['max_skew'], 2)}")
                if "mq" in r:
                    parts.append(f"mq={round(r['mq'], 3)}")
                if bl and "bl_success" in r:
                    parts.append(f"BL={'OK' if r['bl_success'] else 'FAIL'}")
                    if r["bl_success"]:
                        parts.append(f"prism={r.get('bl_n_prism_cells', 0)}")
                print(f"  fid={info['file_id']:7} {tag:10}: " + " ".join(parts),
                      flush=True)
            else:
                msg = "TIMEOUT" if r.get("timeout") else (
                    r.get("message") or r.get("exc", "?")
                )
                print(f"  fid={info['file_id']:7} {tag:10}: FAIL {msg[:80]}",
                      flush=True)

    total = time.perf_counter() - t_start
    out_path = Path(__file__).parent / "bench_thingi10k_all_result.json"
    out_path.write_text(json.dumps(rows, indent=2))

    print(f"\n=== 요약 ===\ntotal time: {round(total, 1)}s\n결과: {out_path}",
          flush=True)
    summary: dict[str, dict[str, int]] = {}
    for r in rows:
        eng = r.get("engine", "?")
        bl = "+BL" if r.get("with_bl") else "raw"
        key = f"{eng:4}{bl:4}"
        summary.setdefault(key, {
            "ok": 0, "fail": 0, "timeout": 0,
            "A": 0, "B": 0, "C": 0, "D": 0, "bl_ok": 0,
        })
        if r.get("success"):
            summary[key]["ok"] += 1
            g = r.get("grade", "?")
            if g in ("A", "B", "C", "D"):
                summary[key][g] += 1
            if r.get("bl_success"):
                summary[key]["bl_ok"] += 1
        elif r.get("timeout"):
            summary[key]["timeout"] += 1
        else:
            summary[key]["fail"] += 1
    for k, v in sorted(summary.items()):
        print(f"  {k}: {v}", flush=True)


if __name__ == "__main__":
    main()
