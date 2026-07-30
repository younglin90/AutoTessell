"""자율 루프 목표 달성 판정 스크립트.

목표: 사용자가 (1) STL/CAD 업로드 (2) 목표 격자 수 N (3) mesh_type
(tet/hex_dominant/poly) (4) BL 레이어 수를 입력하면 웹 GUI 에서 자동으로
해당 메쉬가 생성된다.

성공 기준 (모두 통과 시 exit 0):
  A. 웹 GUI(index.html)에 4개 입력 컨트롤 존재
     (파일 업로드 / 목표 셀 수 / mesh_type 3종 / BL 레이어)
  B. 파라미터 전파: dry-run 으로 N + bl_layers 가 strategy 에 반영되는지
  C. E2E: 서버 기동 → cube STL 업로드 → 각 mesh_type 으로 WS 생성 →
     verdict PASS/PASS_WITH_WARNINGS + 0.3N ≤ cells ≤ 3N

Usage:
    python tests/verify_goal.py
    python tests/verify_goal.py --phase param --target-cells 2000 --bl-layers 0
    python tests/verify_goal.py --phase e2e --types tet --per-type-timeout 120
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PORT = 9746
BASE = f"http://127.0.0.1:{PORT}"
WS = f"ws://127.0.0.1:{PORT}"
STL = ROOT / "tests" / "stl" / "01_easy_cube.stl"
N_TARGET = 15000
BL_LAYERS = 2
CELL_LO, CELL_HI = 0.3, 3.0
RUN_TIMEOUT = 420  # per mesh_type [s]

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(f"{name}: {detail}")


# ---------------------------------------------------------------------------
# A. GUI controls
# ---------------------------------------------------------------------------

def verify_gui() -> None:
    print("[A] 웹 GUI 컨트롤")
    html = (ROOT / "desktop" / "web" / "index.html").read_text(encoding="utf-8")
    check("파일 업로드 컨트롤", 'id="file-input"' in html and 'id="dropzone"' in html)
    check(
        "mesh_type 3종 선택",
        all(f'data-v="{t}"' in html for t in ("tet", "hex_dominant", "poly")),
    )
    check("목표 셀 수 N 입력", 'id="max_cells"' in html)
    check("BL 레이어 수 입력", 'id="bl_layers"' in html)


# ---------------------------------------------------------------------------
# B. 파라미터 전파 (dry-run strategy)
# ---------------------------------------------------------------------------

def verify_param_propagation(target_cells: int = N_TARGET, bl_layers: int = BL_LAYERS) -> None:
    print("[B] 파라미터 전파 (dry-run)")
    import tempfile

    from desktop.server import _build_run_kwargs

    kwargs = _build_run_kwargs(
        "draft", "auto", "tet", 1,
        {"max_cells": target_cells, "bl_layers": bl_layers},
    )
    tsp = kwargs.get("tier_specific_params", {})
    check("N → max_cells+target_cells", kwargs.get("max_cells") == target_cells
          and tsp.get("target_cells") == target_cells)
    check("bl_layers → tier params", tsp.get("bl_layers") == bl_layers)

    from core.pipeline.orchestrator import PipelineOrchestrator

    with tempfile.TemporaryDirectory(prefix="verify_goal_") as td:
        res = PipelineOrchestrator().run(
            STL, Path(td) / "case", dry_run=True, progress_callback=None, **kwargs
        )
        ok = bool(res.success and res.strategy is not None)
        bl = getattr(res.strategy, "boundary_layers", None)
        n_layers = getattr(bl, "num_layers", None)
        enabled = getattr(bl, "enabled", None)
        check("dry-run strategy 생성", ok)
        check(
            "strategy.boundary_layers.num_layers == BL (+enabled)",
            n_layers == bl_layers and enabled is (bl_layers > 0),
            f"num_layers={n_layers} enabled={enabled}",
        )


# ---------------------------------------------------------------------------
# C. E2E per mesh_type
# ---------------------------------------------------------------------------

def _start_server() -> None:
    import uvicorn

    from desktop.server import app

    cfg = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error")
    server = uvicorn.Server(cfg)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            return
        time.sleep(0.1)
    raise RuntimeError("server failed to start")


async def _run_type(
    mesh_type: str,
    *,
    target_cells: int = N_TARGET,
    bl_layers: int = BL_LAYERS,
    run_timeout: int = RUN_TIMEOUT,
) -> dict:
    import httpx
    import websockets

    async with httpx.AsyncClient(timeout=60) as c:
        with STL.open("rb") as f:
            r = await c.post(
                f"{BASE}/upload",
                files={"file": (STL.name, f, "application/octet-stream")},
            )
        r.raise_for_status()
        job_id = r.json()["job_id"]

    t0 = time.perf_counter()
    result: dict = {}
    async with websockets.connect(f"{WS}/ws/mesh/{job_id}", max_size=None) as ws:
        await ws.send(json.dumps({
            "action": "start",
            "mesh_type": mesh_type,
            "quality": "draft",
            "tier": "auto",
            "max_iterations": 1,
            "max_cells": target_cells,
            "bl_layers": bl_layers,
        }))
        try:
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=run_timeout))
                if msg.get("type") in ("result", "error"):
                    result = msg
                    break
        except TimeoutError:
            result = {"type": "timeout"}
    result["elapsed"] = round(time.perf_counter() - t0, 1)
    result["job_id"] = job_id
    return result


def verify_e2e(
    types: list[str],
    target_cells: int = N_TARGET,
    bl_layers: int = BL_LAYERS,
    run_timeout: int = RUN_TIMEOUT,
) -> None:
    print(f"[C] E2E 메쉬 생성 (N={target_cells}, BL={bl_layers})")
    from core.strategist.tier_selector import mesh_type_family_tiers

    _start_server()
    for mt in types:
        res = asyncio.run(
            _run_type(
                mt,
                target_cells=target_cells,
                bl_layers=bl_layers,
                run_timeout=run_timeout,
            )
        )
        verdict = res.get("verdict", res.get("type"))
        cells = res.get("cells") or 0
        tier = str(res.get("tier") or "")
        ok_verdict = verdict in ("PASS", "PASS_WITH_WARNINGS")
        ok_cells = CELL_LO * target_cells <= cells <= CELL_HI * target_cells
        ok_family = tier in mesh_type_family_tiers(mt)
        check(
            f"{mt}: verdict",
            ok_verdict,
            f"verdict={verdict} tier={tier} ({res.get('elapsed')}s)"
            + (f" msg={str(res.get('message'))[:100]}" if not ok_verdict else ""),
        )
        check(
            f"{mt}: cells in [{CELL_LO}N, {CELL_HI}N]",
            ok_cells,
            f"cells={cells} (N={target_cells})",
        )
        check(
            f"{mt}: 같은 계열 tier 사용",
            ok_family,
            f"tier={tier}",
        )


# ---------------------------------------------------------------------------

_PHASES = ("gui", "param", "e2e")


def _parse_types(raw_values: list[str] | None) -> list[str]:
    if not raw_values:
        return ["tet", "hex_dominant", "poly"]
    types = [item.strip() for value in raw_values for item in value.split(",") if item.strip()]
    if not types:
        raise ValueError("at least one mesh type is required")
    return list(dict.fromkeys(types))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phased release-goal verification")
    parser.add_argument("--phase", choices=_PHASES, action="append")
    parser.add_argument("--types", action="append")
    parser.add_argument("--target-cells", type=int, default=N_TARGET)
    parser.add_argument("--bl-layers", type=int, default=BL_LAYERS)
    parser.add_argument("--per-type-timeout", type=int, default=RUN_TIMEOUT)
    parser.add_argument("--evidence-json", type=Path)
    args = parser.parse_args(argv)
    if args.target_cells <= 0:
        parser.error("--target-cells must be positive")
    if args.bl_layers < 0:
        parser.error("--bl-layers must be non-negative")
    if args.per_type_timeout <= 0:
        parser.error("--per-type-timeout must be positive")
    args.phases = list(dict.fromkeys(args.phase or _PHASES))
    args.types = _parse_types(args.types)
    return args


def _write_evidence(path: Path, evidence: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _run_phase(name: str, args: argparse.Namespace) -> None:
    if name == "gui":
        verify_gui()
    elif name == "param":
        verify_param_propagation(args.target_cells, args.bl_layers)
    elif name == "e2e":
        verify_e2e(args.types, args.target_cells, args.bl_layers, args.per_type_timeout)
    else:  # pragma: no cover - argparse prevents this.
        raise ValueError(f"unknown verification phase: {name}")


def main(argv: list[str] | None = None) -> int:
    global FAILURES
    FAILURES = []
    args = parse_args(argv)
    print(
        f"=== verify_goal — phases={args.phases} types={args.types} "
        f"N={args.target_cells} BL={args.bl_layers} timeout={args.per_type_timeout}s ==="
    )
    evidence = {
        "inputs": {
            "phases": args.phases,
            "types": args.types,
            "target_cells": args.target_cells,
            "bl_layers": args.bl_layers,
            "per_type_timeout": args.per_type_timeout,
        },
        "phases": {phase: {"status": "NOT_RUN"} for phase in _PHASES},
    }
    for phase in args.phases:
        start = time.perf_counter()
        failures_before = len(FAILURES)
        try:
            _run_phase(phase, args)
        except Exception as exc:  # noqa: BLE001
            check(f"{phase} (예외)", False, repr(exc)[:200])
        status = "PASS" if len(FAILURES) == failures_before else "FAIL"
        evidence["phases"][phase] = {
            "status": status,
            "elapsed_seconds": round(time.perf_counter() - start, 3),
            "failures": FAILURES[failures_before:],
        }
    evidence["result"] = "PASS" if not FAILURES else "FAIL"
    evidence["failures"] = list(FAILURES)
    if args.evidence_json is not None:
        _write_evidence(args.evidence_json, evidence)

    print()
    if FAILURES:
        print(f"RESULT: FAIL ({len(FAILURES)} failures)")
        for failure in FAILURES:
            print("  -", failure)
        return 1
    print("RESULT: SUCCESS — selected phases passed; omitted phases are NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
