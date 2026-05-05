"""Round 8 / H2 — native_tet 성공률 / 품질 벤치.

여러 STL 에 대해 native_tet 실행 후:
  - 성공 여부
  - cell 수 / min_q / mean_q
  - elapsed

벤치 result 를 JSON 으로 저장 + 최소 허용 기준 검증.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


BENCH_STL_DIR = Path(__file__).parent / "stl"
BENCH_OUTPUT = Path(__file__).parent / "stl" / "native_tet_bench_latest.json"


def _run_bench(stl_files, seed_density=6):
    from core.generator.native_tet.mesher import generate_native_tet
    from core.generator.native_tet.quality import (
        snapshot as quality_snapshot,
        snapshot_to_dict,
    )
    import tempfile
    import time
    import trimesh

    rows = []
    for stl in stl_files:
        try:
            m = trimesh.load(str(stl), force="mesh")
        except Exception as e:
            rows.append({
                "stl": stl.name, "success": False,
                "error": f"load failed: {e}",
            })
            continue
        V = np.asarray(m.vertices, dtype=np.float64)
        F = np.asarray(m.faces, dtype=np.int64)

        with tempfile.TemporaryDirectory() as td:
            t0 = time.perf_counter()
            try:
                res = generate_native_tet(
                    V, F, Path(td) / "case",
                    seed_density=seed_density,
                    enable_phase_a=True,
                    enable_phase_b=False,
                    max_input_vertices=100000,
                )
                elapsed = time.perf_counter() - t0
                row = {
                    "stl": stl.name,
                    "n_surf_verts": int(V.shape[0]),
                    "n_surf_faces": int(F.shape[0]),
                    "success": bool(res.success),
                    "elapsed_s": round(elapsed, 3),
                    "message": res.message[:200],
                }
                if res.success and res.tets is not None:
                    snap = quality_snapshot(res.tet_points, res.tets)
                    row.update({
                        "n_cells": int(res.n_cells),
                        "n_points": int(res.n_points),
                        # 단순 필드 유지 (backward-compat).
                        "min_q": round(snap.min_q, 4),
                        "mean_q": round(snap.mean_q, 4),
                        "mean_aspect": round(snap.mean_aspect, 2),
                        "min_dihedral_deg": round(snap.min_dihedral_deg, 2),
                        # beta880: 확장 통계 dict 도 함께 저장.
                        "quality_detail": snapshot_to_dict(snap),
                    })
                rows.append(row)
            except Exception as e:
                rows.append({
                    "stl": stl.name,
                    "success": False,
                    "error": str(e),
                    "elapsed_s": round(time.perf_counter() - t0, 3),
                })
    return rows


def test_native_tet_bench_basic(tmp_path) -> None:
    """주요 bench STL 에 대해 벤치 실행 + JSON 저장 + 최소 성공률 보장.

    skip 조건: bench STL 이 없는 환경.
    """
    candidates = [
        BENCH_STL_DIR / "01_easy_cube.stl",
        BENCH_STL_DIR / "02_medium_cylinder.stl",
        BENCH_STL_DIR / "03_hard_bracket.stl",
        BENCH_STL_DIR / "04_extreme_gear.stl",
        BENCH_STL_DIR / "05_ultra_knot.stl",
    ]
    existing = [p for p in candidates if p.exists()]
    if not existing:
        pytest.skip("tests/stl/ bench STL 없음")

    rows = _run_bench(existing, seed_density=6)

    # 결과 저장 (최신 벤치 스냅샷).
    BENCH_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    BENCH_OUTPUT.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 최소 허용: 쉬운 형상 (cube) 은 반드시 성공.
    easy = [r for r in rows if r.get("stl") == "01_easy_cube.stl"]
    assert easy, "cube bench row 없음"
    assert easy[0].get("success") is True, (
        f"easy cube 실패: {easy[0].get('message') or easy[0].get('error')}"
    )

    # 전체 성공률 >= 1/3 (현재 수준).
    n_success = sum(1 for r in rows if r.get("success"))
    assert n_success >= max(1, len(rows) // 3)


def test_native_tet_bench_drift_check() -> None:
    """최신 벤치 JSON 이 존재하면 min_q 가 비정상적으로 떨어지지 않았는지 확인.

    baseline: cube 만 하드 고정. 나머지는 소프트 가이드.
    """
    if not BENCH_OUTPUT.exists():
        pytest.skip("벤치 JSON 아직 없음 — test_native_tet_bench_basic 먼저 실행")
    rows = json.loads(BENCH_OUTPUT.read_text(encoding="utf-8"))
    for r in rows:
        if r.get("stl") == "01_easy_cube.stl" and r.get("success"):
            # cube 는 mean_q > 0.2 유지.
            assert r.get("mean_q", 0.0) > 0.2, (
                f"cube mean_q drift: {r.get('mean_q')}"
            )


BENCH_PHASE_B_OUTPUT = Path(__file__).parent / "stl" / "native_tet_bench_phaseB.json"


@pytest.mark.slow
def test_native_tet_phase_b_comparison_bench() -> None:
    """Phase A only vs A+B+C: 같은 STL 에 대해 품질 비교.

    Slow: 5 STL × 2 모드 + Phase B local ops 이 ultra_knot 에 10s+ 걸림.
    기본 회귀 세트에서 제외. 수동 실행 시에만 사용.
    """
    from core.generator.native_tet.mesher import generate_native_tet
    from core.generator.native_tet.quality import tet_shape_quality
    import tempfile
    import time
    import trimesh

    # Round 14 벡터화 후 4_gear / 5_knot 도 재시도 가능.
    candidates = [
        BENCH_STL_DIR / "01_easy_cube.stl",
        BENCH_STL_DIR / "02_medium_cylinder.stl",
        BENCH_STL_DIR / "03_hard_bracket.stl",
        BENCH_STL_DIR / "04_extreme_gear.stl",
        BENCH_STL_DIR / "05_ultra_knot.stl",
    ]
    existing = [p for p in candidates if p.exists()]
    if not existing:
        pytest.skip("tests/stl/ bench STL 없음")

    rows = []
    for stl in existing:
        m = trimesh.load(str(stl), force="mesh")
        V = np.asarray(m.vertices, dtype=np.float64)
        F = np.asarray(m.faces, dtype=np.int64)

        row = {"stl": stl.name, "n_surf": int(F.shape[0])}

        with tempfile.TemporaryDirectory() as td:
            for label, kw in [
                ("A", dict(enable_phase_a=True, enable_phase_b=False)),
                ("ABC", dict(
                    enable_phase_a=True,
                    enable_phase_b=True,
                    enable_phase_c=True,
                    local_ops_iterations=1,
                    tangent_smooth_iterations=1,
                )),
            ]:
                t0 = time.perf_counter()
                try:
                    res = generate_native_tet(
                        V, F, Path(td) / f"case_{label}",
                        seed_density=6,
                        max_input_vertices=50000,
                        **kw,
                    )
                    elapsed = time.perf_counter() - t0
                    if res.success and res.tets is not None:
                        q = tet_shape_quality(res.tet_points, res.tets)
                        row[f"{label}_success"] = True
                        row[f"{label}_n_cells"] = int(res.n_cells)
                        row[f"{label}_min_q"] = round(float(q.min()), 4) if q.size else 0.0
                        row[f"{label}_mean_q"] = round(float(q.mean()), 4) if q.size else 0.0
                        row[f"{label}_elapsed_s"] = round(elapsed, 3)
                    else:
                        row[f"{label}_success"] = False
                        row[f"{label}_elapsed_s"] = round(elapsed, 3)
                        row[f"{label}_message"] = res.message[:100]
                except Exception as e:
                    row[f"{label}_success"] = False
                    row[f"{label}_error"] = str(e)[:100]
        rows.append(row)

    BENCH_PHASE_B_OUTPUT.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 최소한 cube 는 A/ABC 모두 성공해야.
    cube = next((r for r in rows if r["stl"] == "01_easy_cube.stl"), None)
    assert cube is not None
    assert cube.get("A_success") and cube.get("ABC_success")
