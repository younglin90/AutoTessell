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

Usage:  python tests/verify_goal.py [--types tet,hex_dominant,poly]
"""
from __future__ import annotations

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

def verify_param_propagation() -> None:
    print("[B] 파라미터 전파 (dry-run)")
    import tempfile

    from desktop.server import _build_run_kwargs

    kwargs = _build_run_kwargs(
        "draft", "auto", "tet", 1,
        {"max_cells": N_TARGET, "bl_layers": BL_LAYERS},
    )
    tsp = kwargs.get("tier_specific_params", {})
    check("N → max_cells+target_cells", kwargs.get("max_cells") == N_TARGET
          and tsp.get("target_cells") == N_TARGET)
    check("bl_layers → tier params", tsp.get("bl_layers") == BL_LAYERS)

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
            n_layers == BL_LAYERS and enabled is True,
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


async def _run_type(mesh_type: str) -> dict:
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
            "max_cells": N_TARGET,
            "bl_layers": BL_LAYERS,
        }))
        try:
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=RUN_TIMEOUT))
                if msg.get("type") in ("result", "error"):
                    result = msg
                    break
        except asyncio.TimeoutError:
            result = {"type": "timeout"}
    result["elapsed"] = round(time.perf_counter() - t0, 1)
    result["job_id"] = job_id
    return result


def verify_e2e(types: list[str]) -> None:
    print("[C] E2E 메쉬 생성 (N=%d, BL=%d)" % (N_TARGET, BL_LAYERS))
    from core.strategist.tier_selector import mesh_type_family_tiers

    _start_server()
    for mt in types:
        res = asyncio.run(_run_type(mt))
        verdict = res.get("verdict", res.get("type"))
        cells = res.get("cells") or 0
        tier = str(res.get("tier") or "")
        ok_verdict = verdict in ("PASS", "PASS_WITH_WARNINGS")
        ok_cells = CELL_LO * N_TARGET <= cells <= CELL_HI * N_TARGET
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
            f"cells={cells} (N={N_TARGET})",
        )
        check(
            f"{mt}: 같은 계열 tier 사용",
            ok_family,
            f"tier={tier}",
        )


# ---------------------------------------------------------------------------

def main() -> int:
    types = ["tet", "hex_dominant", "poly"]
    for a in sys.argv[1:]:
        if a.startswith("--types"):
            types = a.split("=", 1)[1].split(",") if "=" in a else types
    print(f"=== verify_goal — types={types} N={N_TARGET} BL={BL_LAYERS} ===")
    verify_gui()
    try:
        verify_param_propagation()
    except Exception as exc:  # noqa: BLE001
        check("파라미터 전파 (예외)", False, repr(exc)[:200])
    try:
        verify_e2e(types)
    except Exception as exc:  # noqa: BLE001
        check("E2E (예외)", False, repr(exc)[:200])

    print()
    if FAILURES:
        print(f"RESULT: FAIL ({len(FAILURES)} failures)")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("RESULT: SUCCESS — 목표 달성")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
