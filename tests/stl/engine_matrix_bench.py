"""전 엔진 × 난이도별 벤치마크 매트릭스.

각 설치된 엔진으로 5개 벤치마크 STL 을 draft quality 로 실행하고
(success/verdict/cells/시간) 을 수집.

Layer post 엔진도 WildMesh precursor 조합으로 매트릭스화.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.pipeline.orchestrator import PipelineOrchestrator  # noqa: E402

STL_ROOT = ROOT / "tests" / "stl"
BENCHMARKS = [
    ("easy_cube",   "01_easy_cube.stl"),
    ("medium_cyl",  "02_medium_cylinder.stl"),
    ("hard_brkt",   "03_hard_bracket.stl"),
    ("extreme_gear","04_extreme_gear.stl"),
    ("ultra_knot",  "05_ultra_knot.stl"),
]

VOLUME_ENGINES = [
    "wildmesh", "tetwild", "netgen", "snappy", "cfmesh",
    "mmg3d", "meshpy", "hex_classy", "polyhedral",
    "gmsh_hex", "core",
    # placeholders (실패 기대)
    "meshkit", "su2_hexpress", "salome_smesh",
]

LAYER_POST_ENGINES = [
    "disabled", "generate_boundary_layers", "refine_wall_layer",
    "netgen_bl", "gmsh_bl",
    # placeholders
    "pyhyp", "meshkit_bl", "su2_hexpress", "salome_bl",
]


def _count_cells(case_dir: Path) -> int:
    try:
        return sum(1 for _ in open(case_dir / "constant" / "polyMesh" / "owner"))
    except Exception:
        return 0


def run_one(tier: str, stl: Path, tag: str, layer: str = "disabled",
            timeout_sec: int = 120) -> dict:
    out = Path(f"/tmp/bench_{tag}_{tier}_{layer}")
    if out.exists():
        shutil.rmtree(out)
    tsp = {}
    if layer != "disabled":
        tsp.update({
            "post_layers_engine": layer,
            "post_layers_num_layers": 2,
            "post_layers_growth_ratio": 1.2,
            "post_layers_first_thickness": 0.005,
            "boundary_layers_enabled": False,
        })
    t0 = time.perf_counter()
    status = "crash"
    err = ""
    verdict = "?"
    cells = 0
    try:
        r = PipelineOrchestrator().run(
            input_path=stl, output_dir=out,
            quality_level="draft", tier_hint=tier,
            max_iterations=1, strict_tier=True,
            tier_specific_params=tsp or None,
            surface_remesh=False, no_repair=False,
        )
        status = "ok" if r.success else "fail"
        err = (r.error or "")[:140]
        if r.quality_report:
            ev = getattr(r.quality_report, "evaluation_summary", None)
            if ev:
                verdict = getattr(ev, "verdict", "?")
                if hasattr(verdict, "value"):
                    verdict = verdict.value
        cells = _count_cells(out)
    except Exception as exc:
        err = f"exception: {str(exc)[:100]}"
    elapsed = time.perf_counter() - t0
    return {
        "tier": tier, "stl": tag, "layer": layer,
        "status": status, "verdict": verdict,
        "cells": cells, "time_s": round(elapsed, 1),
        "err": err,
    }


def main() -> None:
    # 1) Volume engines × cube (가장 쉬운 STL 하나로 모두 검증 — 빠름)
    print("\n=== Volume Engines (cube, draft, 1-iter) ===")
    print(f"{'engine':<16} {'status':<7} {'verdict':<16} {'cells':>8} {'time':>7}  err")
    easy_stl = STL_ROOT / BENCHMARKS[0][1]
    for eng in VOLUME_ENGINES:
        r = run_one(eng, easy_stl, "cube")
        print(f"{r['tier']:<16} {r['status']:<7} {r['verdict']:<16} "
              f"{r['cells']:>8} {r['time_s']:>6.1f}s  "
              f"{r['err'][:60]}")

    # 2) Layer post engines on WildMesh cube
    print("\n=== Layer Post Engines (wildmesh + BL, cube, draft) ===")
    print(f"{'layer_engine':<28} {'status':<7} {'verdict':<16} {'cells':>8} {'time':>7}  err")
    for lay in LAYER_POST_ENGINES:
        r = run_one("wildmesh", easy_stl, "cube", layer=lay)
        print(f"{r['layer']:<28} {r['status']:<7} {r['verdict']:<16} "
              f"{r['cells']:>8} {r['time_s']:>6.1f}s  "
              f"{r['err'][:60]}")

    # 3) Main 4 engines × 5 STLs (더 오래 걸림)
    print("\n=== Main Volume Engines × 5 STL (no layer) ===")
    main_engines = ["wildmesh", "tetwild", "snappy", "cfmesh"]
    header = " " * 12 + "  ".join(f"{tag:<12}" for tag, _ in BENCHMARKS)
    print(header)
    for eng in main_engines:
        row = [f"{eng:<10}"]
        for tag, fname in BENCHMARKS:
            stl = STL_ROOT / fname
            r = run_one(eng, stl, tag)
            cells_str = f"{r['cells']}" if r['cells'] else "-"
            tag_result = f"{r['verdict'][:4]}/{cells_str}/{r['time_s']:.0f}s"
            row.append(f"{tag_result:<12}")
        print("  " + "  ".join(row))


if __name__ == "__main__":
    main()
