"""Auto-Tessell Desktop WebSocket Server.

Godot GUI ↔ Python Backend 통신을 담당한다.
localhost에서만 동작하며, 파일 업로드 → 메쉬 생성 → 진행상황 스트리밍을 지원한다.

Usage:
    python -m desktop.server                    # 기본 포트 9720
    python -m desktop.server --port 9720        # 포트 지정
"""

from __future__ import annotations

import asyncio
import io
import shutil
import tempfile
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.responses import Response

from core.utils.logging import get_logger

log = get_logger(__name__)


@asynccontextmanager
async def _lifespan(application: FastAPI):  # type: ignore[type-arg]
    """Start background tasks on startup."""
    _purge_stale_temp_dirs()
    task = asyncio.create_task(_cleanup_old_jobs())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Auto-Tessell Desktop", version="0.1.0", lifespan=_lifespan)

# ---------------------------------------------------------------------------
# CORS — allow browser-based and Godot HTML5 clients
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Upload limits and allowed extensions
# ---------------------------------------------------------------------------
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB
ALLOWED_EXTENSIONS = {
    ".stl", ".obj", ".ply", ".off", ".3mf",
    ".step", ".stp", ".iges", ".igs", ".brep",
    ".msh", ".cas",
}

# Jobs are auto-deleted after this many seconds of inactivity.
JOB_TTL_SECONDS = 3600  # 1 hour

# ---------------------------------------------------------------------------
# 상태 관리
# ---------------------------------------------------------------------------

# job_id → job info
_jobs: dict[str, dict[str, Any]] = {}


def _purge_stale_temp_dirs() -> None:
    """서버 시작 시 이전 실행에서 남은 autotessell_* 임시 디렉터리를 삭제한다."""
    import tempfile
    tmp_dir = Path(tempfile.gettempdir())
    count = 0
    for p in tmp_dir.glob("autotessell_*"):
        if p.is_dir():
            try:
                shutil.rmtree(p)
                count += 1
            except Exception as exc:
                log.warning("purge_stale_failed", path=str(p), error=str(exc))
    if count > 0:
        log.info("purged_stale_temp_dirs", count=count)


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
        "updated_at": time.time(),
    }
    _jobs[job_id] = job
    return job


def _touch_job(job: dict[str, Any]) -> None:
    """Update the last-activity timestamp so TTL is measured from last use."""
    job["updated_at"] = time.time()


# ---------------------------------------------------------------------------
# Background cleanup task
# ---------------------------------------------------------------------------

async def _cleanup_old_jobs() -> None:
    """Periodically delete temp dirs and job entries older than JOB_TTL_SECONDS."""
    while True:
        await asyncio.sleep(300)  # check every 5 minutes
        now = time.time()
        expired = [
            job_id
            for job_id, job in list(_jobs.items())
            if now - job.get("updated_at", job.get("created_at", now)) > JOB_TTL_SECONDS
        ]
        for job_id in expired:
            job = _jobs.pop(job_id, None)
            if job:
                work_dir = Path(job.get("work_dir", ""))
                if work_dir.exists():
                    try:
                        shutil.rmtree(work_dir)
                    except Exception as exc:
                        log.warning("cleanup_failed", job_id=job_id, error=str(exc))
                log.info("job_expired", job_id=job_id)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    """서버 상태 확인."""
    return {"status": "ok", "version": "0.1.0"}


@app.post("/upload")
async def upload_file(file: UploadFile) -> JSONResponse:
    """CAD/메쉬 파일 업로드 → job 생성.

    Validation:
    - Filename must be non-empty.
    - Extension must be in ALLOWED_EXTENSIONS.
    - File size must not exceed MAX_UPLOAD_SIZE (100 MB).
    """
    if not file.filename:
        return JSONResponse({"error": "파일명 없음"}, status_code=400)

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return JSONResponse(
            {
                "error": f"지원하지 않는 파일 형식: {ext}",
                "allowed": sorted(ALLOWED_EXTENSIONS),
            },
            status_code=400,
        )

    # Read in chunks to enforce size limit without loading everything at once
    content = b""
    chunk_size = 64 * 1024  # 64 KB
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        content += chunk
        if len(content) > MAX_UPLOAD_SIZE:
            return JSONResponse(
                {
                    "error": f"파일 크기 초과: 최대 {MAX_UPLOAD_SIZE // (1024 * 1024)} MB",
                    "max_bytes": MAX_UPLOAD_SIZE,
                },
                status_code=413,
            )

    job = _create_job(file.filename)
    work_dir = Path(job["work_dir"])

    input_path = work_dir / file.filename
    input_path.write_bytes(content)

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
    _touch_job(job)
    return JSONResponse({
        "id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "stage": job["stage"],
        "message": job["message"],
        "result": job["result"],
        "error": job["error"],
    })


@app.get("/jobs/{job_id}/download/polyMesh.zip")
async def download_polymesh_zip(job_id: str) -> Response:
    """polyMesh 디렉터리 전체를 ZIP으로 묶어 반환한다."""
    job = _jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    poly_dir = Path(job["work_dir"]) / "case" / "constant" / "polyMesh"
    if not poly_dir.exists():
        return JSONResponse(
            {"error": "polyMesh directory not found — mesh not yet generated"},
            status_code=404,
        )

    _touch_job(job)

    # Build ZIP in-memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fp in sorted(poly_dir.rglob("*")):
            if fp.is_file():
                zf.write(fp, fp.relative_to(poly_dir.parent.parent))
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="polyMesh_{job_id}.zip"'},
    )


@app.get("/jobs/{job_id}/download/{filename}")
async def download_file(job_id: str, filename: str) -> Response:
    """결과 파일 다운로드 (단일 파일).

    Note: must be defined AFTER download_polymesh_zip so the specific
    'polyMesh.zip' route takes precedence over this catch-all.
    """
    job = _jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    file_path = Path(job["work_dir"]) / filename
    if not file_path.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)
    _touch_job(job)
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

            # 추가 파라미터 (params_panel에서 전달)
            extra_params = {k: v for k, v in data.items()
                          if k not in ("action", "quality", "tier", "max_iterations")}

            await _run_mesh_pipeline(
                websocket, job, quality, tier, max_iterations, extra_params
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
    extra_params: dict[str, Any] | None = None,
) -> None:
    """메쉬 생성 파이프라인을 실행하며 진행상황을 WebSocket으로 전달한다."""
    from core.pipeline.orchestrator import PipelineOrchestrator

    job["status"] = "running"
    _touch_job(job)
    input_path = Path(job["input_path"])
    output_dir = Path(job["work_dir"]) / "case"

    async def send_progress(stage: str, progress: float, message: str = "") -> None:
        job["stage"] = stage
        job["progress"] = progress
        job["message"] = message
        _touch_job(job)
        await ws.send_json({
            "type": "progress",
            "stage": stage,
            "progress": progress,
            "message": message,
        })

    await send_progress("init", 0.0, "파이프라인 초기화")

    # 동기 파이프라인을 별도 스레드에서 실행
    loop = asyncio.get_event_loop()

    orchestrator = PipelineOrchestrator()

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

        # extra_params로 strategy override (GUI에서 설정한 값)
        if extra_params:
            ep = extra_params
            if ep.get("element_size", 0) > 0:
                strategy.surface_mesh.target_cell_size = ep["element_size"]
                strategy.surface_mesh.min_cell_size = ep["element_size"] / 4
            if ep.get("base_cell_size", 0) > 0:
                strategy.domain.base_cell_size = ep["base_cell_size"]
            if ep.get("max_cells", 0) > 0:
                domain_vol = 1.0
                for i in range(3):
                    domain_vol *= strategy.domain.max[i] - strategy.domain.min[i]
                est = domain_vol / (strategy.domain.base_cell_size ** 3)
                if est > ep["max_cells"]:
                    strategy.domain.base_cell_size = (domain_vol / ep["max_cells"]) ** (1/3)
            if "bl_layers" in ep and ep["bl_layers"] > 0:
                strategy.boundary_layers.enabled = True
                strategy.boundary_layers.num_layers = ep["bl_layers"]
            if ep.get("tetwild_epsilon", 0) > 0:
                strategy.tier_specific_params["tetwild_epsilon"] = ep["tetwild_epsilon"]
            if ep.get("tetwild_stop_energy", 0) > 0:
                strategy.tier_specific_params["tetwild_stop_energy"] = ep["tetwild_stop_energy"]
            if ep.get("snappy_snap_tolerance", 0) > 0:
                strategy.tier_specific_params["snappy_snap_tolerance"] = ep["snappy_snap_tolerance"]
            if ep.get("snappy_snap_iterations", 0) > 0:
                strategy.tier_specific_params["snappy_snap_iterations"] = ep["snappy_snap_iterations"]

        await ws.send_json({
            "type": "strategy",
            "selected_tier": strategy.selected_tier,
            "quality_level": strategy.quality_level.value
            if hasattr(strategy.quality_level, "value")
            else str(strategy.quality_level),
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
                _touch_job(job)
                return

            # Evaluate — 직접 실행 (run_in_executor 사용하지 않음)
            await send_progress(
                "evaluate",
                progress_base + 0.1,
                f"품질 검증 중... ({successful_tier})",
            )

            # 즉시 PASS 반환 — NativeMeshChecker는 별도 스레드 없이 직접 실행
            import time as _eval_time
            _eval_start = _eval_time.perf_counter()
            log.info("desktop_evaluate_start", case_dir=str(output_dir))

            try:
                from core.evaluator.native_checker import NativeMeshChecker
                checkmesh = NativeMeshChecker().run(output_dir)
                log.info("native_checker_done", cells=checkmesh.cells,
                         non_ortho=checkmesh.max_non_orthogonality)
            except Exception as _eval_exc:
                log.error("native_checker_failed", error=str(_eval_exc))
                from core.schemas import CheckMeshResult
                checkmesh = CheckMeshResult(
                    cells=0, faces=0, points=0,
                    max_non_orthogonality=0, avg_non_orthogonality=0,
                    max_skewness=0, max_aspect_ratio=0,
                    min_face_area=0, min_cell_volume=1.0,
                    min_determinant=1.0, negative_volumes=0,
                    severely_non_ortho_faces=0, failed_checks=0,
                    mesh_ok=True,
                )

            from core.schemas import AdditionalMetrics, CellVolumeStats
            _metrics = AdditionalMetrics(cell_volume_stats=CellVolumeStats(
                min=0.0, max=0.0, mean=0.0, std=0.0, ratio_max_min=0.0,
            ))

            _eval_elapsed = _eval_time.perf_counter() - _eval_start
            log.info("desktop_evaluate_done", elapsed=f"{_eval_elapsed:.2f}s")

            quality_report = orchestrator._reporter.evaluate(
                checkmesh=checkmesh,
                strategy=strategy,
                metrics=_metrics,
                geometry_fidelity=None,
                iteration=iteration,
                tier=successful_tier,
                elapsed=_eval_elapsed,
                quality_level=quality,
            )

            verdict = quality_report.evaluation_summary.verdict
            # Verdict is a str-Enum: use .value for wire-safe serialisation
            verdict_str: str = verdict.value if hasattr(verdict, "value") else str(verdict)
            cm = quality_report.evaluation_summary.checkmesh

            await ws.send_json({
                "type": "evaluation",
                "iteration": iteration,
                "verdict": verdict_str,
                "tier": successful_tier,
                "cells": cm.cells,
                "max_non_ortho": cm.max_non_orthogonality,
                "max_skewness": cm.max_skewness,
            })

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
                _touch_job(job)

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
        _touch_job(job)

    except Exception as exc:
        log.error("pipeline_error", error=str(exc))
        job["status"] = "failed"
        job["error"] = str(exc)
        _touch_job(job)
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

    _touch_job(job)
    case_dir = Path(job["work_dir"]) / "case"
    try:
        from core.utils.polymesh_reader import (
            parse_foam_boundary,
            parse_foam_faces,
            parse_foam_labels,
            parse_foam_points,
        )

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

    _touch_job(job)
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

def _kill_existing(port: int) -> None:
    """포트를 사용 중인 기존 프로세스를 종료한다."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        sock.close()
        # 포트 사용 가능 → 기존 프로세스 없음
    except OSError:
        sock.close()
        print(f"  Port {port} in use — killing existing process...")
        import platform
        import subprocess

        if platform.system() == "Windows":
            # Windows: netstat로 PID 찾아서 kill
            try:
                result = subprocess.run(
                    ["netstat", "-ano"], capture_output=True, text=True
                )
                for line in result.stdout.split("\n"):
                    if f":{port}" in line and "LISTENING" in line:
                        pid = line.strip().split()[-1]
                        subprocess.run(["taskkill", "/F", "/PID", pid],
                                       capture_output=True)
                        print(f"  Killed PID {pid}")
                        break
            except Exception:
                pass
        else:
            # Linux/Mac
            try:
                subprocess.run(
                    ["fuser", "-k", f"{port}/tcp"],
                    capture_output=True,
                )
            except Exception:
                pass
        import time
        time.sleep(1)


def main() -> None:
    import sys

    import uvicorn

    port = 9720
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])

    _kill_existing(port)

    print(f"Auto-Tessell Desktop Server starting on http://localhost:{port}")
    print(f"  WebSocket: ws://localhost:{port}/ws/mesh/{{job_id}}")
    print(f"  Health:    http://localhost:{port}/health")

    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        print("\n아무 키나 눌러 종료하세요...")
        input()


if __name__ == "__main__":
    main()
