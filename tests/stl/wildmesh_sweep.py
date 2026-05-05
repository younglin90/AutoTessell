"""WildMesh draft 파라미터 sweep — 05_ultra_knot.stl 이 PASS 할 때까지.

각 시도마다:
  - tier_specific_params 로 wildmesh_* 값 주입 (complexity tuning 무력화)
  - strict_tier=True, max_iterations=1 로 fallback 없이 1회 시도
  - knot PASS 여부 + max_non_ortho + cells + 시간 기록

탐색 전략: 현재 기본값에서 출발해 edge_length_r ↓, stop_quality ↓ 방향으로
단계적으로 조밀화 + 품질 강화. timeout(120s) 전에 non-ortho < 80° 달성 시 STOP.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from core.pipeline.orchestrator import PipelineOrchestrator

KNOT = Path("tests/stl/05_ultra_knot.stl")


def try_params(label: str, params: dict, max_sec: float = 120.0) -> dict:
    out = Path(f"/tmp/wm_sweep_{label}")
    if out.exists():
        import shutil
        shutil.rmtree(out)

    tsp = {
        "wildmesh_epsilon": params["eps"],
        "wildmesh_edge_length_r": params["edge"],
        "wildmesh_stop_quality": params["sq"],
        "wildmesh_max_its": params["its"],
    }
    print(f"\n[{label}] eps={params['eps']} edge={params['edge']} "
          f"sq={params['sq']} its={params['its']}")
    print("  ", end="", flush=True)

    t0 = time.perf_counter()
    orch = PipelineOrchestrator()
    try:
        result = orch.run(
            input_path=KNOT,
            output_dir=out,
            quality_level="draft",
            tier_hint="wildmesh",
            max_iterations=1,
            tier_specific_params=tsp,
            surface_remesh=False,
            no_repair=True,
            strict_tier=True,
            write_of_case=False,
        )
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"EXC {exc}")
        return {"label": label, "verdict": "EXC", "elapsed": elapsed, "error": str(exc)}
    elapsed = time.perf_counter() - t0

    info = {"label": label, "elapsed": elapsed, "params": params}
    if result.quality_report:
        cm = getattr(result.quality_report, "checkmesh", None)
        ev = getattr(result.quality_report, "evaluation_summary", None)
        info["verdict"] = getattr(ev, "verdict", "?") if ev else "?"
        if cm:
            info["cells"] = cm.cells
            info["max_non_ortho"] = cm.max_non_orthogonality
            info["max_skewness"] = cm.max_skewness
            info["negative_volumes"] = cm.negative_volumes
        print(f"{info['verdict']} {elapsed:.1f}s cells={info.get('cells', '?')} "
              f"non-ortho={info.get('max_non_ortho', '?'):.1f}°" if cm else
              f"{info['verdict']} {elapsed:.1f}s (no checkmesh)")
    else:
        info["verdict"] = "FAIL" if not result.success else "PASS?"
        print(f"{info['verdict']} {elapsed:.1f}s err={result.error}")
    return info


def main() -> None:
    """점점 더 tight 하게 조여가며 시도. 첫 PASS 시 STOP."""
    trials = [
        # 1) 현재 draft 기본값 — baseline (expected FAIL)
        ("T00_default",      {"eps": 0.002,   "edge": 0.06,  "sq": 20.0, "its": 40}),
        # 2) edge_length_r 를 조밀화
        ("T01_edge045",      {"eps": 0.002,   "edge": 0.045, "sq": 20.0, "its": 40}),
        ("T02_edge035",      {"eps": 0.002,   "edge": 0.035, "sq": 20.0, "its": 40}),
        # 3) stop_quality 강화
        ("T03_sq12",         {"eps": 0.002,   "edge": 0.045, "sq": 12.0, "its": 60}),
        # 4) epsilon 절반
        ("T04_eps0015",      {"eps": 0.0015,  "edge": 0.045, "sq": 12.0, "its": 60}),
        # 5) TetWild 매칭 조합 (이미 standard에 들어 있는 값)
        ("T05_tetwildmatch", {"eps": 0.001,   "edge": 0.05,  "sq": 10.0, "its": 80}),
        # 6) 조금 더 조밀
        ("T06_eps001_edge04", {"eps": 0.001,  "edge": 0.04,  "sq": 10.0, "its": 80}),
        # 7) stop_quality 8
        ("T07_sq8",          {"eps": 0.001,   "edge": 0.04,  "sq": 8.0,  "its": 100}),
        # 8) edge 0.035 + sq 10
        ("T08_edge035_sq10", {"eps": 0.0012,  "edge": 0.035, "sq": 10.0, "its": 80}),
    ]

    results: list[dict] = []
    best: dict | None = None
    for label, params in trials:
        r = try_params(label, params)
        results.append(r)
        # draft 임계값 80° 기준 PASS 여부로 판단
        if r.get("verdict", "").startswith("PASS") and r.get("max_non_ortho", 999) < 80:
            # 첫 PASS. 더 빠른/견고한 값 찾기 위해 한 번 더 시도
            if best is None:
                best = r
                print(f"\n★ 첫 PASS 발견: {label}")
                # stop condition: non-ortho 여유가 5° 이상이면 그만
                margin = 80.0 - r["max_non_ortho"]
                if margin >= 5.0 and r["elapsed"] < 30:
                    print(f"  → margin {margin:.1f}°, 속도 {r['elapsed']:.1f}s — 충분. STOP.")
                    break
                else:
                    print(f"  → margin {margin:.1f}° / 속도 {r['elapsed']:.1f}s — 계속 탐색해 더 안정적 값 시도.")

    print("\n" + "=" * 72)
    print("요약:")
    print(f"  {'label':<26} {'verdict':<8} {'time':>7} {'cells':>7} {'non-ortho':>10}")
    for r in results:
        print(f"  {r['label']:<26} {r.get('verdict', '?'):<8} "
              f"{r.get('elapsed', 0):>6.1f}s "
              f"{r.get('cells', '-'):>7} "
              f"{r.get('max_non_ortho', 0):>9.1f}°")
    if best:
        print(f"\n✓ 최적 파라미터: {best['params']}")
        print(f"  결과: non-ortho {best['max_non_ortho']:.1f}°, "
              f"cells {best['cells']}, time {best['elapsed']:.1f}s")
        sys.exit(0)
    else:
        print("\n✗ 모든 시도 실패. 더 극단적 파라미터 필요.")
        sys.exit(1)


if __name__ == "__main__":
    main()
