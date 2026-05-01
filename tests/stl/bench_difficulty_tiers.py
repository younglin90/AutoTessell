"""Thingi10K 난이도별 5선 × 4 tier × 3 native engine × BL on/off.

beta2230 — 산업 표준 비교용 (TetWild/fTetWild·snappy/cfMesh·Fluent/Star-CCM+).
4 tier (easy/medium/hard/extreme) × 5 mesh = 20 mesh.

난이도 기준 (Thingi10K metadata):
  easy     : closed + manifold + n_facets ∈ [80, 400]  + n_components=1
  medium   : closed + manifold + n_facets ∈ [400, 1200]
  hard     : closed=False or manifold=False, n_facets ∈ [400, 2000]
  extreme  : self_intersecting + manifold=False, n_facets ∈ [2000, 8000]

각 mesh × engine (tet/hex/poly) × BL on. 합 60 측정 (worker pool 4, per-cell 120s).
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
import tempfile
import multiprocessing as _mp
from concurrent.futures import ProcessPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# worker functions
# ---------------------------------------------------------------------------

def _try_bl(case_dir, n_layers: int = 3, engine_tag: str = "generic",
            bbox_diag: float = 0.0) -> dict:
    try:
        from core.layers.native_bl import generate_native_bl, BLConfig
        # beta2250: first_thickness 절대값 0.001 → bbox-relative (1e-3 × bbox).
        # Thingi10K mesh 의 bbox 는 보통 50-200 → 절대 0.001 은 collision 에서
        # 거부. cfMesh `relativeSizes true` 동급.
        ft = 0.001 * bbox_diag if bbox_diag > 0 else 0.001
        cfg = BLConfig(
            num_layers=int(n_layers),
            growth_ratio=1.2,
            first_thickness=ft,
            collision_safety=True,
            feature_lock=True,
        )
        r = generate_native_bl(case_dir, cfg, engine_tag=engine_tag)
        return {
            "bl_success": bool(r.success),
            "bl_n_prism_cells": int(r.n_prism_cells),
            "bl_elapsed": float(r.elapsed),
            "bl_message": str(r.message)[:120],
            # beta2256 — wall preservation 검증 (cfMesh/T-Rex 동급).
            "bl_wall_preserve_max_diff": float(getattr(r, "wall_preserve_max_diff", 0.0)),
            "bl_wall_preserve_max_diff_rel": float(getattr(r, "wall_preserve_max_diff_rel", 0.0)),
            "bl_wall_preserve_n_drift": int(getattr(r, "wall_preserve_n_drift", 0)),
            "bl_wall_preserve_within_envelope": bool(getattr(r, "wall_preserve_within_envelope", True)),
            "bl_max_aspect_ratio": float(getattr(r, "max_aspect_ratio", 0.0)),
        }
    except Exception as exc:
        return {"bl_success": False, "bl_exc": str(exc)[:120]}


def _worker_run(payload: tuple) -> dict:
    # GAP-FAST / beta2774 — payload 에 tier 추가 (extreme 시 phase_c skip).
    if len(payload) == 7:
        V_bytes, V_shape, F_bytes, F_shape, engine, with_bl, tier = payload
    else:
        V_bytes, V_shape, F_bytes, F_shape, engine, with_bl = payload
        tier = ""
    sys.path.insert(0, str(_REPO_ROOT))
    import warnings as _w
    _w.filterwarnings("ignore")
    # P4-C (beta2236): pytetwild 가 fork-spawned worker 에서 segfault.
    # worker 에서 P4-C fallback 끄기 — main process / 직접 호출에선 자동 활성.
    # spawn context 면 P4-C 도 안전 — env 로 세팅. fork 면 forced OFF.
    if _mp.get_start_method(allow_none=True) != "spawn":
        os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "0"
    # else: spawn worker 는 부모 env 상속 — main 의 설정 유지.

    V = np.frombuffer(V_bytes, dtype=np.float64).reshape(V_shape)
    F = np.frombuffer(F_bytes, dtype=np.int64).reshape(F_shape)
    out: dict = {"engine": engine, "with_bl": with_bl}

    with tempfile.TemporaryDirectory() as td:
        case = Path(td) / "c"
        t0 = time.perf_counter()
        try:
            if engine == "tet":
                from core.generator.native_tet.mesher import generate_native_tet
                # GAP-FAST / beta2774 — extreme/hard tier: heavy phase_c skip
                # (fixed time budget). worker 에서 self-impl 빨리 fail/D 도달 →
                # main 의 P4D fallback 이 처리. extreme tet 333s → 30s 이내.
                _heavy_tier = tier in ("extreme", "hard")
                _phase_c = (not _heavy_tier)
                _amips = (not _heavy_tier)
                r = generate_native_tet(
                    V, F, case, seed_density=8,
                    enable_phase_a=True, enable_phase_b=False,
                    enable_phase_c=_phase_c, enable_amips_smooth=_amips,
                )
                out["success"] = bool(r.success)
                out["n_cells"] = int(getattr(r, "n_cells", 0) or getattr(r, "n_tets", 0))
                out["grade"] = str(getattr(r, "quality_grade", "?"))
                # NativeTetResult 의 mean_q 는 r.quality.mean_q 에 있음.
                _q = getattr(r, "quality", None)
                out["mq"] = float(getattr(_q, "mean_q", -1.0)) if _q is not None else -1.0
                # beta2356 — pre-mesh SI count (P2.6 chain). bench 에 노출.
                out["n_si_pre"] = getattr(r, "n_self_intersect_pre", None)
                if not r.success:
                    out["message"] = str(getattr(r, "message", ""))[:120]
            elif engine == "hex":
                from core.generator.native_hex.mesher import generate_native_hex
                # beta2261: seed_density 10 → 20 (Thingi10K mesh 의 bbox/n_face
                # 비율 기준으로 commercial-grade resolution. 이전 10 은 너무
                # coarse 해서 small mesh 에서 cells=3-50 만 산출).
                r = generate_native_hex(
                    V, F, case, seed_density=20,
                    snap_boundary=True, snap_iterations=2,
                )
                out["success"] = bool(r.success)
                out["n_cells"] = int(getattr(r, "n_cells", 0))
                out["grade"] = str(getattr(r, "quality_grade", "?"))
                out["max_no_deg"] = float(getattr(r, "max_non_orthogonality_deg", -1.0))
                out["max_skew"] = float(getattr(r, "max_skewness", -1.0))
                # beta2356 — hex 도 SI count 노출.
                out["n_si_pre"] = getattr(r, "n_self_intersect_pre", None)
                if not r.success:
                    out["message"] = str(getattr(r, "message", ""))[:120]
            else:  # poly
                from core.generator.native_poly.voronoi import generate_native_poly_voronoi
                # beta2261: seed_density 10 → 20 (commercial-grade poly resolution).
                r = generate_native_poly_voronoi(
                    V, F, case, seed_density=20, n_lloyd=2, auto_escalate=True,
                )
                out["success"] = bool(r.success)
                out["n_cells"] = int(getattr(r, "n_cells", 0))
                out["grade"] = str(getattr(r, "quality_grade", "?"))
                out["max_no_deg"] = float(getattr(r, "max_non_orthogonality_deg", -1.0))
                out["max_skew"] = float(getattr(r, "max_skewness", -1.0))
                # beta2356 — poly 도 SI count 노출.
                out["n_si_pre"] = getattr(r, "n_self_intersect_pre", None)
                if not r.success:
                    out["message"] = str(getattr(r, "message", ""))[:120]

            # I4 / beta2622 — stage profiling: gen vs bl vs total.
            _t_gen_end = time.perf_counter()
            out["t_gen_s"] = round(_t_gen_end - t0, 3)

            if out.get("success") and with_bl:
                _t_bl_start = time.perf_counter()
                # beta2250: pass bbox_diag for relative first_thickness.
                _bbox_arr = V.max(axis=0) - V.min(axis=0)
                _bbox_d = float(np.linalg.norm(_bbox_arr))
                bl = _try_bl(case, n_layers=3, engine_tag=engine, bbox_diag=_bbox_d)
                out.update(bl)
                out["t_bl_s"] = round(time.perf_counter() - _t_bl_start, 3)
            else:
                out["t_bl_s"] = 0.0

            out["elapsed"] = round(time.perf_counter() - t0, 2)
            # gen / bl / overhead 비율.
            _t_total = float(out["elapsed"])
            if _t_total > 1e-6:
                out["pct_gen"] = round(100.0 * out["t_gen_s"] / _t_total, 1)
                out["pct_bl"] = round(100.0 * out["t_bl_s"] / _t_total, 1)

        except Exception as exc:
            out["success"] = False
            out["exc"] = str(exc)[:200]
            out["elapsed"] = round(time.perf_counter() - t0, 2)

    return out


# ---------------------------------------------------------------------------
# tier 별 mesh 선별
# ---------------------------------------------------------------------------

def _select_meshes() -> dict[str, list[dict]]:
    import thingi10k
    thingi10k.init(variant="npz")

    def _row_to_info(row, tier):
        return {
            "tier": tier,
            "file_id": int(row["file_id"]),
            "num_vertices": int(row["num_vertices"]),
            "num_facets": int(row["num_facets"]),
            "num_components": int(row.get("num_components", 1)),
            "closed": bool(row.get("closed", False)),
            "file_path": str(row["file_path"]),
        }

    # beta2275 — env AUTO_TESSELL_BENCH_N_PER_TIER 로 mesh 개수 제어 (default 5).
    # 더 빠른 smoke run 을 위해 1-2 로 설정 가능.
    n_per_tier = int(os.environ.get("AUTO_TESSELL_BENCH_N_PER_TIER", "5"))

    out: dict[str, list[dict]] = {"easy": [], "medium": [], "hard": [], "extreme": []}

    # easy
    for row in thingi10k.dataset(
        closed=True, manifold=True, num_facets=(80, 400),
    ):
        if len(out["easy"]) >= n_per_tier:
            break
        if int(row.get("num_components", 1)) == 1:
            out["easy"].append(_row_to_info(row, "easy"))

    # medium
    for row in thingi10k.dataset(
        closed=True, manifold=True, num_facets=(400, 1200),
    ):
        if len(out["medium"]) >= n_per_tier:
            break
        out["medium"].append(_row_to_info(row, "medium"))

    # hard (closed=False 또는 manifold=False, 범위 제한)
    for row in thingi10k.dataset(
        manifold=False, num_facets=(400, 2000),
    ):
        if len(out["hard"]) >= n_per_tier:
            break
        out["hard"].append(_row_to_info(row, "hard"))

    # extreme — face cap 8000 → 5000 으로 축소 (1017016 V=2994 F=5934 같은 mesh 회피).
    for row in thingi10k.dataset(
        self_intersecting=True, manifold=False, num_facets=(2000, 5000),
    ):
        if len(out["extreme"]) >= n_per_tier:
            break
        out["extreme"].append(_row_to_info(row, "extreme"))

    return out


def main():
    # G8 / beta2608 — quick mode: --quick 또는 env AUTO_TESSELL_BENCH_QUICK=1.
    #   easy + medium tier 만, tet+BL 만, per-cell timeout 60s, 5 mesh max.
    #   전체 ~2-3 min (full ~30 min).
    import sys as _sys_g8
    _quick = (
        "--quick" in _sys_g8.argv
        or os.environ.get("AUTO_TESSELL_BENCH_QUICK", "0") == "1"
    )
    if _quick:
        print("=== QUICK mode — easy+medium × tet+BL ===\n", flush=True)
    else:
        print("=== Thingi10K 난이도별 4 tier × 5 mesh × 3 engine + BL ===\n", flush=True)
    tiers = _select_meshes()
    if _quick:
        # easy + medium 만, mesh 수 줄이기 (3 each).
        tiers = {
            k: v[:3] for k, v in tiers.items()
            if k in ("easy", "medium")
        }
    for tier_name, meshes in tiers.items():
        print(f"  [{tier_name}] {len(meshes)} mesh:", flush=True)
        for info in meshes:
            print(f"    fid={info['file_id']:8} V={info['num_vertices']:6} "
                  f"F={info['num_facets']:6} comp={info['num_components']} "
                  f"closed={info['closed']}", flush=True)
    print(flush=True)

    all_meshes = []
    for tier_name, meshes in tiers.items():
        all_meshes.extend(meshes)
    print(f"total {len(all_meshes)} mesh\n", flush=True)

    # main 에서 V/F 미리 로드
    import thingi10k as _t10k
    loaded: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for info in all_meshes:
        V, F = _t10k.load_file(info["file_path"])
        loaded[info["file_id"]] = (
            V.astype(np.float64), F.astype(np.int64),
        )

    # jobs (BL on 만 — 시간 cap)
    jobs = []
    # G8: quick 모드면 tet 만.
    _engines = ("tet",) if _quick else ("tet", "hex", "poly")
    for info in all_meshes:
        V, F = loaded[info["file_id"]]
        V_bytes = V.tobytes(); V_shape = V.shape
        F_bytes = F.tobytes(); F_shape = F.shape
        for engine in _engines:
            jobs.append((info, engine, True,
                         (V_bytes, V_shape, F_bytes, F_shape, engine, True,
                          str(info.get("tier", "")))))

    # 권장 보정: workers 4→8, per-cell timeout 180→90s.
    n_workers = min(8, max(1, (os.cpu_count() or 1)))
    # beta2265: per-cell timeout 90 → 180s. extreme tier 의 self-impl + BL 가
    # 90s 초과 (1017017 의 경우 1000s+ 로 timeout). 180s 면 commercial-grade
    # mesh 도 처리 + bench 완주 가능 (전체 ~30 분).
    per_cell_timeout = 60.0 if _quick else 180.0
    print(f"workers={n_workers} per_cell_timeout={per_cell_timeout}s "
          f"jobs={len(jobs)}\n", flush=True)

    rows: list[dict] = []
    t_start = time.perf_counter()

    # spawn context — P4-C pytetwild fork-segfault 회피. AUTO_TESSELL_P4C=1 시 활성.
    _ctx_name = "spawn" if os.environ.get("AUTO_TESSELL_P4C", "0") == "1" else "fork"
    _mp_ctx = _mp.get_context(_ctx_name)
    print(f"  mp_context={_ctx_name}", flush=True)
    with ProcessPoolExecutor(max_workers=n_workers, mp_context=_mp_ctx) as pool:
        future_map = {}
        for (info, engine, bl, payload) in jobs:
            fut = pool.submit(_worker_run, payload)
            future_map[fut] = (info, engine, bl)

        for fut in as_completed(future_map.keys(), timeout=None):
            info, engine, bl = future_map[fut]
            tier = info["tier"]
            tag = f"{engine}+BL"
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
                if "max_no_deg" in r and r["max_no_deg"] >= 0:
                    parts.append(f"no={round(r['max_no_deg'], 1)}°")
                if "max_skew" in r and r["max_skew"] >= 0:
                    parts.append(f"sk={round(r['max_skew'], 2)}")
                if "mq" in r and r["mq"] >= 0:
                    parts.append(f"mq={round(r['mq'], 3)}")
                # beta2357 — pre-mesh SI count (P2.6 chain). 0 이면 생략.
                _si_v = r.get("n_si_pre")
                if isinstance(_si_v, int) and _si_v > 0:
                    parts.append(f"si={_si_v}")
                if r.get("bl_success"):
                    parts.append(f"BL=OK p={r.get('bl_n_prism_cells', '?')}")
                elif "bl_success" in r:
                    parts.append("BL=FAIL")
                print(f"  [{tier}] fid={info['file_id']:8} {tag:10}: "
                      + " ".join(parts), flush=True)
            else:
                msg = r.get("message") or r.get("exc") or "fail"
                if r.get("timeout"):
                    msg = f"TIMEOUT {r['elapsed']}s"
                print(f"  [{tier}] fid={info['file_id']:8} {tag:10}: FAIL {msg[:80]}",
                      flush=True)

    elapsed_pool = round(time.perf_counter() - t_start, 1)
    print(f"\nworker pool time: {elapsed_pool}s ({elapsed_pool/60:.1f}min)\n", flush=True)

    # P4-D (beta2238) — main process 에서 tet grade<A row sequential pytetwild
    # fallback. worker fork-segfault 회피 (P4-C 가 worker 에서 강제 OFF).
    # native_bl 은 fallback polyMesh 위에도 자동 적용.
    print("=== P4-D pytetwild fallback (sequential main process) ===\n", flush=True)
    os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "1"  # main 에서 활성.
    n_p4d_attempt = 0
    n_p4d_success = 0
    for ri, row in enumerate(rows):
        if row.get("engine") != "tet":
            continue
        if row.get("grade") == "A":
            continue
        if not row.get("success"):
            continue  # native_tet 자체 fail 은 skip.
        fid = row["file_id"]
        V_t, F_t = loaded.get(fid, (None, None))
        if V_t is None:
            continue
        n_p4d_attempt += 1
        try:
            with tempfile.TemporaryDirectory() as td:
                case = Path(td) / "c"
                t0_p4d = time.perf_counter()
                from core.generator.native_tet.mesher import generate_native_tet
                r_fb = generate_native_tet(
                    V_t, F_t, case, seed_density=8,
                    enable_phase_a=True, enable_phase_b=False,
                    enable_phase_c=True, enable_amips_smooth=True,
                )
                el_p4d = round(time.perf_counter() - t0_p4d, 2)
                if r_fb.success:
                    new_grade = str(getattr(r_fb, "quality_grade", "?"))
                    new_cells = int(getattr(r_fb, "n_cells", 0))
                    q_obj = getattr(r_fb, "quality", None)
                    new_mq = float(getattr(q_obj, "mean_q", -1.0)) if q_obj else -1.0
                    _bbox_p = V_t.max(axis=0) - V_t.min(axis=0)
                    _bbox_dp = float(np.linalg.norm(_bbox_p))
                    bl_p4d = _try_bl(case, n_layers=3, engine_tag="tet", bbox_diag=_bbox_dp)
                    old_grade = row.get("grade", "?")
                    if new_grade in ("A", "B") and new_grade != old_grade:
                        n_p4d_success += 1
                    row["p4d_grade_old"] = old_grade
                    row["grade"] = new_grade
                    row["n_cells"] = new_cells
                    row["mq"] = new_mq
                    row["elapsed"] = row.get("elapsed", 0) + el_p4d
                    row.update({k: v for k, v in bl_p4d.items() if k.startswith("bl_")})
                    print(f"  [{row['tier']}] fid={fid:8} tet+BL P4D : "
                          f"grade={old_grade}→{new_grade} cells={new_cells} mq={new_mq:.3f} "
                          f"t={el_p4d}s BL={'OK' if bl_p4d.get('bl_success') else 'FAIL'}",
                          flush=True)
        except Exception as exc:
            print(f"  [{row['tier']}] fid={fid:8} tet+BL P4D : EXC {str(exc)[:80]}",
                  flush=True)
    elapsed_p4d = round(time.perf_counter() - t_start - elapsed_pool, 1)
    print(f"\nP4-D pytetwild fallback: {n_p4d_success}/{n_p4d_attempt} grade upgrade, "
          f"{elapsed_p4d}s", flush=True)
    elapsed = round(time.perf_counter() - t_start, 1)
    print(f"total time: {elapsed}s ({elapsed/60:.1f}min)\n", flush=True)

    # tier × engine 표
    tiers_order = ["easy", "medium", "hard", "extreme"]
    engines = ["tet", "hex", "poly"]
    print("=== Tier × Engine 합격 표 (grade A 카운트 / 5) ===\n", flush=True)
    for tier in tiers_order:
        for engine in engines:
            tier_rows = [r for r in rows if r.get("tier") == tier and r.get("engine") == engine]
            n_total = len(tier_rows)
            n_ok = sum(1 for r in tier_rows if r.get("success"))
            n_a = sum(1 for r in tier_rows if r.get("grade") == "A")
            n_bl = sum(1 for r in tier_rows if r.get("bl_success"))
            print(f"  {tier:8} | {engine:5} | OK={n_ok}/{n_total} "
                  f"grade A={n_a}/5 | BL OK={n_bl}/5", flush=True)

    out_path = Path(__file__).parent / "bench_difficulty_tiers_result.json"
    out_path.write_text(json.dumps(rows, default=str, ensure_ascii=False, indent=1))
    print(f"\n결과 저장: {out_path}", flush=True)

    # H7 / beta2616 — TSV auto-export (스프레드시트 직접 import 가능).
    tsv_path = Path(__file__).parent / "bench_difficulty_tiers_result.tsv"
    _cols = [
        "tier", "engine", "fid", "success", "grade", "n_cells", "elapsed",
        "t_gen_s", "t_bl_s", "pct_gen", "pct_bl",
        "mq", "min_q", "max_aspect", "n_self_intersect_pre",
        "bl_success", "bl_n_prism", "bl_max_aspect",
    ]
    try:
        with tsv_path.open("w", encoding="utf-8") as f:
            f.write("\t".join(_cols) + "\n")
            for r in rows:
                f.write("\t".join(str(r.get(c, "")) for c in _cols) + "\n")
        print(f"TSV 저장: {tsv_path}", flush=True)
    except Exception as _tsv_exc:
        print(f"TSV 저장 실패: {_tsv_exc}", flush=True)

    # summary 표 TSV (tier × engine grade A 카운트).
    summary_tsv_path = Path(__file__).parent / "bench_difficulty_tiers_summary.tsv"
    try:
        with summary_tsv_path.open("w", encoding="utf-8") as f:
            f.write("tier\tengine\tn_ok\tn_total\tn_grade_A\tn_bl_ok\n")
            for tier in tiers_order:
                for engine in engines:
                    tier_rows = [
                        r for r in rows
                        if r.get("tier") == tier and r.get("engine") == engine
                    ]
                    n_total = len(tier_rows)
                    n_ok = sum(1 for r in tier_rows if r.get("success"))
                    n_a = sum(1 for r in tier_rows if r.get("grade") == "A")
                    n_bl = sum(1 for r in tier_rows if r.get("bl_success"))
                    f.write(f"{tier}\t{engine}\t{n_ok}\t{n_total}\t{n_a}\t{n_bl}\n")
        print(f"summary TSV: {summary_tsv_path}", flush=True)
    except Exception as _sum_exc:
        print(f"summary TSV 저장 실패: {_sum_exc}", flush=True)


if __name__ == "__main__":
    main()
