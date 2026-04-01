"""Auto-Tessell Desktop WebSocket Server.

Godot GUI ↔ Python Backend 통신을 담당한다.
localhost에서만 동작하며, 파일 업로드 → 메쉬 생성 → 진행상황 스트리밍을 지원한다.

Usage:
    python -m desktop.server                    # 기본 포트 9720
    python -m desktop.server --port 9720        # 포트 지정
"""

from __future__ import annotations

import asyncio
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from starlette.responses import Response

from core.utils.logging import get_logger

log = get_logger(__name__)

app = FastAPI(title="Auto-Tessell Desktop", version="0.1.0")

# ---------------------------------------------------------------------------
# 상태 관리
# ---------------------------------------------------------------------------

# job_id → job info
_jobs: dict[str, dict[str, Any]] = {}


def _create_job(input_filename: str) -> dict[str, Any]:
    job_id = str(uuid.uuid4())[:8]
    job = {
        "id": job_id,
        "status": "pending",
        "input_file": input_filename,
        "progress": 0.0,
        "stage": "",
        "message": "",
        "work_dir": tempfile.mkdtemp(prefix=f"autotessell_{job_id}_"),
        "result": None,
        "error": None,
        "created_at": time.time(),
    }
    _jobs[job_id] = job
    return job


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    """서버 상태 확인."""
    return {"status": "ok", "version": "0.1.0"}


@app.post("/upload")
async def upload_file(file: UploadFile) -> JSONResponse:
    """CAD/메쉬 파일 업로드 → job 생성."""
    if not file.filename:
        return JSONResponse({"error": "파일명 없음"}, status_code=400)

    job = _create_job(file.filename)
    work_dir = Path(job["work_dir"])

    # 파일 저장
    input_path = work_dir / file.filename
    with open(input_path, "wb") as f:
        content = await file.read()
        f.write(content)

    job["input_path"] = str(input_path)
    log.info("file_uploaded", job_id=job["id"], filename=file.filename, size=len(content))

    return JSONResponse({
        "job_id": job["id"],
        "filename": file.filename,
        "size": len(content),
    })


@app.get("/jobs")
async def list_jobs() -> list[dict[str, Any]]:
    """모든 작업 목록."""
    return [
        {
            "id": j["id"],
            "status": j["status"],
            "input_file": j["input_file"],
            "progress": j["progress"],
            "stage": j["stage"],
        }
        for j in _jobs.values()
    ]


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    """특정 작업 상태."""
    job = _jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    return JSONResponse({
        "id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "stage": job["stage"],
        "message": job["message"],
        "result": job["result"],
        "error": job["error"],
    })


@app.get("/jobs/{job_id}/download/{filename}")
async def download_file(job_id: str, filename: str) -> Response:
    """결과 파일 다운로드."""
    job = _jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    file_path = Path(job["work_dir"]) / filename
    if not file_path.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(file_path, filename=filename)


# ---------------------------------------------------------------------------
# WebSocket — 메쉬 생성 + 실시간 진행상황
# ---------------------------------------------------------------------------


@app.websocket("/ws/mesh/{job_id}")
async def websocket_mesh(websocket: WebSocket, job_id: str) -> None:
    """메쉬 생성 WebSocket. 진행상황을 실시간 스트리밍한다.

    Protocol:
        Client → Server: {"action": "start", "quality": "draft", "tier": "auto"}
        Server → Client: {"type": "progress", "stage": "analyze", "progress": 0.2, "message": "..."}
        Server → Client: {"type": "result", "success": true, "verdict": "PASS", ...}
        Server → Client: {"type": "error", "message": "..."}
    """
    await websocket.accept()
    log.info("ws_connected", job_id=job_id)

    job = _jobs.get(job_id)
    if not job:
        await websocket.send_json({"type": "error", "message": "Job not found"})
        await websocket.close()
        return

    try:
        # 클라이언트로부터 시작 명령 대기
        data = await websocket.receive_json()
        action = data.get("action")

        if action == "start":
            quality = data.get("quality", "standard")
            tier = data.get("tier", "auto")
            max_iterations = data.get("max_iterations", 3)

            await _run_mesh_pipeline(
                websocket, job, quality, tier, max_iterations
            )
        else:
            await websocket.send_json({"type": "error", "message": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        log.info("ws_disconnected", job_id=job_id)
    except Exception as exc:
        log.error("ws_error", job_id=job_id, error=str(exc))
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass


async def _run_mesh_pipeline(
    ws: WebSocket,
    job: dict[str, Any],
    quality: str,
    tier: str,
    max_iterations: int,
) -> None:
    """메쉬 생성 파이프라인을 실행하며 진행상황을 WebSocket으로 전달한다."""
    from core.pipeline.orchestrator import PipelineOrchestrator

    job["status"] = "running"
    input_path = Path(job["input_path"])
    output_dir = Path(job["work_dir"]) / "case"

    async def send_progress(stage: str, progress: float, message: str = "") -> None:
        job["stage"] = stage
        job["progress"] = progress
        job["message"] = message
        await ws.send_json({
            "type": "progress",
            "stage": stage,
            "progress": progress,
            "message": message,
        })

    await send_progress("init", 0.0, "파이프라인 초기화")

    # 동기 파이프라인을 별도 스레드에서 실행
    loop = asyncio.get_event_loop()

    # 진행 콜백을 위한 단계별 실행
    orchestrator = PipelineOrchestrator()

    # 각 단계를 개별 실행하여 진행상황 전달
    try:
        # 1. Analyze
        await send_progress("analyze", 0.1, "지오메트리 분석 중...")
        geometry_report = await loop.run_in_executor(
            None, orchestrator._analyzer.analyze, input_path
        )

        # 2. Preprocess
        await send_progress("preprocess", 0.3, "표면 전처리 중...")
        work_dir = output_dir / "_work"
        work_dir.mkdir(parents=True, exist_ok=True)

        def _preprocess() -> tuple[Path, Any]:
            return orchestrator._preprocessor.run(
                input_path=input_path,
                geometry_report=geometry_report,
                output_dir=work_dir,
            )

        preprocessed_path, preprocessed_report = await loop.run_in_executor(None, _preprocess)

        # 3. Strategize
        await send_progress("strategize", 0.4, f"전략 수립 중... (quality={quality})")

        def _strategize() -> Any:
            return orchestrator._planner.plan(
                geometry_report=geometry_report,
                preprocessed_report=preprocessed_report,
                tier_hint=tier,
                quality_level=quality,
            )

        strategy = await loop.run_in_executor(None, _strategize)

        await ws.send_json({
            "type": "strategy",
            "selected_tier": strategy.selected_tier,
            "quality_level": str(strategy.quality_level),
            "cell_size": strategy.surface_mesh.target_cell_size,
        })

        # 4. Generate + Evaluate loop
        for iteration in range(1, max_iterations + 1):
            progress_base = 0.5 + (iteration - 1) * 0.15
            await send_progress(
                "generate",
                progress_base,
                f"메쉬 생성 중... (iteration {iteration}/{max_iterations})",
            )

            def _generate() -> Any:
                return orchestrator._generator.run(strategy, preprocessed_path, output_dir)

            generator_log = await loop.run_in_executor(None, _generate)

            # 성공 tier 확인
            successful_tier = orchestrator._find_successful_tier(generator_log)
            if successful_tier is None:
                await ws.send_json({
                    "type": "result",
                    "success": False,
                    "message": "모든 Tier 실패",
                })
                job["status"] = "failed"
                job["error"] = "All tiers failed"
                return

            # Evaluate
            await send_progress(
                "evaluate",
                progress_base + 0.1,
                f"품질 검증 중... ({successful_tier})",
            )

            def _evaluate() -> Any:
                return orchestrator._evaluate(
                    case_dir=output_dir,
                    strategy=strategy,
                    iteration=iteration,
                    tier=successful_tier,
                    quality_level=quality,
                    preprocessed_path=preprocessed_path,
                    geometry_report=geometry_report,
                )

            quality_report = await loop.run_in_executor(None, _evaluate)

            verdict = quality_report.evaluation_summary.verdict
            cm = quality_report.evaluation_summary.checkmesh

            await ws.send_json({
                "type": "evaluation",
                "iteration": iteration,
                "verdict": verdict.value if hasattr(verdict, 'value') else str(verdict),
                "tier": successful_tier,
                "cells": cm.cells,
                "max_non_ortho": cm.max_non_orthogonality,
                "max_skewness": cm.max_skewness,
            })

            verdict_str = verdict.value if hasattr(verdict, 'value') else str(verdict)
            if verdict_str in ("PASS", "PASS_WITH_WARNINGS"):
                await send_progress("done", 1.0, f"완료! {verdict_str}")
                job["status"] = "completed"
                job["result"] = {
                    "success": True,
                    "verdict": verdict_str,
                    "cells": cm.cells,
                    "tier": successful_tier,
                    "output_dir": str(output_dir),
                }

                await ws.send_json({
                    "type": "result",
                    "success": True,
                    "verdict": verdict_str,
                    "cells": cm.cells,
                    "tier": successful_tier,
                    "max_non_ortho": cm.max_non_orthogonality,
                    "max_skewness": cm.max_skewness,
                    "output_dir": str(output_dir),
                })
                return

        # 모든 iteration 실패
        await ws.send_json({
            "type": "result",
            "success": False,
            "message": f"{max_iterations}회 반복 후 실패",
        })
        job["status"] = "failed"
        job["error"] = f"Failed after {max_iterations} iterations"

    except Exception as exc:
        log.error("pipeline_error", error=str(exc))
        job["status"] = "failed"
        job["error"] = str(exc)
        await ws.send_json({"type": "error", "message": str(exc)})


# ---------------------------------------------------------------------------
# Mesh data endpoint (for Godot 3D viewer)
# ---------------------------------------------------------------------------


@app.get("/jobs/{job_id}/mesh")
async def get_mesh_data(job_id: str) -> JSONResponse:
    """생성된 메쉬의 vertex/face 데이터를 JSON으로 반환 (Godot 3D 뷰어용)."""
    job = _jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    case_dir = Path(job["work_dir"]) / "case"
    try:
        from core.utils.polymesh_reader import parse_foam_points, parse_foam_faces, parse_foam_boundary, parse_foam_labels

        poly_dir = case_dir / "constant" / "polyMesh"
        points = parse_foam_points(poly_dir / "points")
        faces = parse_foam_faces(poly_dir / "faces")
        boundary = parse_foam_boundary(poly_dir / "boundary")

        # Boundary faces만 추출 (3D 뷰어용 — 내부 면은 불필요)
        boundary_faces = []
        for patch in boundary:
            start = patch["startFace"]
            n = patch["nFaces"]
            for i in range(start, start + n):
                if i < len(faces):
                    boundary_faces.append(faces[i])

        return JSONResponse({
            "points": points,
            "boundary_faces": boundary_faces,
            "patches": boundary,
            "num_cells": int(max(
                parse_foam_labels(poly_dir / "owner") if (poly_dir / "owner").exists() else [0]
            )) + 1 if (poly_dir / "owner").exists() else 0,
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/jobs/{job_id}/surface")
async def get_surface_stl(job_id: str) -> Response:
    """전처리된 표면 STL 파일 반환 (Godot 3D 뷰어용)."""
    job = _jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    work_dir = Path(job["work_dir"])
    stl_path = work_dir / "case" / "_work" / "preprocessed.stl"
    if not stl_path.exists():
        # 원본 입력 파일 반환
        stl_path = Path(job.get("input_path", ""))
    if not stl_path.exists():
        return JSONResponse({"error": "Surface file not found"}, status_code=404)

    return FileResponse(stl_path, filename="surface.stl", media_type="application/octet-stream")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import uvicorn
    import sys

    port = 9720
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])

    print(f"Auto-Tessell Desktop Server starting on http://localhost:{port}")
    print(f"  WebSocket: ws://localhost:{port}/ws/mesh/{{job_id}}")
    print(f"  Health:    http://localhost:{port}/health")

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
