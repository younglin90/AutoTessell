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
import logging
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from core.utils.logging import configure_logging, get_logger, make_processor_formatter
from core.version import APP_VERSION
from desktop.default_env import apply_default_env

# On Korean/legacy Windows the console encoding defaults to cp949, which cannot
# encode characters the meshing pipeline prints/logs (em-dash, °, ·, …).  Force
# the process std streams to UTF-8 so a stray print() inside a worker thread
# never crashes the run with UnicodeEncodeError.
import sys as _sys  # noqa: E402

for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 — older/odd streams lack reconfigure
        pass

log = get_logger(__name__)

# Apply the same AUTO_TESSELL_* defaults the Qt desktop GUI uses so a mesh
# produced from the browser matches the Windows GUI bit-for-bit.  setdefault
# semantics → user/CI overrides still win.
apply_default_env()


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Start background tasks on startup."""
    _purge_stale_temp_dirs()
    task = asyncio.create_task(_cleanup_old_jobs())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Auto-Tessell Desktop", version=APP_VERSION, lifespan=_lifespan)

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

# CAD formats that need server-side tessellation to a preview STL (the browser
# STL parser cannot read them directly).
CAD_PREVIEW_EXTS = {".step", ".stp", ".iges", ".igs", ".brep"}

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


class _PipelineCancelled(BaseException):
    """Raised inside ``progress_callback`` to abort ``orchestrator.run()``.

    Must derive from ``BaseException`` (not ``Exception``): the orchestrator
    wraps the progress callback — and every pipeline stage — in
    ``except Exception``, so an ``Exception`` subclass would be swallowed and the
    run would continue. A ``BaseException`` slips past all those guards and
    propagates out of ``run()`` to the awaiting coroutine.
    """


_LEVEL_NAME_MAP = {
    "DEBUG": "debug", "INFO": "info", "WARNING": "warn",
    "ERROR": "error", "CRITICAL": "error",
}
_DETAIL_LOG_FORMATTER = make_processor_formatter(colors=False)


class _ThreadScopedLogHandler(logging.Handler):
    """Streams every ``structlog``/``logging`` record from ONE worker thread
    to the GUI, so the log panel shows the same engine-level detail (tier
    iterations, BL passes, per-iteration metrics, ...) the terminal already
    prints — not just the ~10 coarse stage-progress lines.

    Scoped by ``record.thread`` (the OS thread id), not a job id: two jobs
    running concurrently execute on two distinct worker threads (each
    ``run_in_executor`` callable runs start-to-finish on one thread), so
    filtering on thread id keeps their detail logs from crossing streams
    without needing contextvars propagation into the executor thread (which
    ``run_in_executor`` does not do).
    """

    def __init__(self, thread_id_box: dict[str, int | None], sink: Callable[[dict[str, Any]], None]):
        super().__init__()
        self._thread_id_box = thread_id_box
        self._sink = sink
        self.setFormatter(_DETAIL_LOG_FORMATTER)

    def emit(self, record: logging.LogRecord) -> None:
        wanted = self._thread_id_box.get("id")
        if wanted is None or record.thread != wanted:
            return
        try:
            text = self.format(record)
        except Exception:  # noqa: BLE001 — never let a bad record kill the run
            text = record.getMessage()
        level = _LEVEL_NAME_MAP.get(record.levelname, "info")
        self._sink({"type": "log", "level": level, "message": f"[Engine] {text}"})


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
        # Cooperative-cancellation flag, set by POST /jobs/{id}/cancel and
        # polled inside the pipeline progress callback.
        "cancel_event": threading.Event(),
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
    return {"status": "ok", "version": APP_VERSION}


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

    # CAD inputs (STEP/IGES/BREP) are not parseable by the browser's STL reader.
    # Tessellate to a preview STL at upload time so the viewer can show the
    # surface before a run.  Best-effort: never block the upload on failure.
    if ext in CAD_PREVIEW_EXTS:
        try:
            from core.analyzer.file_reader import load_mesh

            mesh = await asyncio.get_event_loop().run_in_executor(
                None, lambda: load_mesh(input_path)
            )
            preview_path = work_dir / "preview.stl"
            mesh.export(str(preview_path))
            job["preview_path"] = str(preview_path)
            log.info("cad_preview_generated", job_id=job["id"], path=str(preview_path))
        except Exception as exc:  # noqa: BLE001
            log.warning("cad_preview_failed", job_id=job["id"], error=str(exc))

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


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> JSONResponse:
    """실행 중인 작업을 협조적으로 취소한다.

    cancel_event 를 set 하면 다음 파이프라인 단계(progress_callback)에서
    _PipelineCancelled 가 발생해 orchestrator.run() 이 중단된다.
    """
    job = _jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    ev = job.get("cancel_event")
    if ev is not None:
        ev.set()
    _touch_job(job)
    log.info("job_cancel_requested", job_id=job_id, status=job.get("status"))
    return JSONResponse({"status": "cancelling", "job_id": job_id})


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


# Formats offered to the web GUI (subset of mesh_exporter.SupportedFormat that
# makes sense as a single downloadable file).
EXPORT_FORMATS: tuple[str, ...] = (
    "vtu", "vtk", "fluent", "cgns", "su2", "nastran", "tecplot", "stl", "obj", "ply",
)


@app.get("/jobs/{job_id}/export")
async def export_job_mesh(job_id: str, format: str = "vtu") -> Response:
    """생성된 polyMesh 를 요청한 CFD/시각화 포맷으로 변환해 다운로드한다.

    core.utils.mesh_exporter.export_mesh 를 재사용한다 (VTU/Fluent/CGNS/...).
    """
    job = _jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    fmt = (format or "vtu").lower()
    if fmt not in EXPORT_FORMATS:
        return JSONResponse(
            {"error": f"Unsupported format: {fmt}", "allowed": list(EXPORT_FORMATS)},
            status_code=400,
        )

    case_dir = Path(job["work_dir"]) / "case"
    if not (case_dir / "constant" / "polyMesh" / "points").exists():
        return JSONResponse(
            {"error": "polyMesh not found — mesh not yet generated"},
            status_code=404,
        )

    _touch_job(job)
    try:
        from core.utils.mesh_exporter import _FORMAT_EXTENSIONS, export_mesh

        ext = _FORMAT_EXTENSIONS.get(fmt, ".vtu")
        out_path = case_dir / f"mesh_{job_id}{ext}"
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: export_mesh(case_dir, out_path, fmt)  # type: ignore[arg-type]
        )
    except Exception as exc:  # noqa: BLE001
        log.error("export_failed", job_id=job_id, fmt=fmt, error=str(exc))
        return JSONResponse({"error": f"Export failed: {exc}"}, status_code=500)

    if not result or not Path(result).exists():
        return JSONResponse(
            {"error": f"Export produced no output for format '{fmt}'"},
            status_code=500,
        )
    log.info("mesh_exported_for_download", job_id=job_id, fmt=fmt, path=str(result))
    return FileResponse(Path(result), filename=Path(result).name)


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
            mesh_type = data.get("mesh_type", "auto")
            max_iterations = data.get("max_iterations", 1)

            # 추가 파라미터 (params_panel / 웹 GUI에서 전달)
            extra_params = {k: v for k, v in data.items()
                          if k not in ("action", "quality", "tier",
                                       "mesh_type", "max_iterations")}

            await _run_mesh_pipeline(
                websocket, job, quality, tier, max_iterations,
                extra_params, mesh_type=mesh_type,
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


def _build_run_kwargs(
    quality: str,
    tier: str,
    mesh_type: str,
    max_iterations: int,
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    """WebSocket start payload → ``orchestrator.run()`` 키워드 인자로 변환.

    Qt GUI 의 propagation 규칙과 동일하게 매핑한다 (CLAUDE.md v1.1):
    - Max Cells → max_cells kwarg + tier_specific_params['target_cells','max_cells']
    - BL layers → tier_specific_params['bl_layers','cfmesh_bl_n_layers']
    - 그 외 알 수 없는 키 → tier_specific_params 로 자동 머지.
    """
    extra = dict(extra or {})
    tsp: dict[str, Any] = {}

    try:
        n_iter = max(1, int(max_iterations))
    except (TypeError, ValueError):
        n_iter = 1

    kwargs: dict[str, Any] = {
        "quality_level": quality,
        "mesh_type": mesh_type,
        "tier_hint": tier,
        "max_iterations": n_iter,
        # >1 회 명시 시에만 자동 재시도 (기본은 off — CLAUDE.md 정책).
        "auto_retry": "continue" if n_iter > 1 else "off",
        "write_of_case": True,
    }

    def _pos_float(key: str) -> float | None:
        val = extra.get(key)
        try:
            f = float(val)
        except (TypeError, ValueError):
            return None
        return f if f > 0 else None

    def _pos_int(key: str) -> int | None:
        val = extra.get(key)
        try:
            i = int(float(val))
        except (TypeError, ValueError):
            return None
        return i if i > 0 else None

    # --- 셀 크기 ---
    es = _pos_float("element_size")
    if es is not None:
        kwargs["element_size"] = es
    bcs = _pos_float("base_cell_size")
    if bcs is not None:
        tsp["base_cell_size"] = bcs

    # --- 최대 셀 수 ---
    mc = _pos_int("max_cells")
    if mc is not None:
        kwargs["max_cells"] = mc
        tsp["max_cells"] = mc
        tsp["target_cells"] = mc

    # --- Boundary Layer ---
    bl = _pos_int("bl_layers")
    if bl is not None:
        tsp["bl_layers"] = bl
        tsp["cfmesh_bl_n_layers"] = bl

    # --- 불리언 플래그 ---
    if extra.get("no_repair"):
        kwargs["no_repair"] = True
    if extra.get("force_remesh") or extra.get("surface_remesh"):
        kwargs["surface_remesh"] = True
    if extra.get("allow_ai_fallback"):
        kwargs["allow_ai_fallback"] = True
    if extra.get("dry_run"):
        kwargs["dry_run"] = True

    # --- 엔진 선택 ---
    re_engine = extra.get("remesh_engine")
    if re_engine and re_engine != "auto":
        kwargs["remesh_engine"] = re_engine
    chk = extra.get("checker_engine")
    if chk and chk != "auto":
        kwargs["validator_engine"] = chk

    # --- 나머지 키 → tier_specific_params 자동 머지 ---
    _skip = {
        "action", "quality", "tier", "mesh_type", "max_iterations",
        "element_size", "base_cell_size", "max_cells", "bl_layers",
        "no_repair", "force_remesh", "surface_remesh", "allow_ai_fallback",
        "dry_run", "remesh_engine", "checker_engine", "repair_engine",
        "volume_engine", "postprocess_engine", "cad_engine", "export_vtk",
    }
    for k, v in extra.items():
        if k in _skip:
            continue
        if v is None or v == "" or v == 0:
            continue
        tsp[k] = v

    if tsp:
        kwargs["tier_specific_params"] = tsp
    return kwargs


async def _run_mesh_pipeline(
    ws: WebSocket,
    job: dict[str, Any],
    quality: str,
    tier: str,
    max_iterations: int,
    extra_params: dict[str, Any] | None = None,
    mesh_type: str = "auto",
) -> None:
    """메쉬 생성 파이프라인을 실행하며 진행상황을 WebSocket으로 전달한다.

    Qt GUI 와 동일한 ``orchestrator.run()`` 진입점을 사용해 mesh_type
    (tet / hex_dominant / poly) 별 BL·후처리까지 완전 parity 를 보장한다.
    파이프라인은 별도 스레드에서 동작하며, ``progress_callback`` 이
    스레드-세이프하게 WebSocket 으로 진행률을 push 한다.
    """
    from core.pipeline.orchestrator import PipelineOrchestrator

    job["status"] = "running"
    _touch_job(job)
    input_path = Path(job["input_path"])
    output_dir = Path(job["work_dir"]) / "case"
    loop = asyncio.get_event_loop()
    cancel_event: threading.Event = job.get("cancel_event") or threading.Event()
    cancel_event.clear()  # fresh start (job objects can be re-run)

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

    def _send_threadsafe(payload: dict[str, Any]) -> None:
        """worker 스레드의 progress_callback 에서 호출 — 이벤트 루프로 스케줄."""
        try:
            asyncio.run_coroutine_threadsafe(ws.send_json(payload), loop)
        except Exception:  # noqa: BLE001
            pass

    def progress_callback(percent: int, message: str) -> None:
        # Cooperative cancellation: this runs in the worker thread on every
        # pipeline stage.  Raising here aborts orchestrator.run() (see
        # _PipelineCancelled docstring for why it must be a BaseException).
        if cancel_event.is_set():
            raise _PipelineCancelled()
        frac = max(0.0, min(1.0, percent / 100.0))
        job["progress"] = frac
        job["stage"] = message
        job["message"] = message
        _send_threadsafe({
            "type": "progress",
            "stage": message,
            "progress": frac,
            "message": message,
        })
        _send_threadsafe({
            "type": "log",
            "level": "info",
            "message": f"[Server] {percent:3d}% · {message}",
        })

    await send_progress("init", 0.0, "파이프라인 초기화")
    await ws.send_json({
        "type": "log",
        "level": "info",
        "message": (
            f"[Server] mesh_type={mesh_type} quality={quality} "
            f"tier={tier} max_iter={max_iterations}"
        ),
    })

    run_kwargs = _build_run_kwargs(quality, tier, mesh_type, max_iterations, extra_params)
    orchestrator = PipelineOrchestrator()

    # Stream every engine-level log record (tier iterations, BL passes,
    # per-pass metrics, ...) emitted on the worker thread while it runs, so
    # the GUI log panel matches the terminal's detail instead of only the
    # ~10 coarse stage-progress lines from progress_callback.
    _thread_box: dict[str, int | None] = {"id": None}
    _detail_handler = _ThreadScopedLogHandler(_thread_box, _send_threadsafe)
    logging.getLogger().addHandler(_detail_handler)

    def _tracked_run() -> Any:
        _thread_box["id"] = threading.get_ident()
        return orchestrator.run(
            input_path, output_dir,
            progress_callback=progress_callback,
            **run_kwargs,
        )

    try:
        import time as _t
        _t0 = _t.perf_counter()
        try:
            result = await loop.run_in_executor(None, _tracked_run)
        finally:
            logging.getLogger().removeHandler(_detail_handler)
        elapsed = _t.perf_counter() - _t0
    except _PipelineCancelled:
        log.info("pipeline_cancelled", job_id=job["id"])
        job["status"] = "cancelled"
        job["error"] = "cancelled by user"
        _touch_job(job)
        try:
            await ws.send_json({"type": "log", "level": "warn",
                "message": "[Server] 사용자가 메쉬 생성을 취소했습니다."})
            await send_progress("cancelled", job.get("progress", 0.0), "취소됨")
        except Exception:
            pass
        await ws.send_json({
            "type": "result",
            "success": False,
            "verdict": "CANCELLED",
            "message": "사용자가 취소했습니다.",
        })
        return
    except Exception as exc:  # noqa: BLE001
        log.error("pipeline_error", error=str(exc))
        job["status"] = "failed"
        job["error"] = str(exc)
        _touch_job(job)
        try:
            await ws.send_json({"type": "log", "level": "error",
                "message": f"[Server] 파이프라인 에러: {exc}"})
        except Exception:
            pass
        await ws.send_json({"type": "error", "message": str(exc)})
        return

    # --- tier 시도 내역 로그 (성공/실패 사유를 브라우저 콘솔에 그대로) ---
    try:
        for _att in (result.generator_log.execution_summary.tiers_attempted or []):
            await ws.send_json({
                "type": "log",
                "level": "info" if _att.status == "success" else "warn",
                "message": f"[Server] {_att.tier}: {_att.status} ({_att.time_seconds:.1f}s)"
                + (f" — {(_att.error_message or '')[:120]}" if _att.error_message else ""),
            })
    except Exception:  # noqa: BLE001
        pass

    # --- 전략(strategy) 메시지 ---
    strategy = result.strategy
    selected_tier = getattr(strategy, "selected_tier", tier) if strategy else tier
    # 실제 성공한 tier 를 보고 (fallback 체인으로 다른 tier 가 성공했을 수 있음)
    try:
        for _att in (result.generator_log.execution_summary.tiers_attempted or []):
            if _att.status == "success":
                selected_tier = _att.tier
                break
    except Exception:  # noqa: BLE001 — generator_log 없으면 strategy 값 유지
        pass
    if strategy is not None:
        ql = getattr(strategy, "quality_level", quality)
        ql_str = ql.value if hasattr(ql, "value") else str(ql)
        mt = getattr(strategy, "mesh_type", mesh_type)
        mt_str = mt.value if hasattr(mt, "value") else str(mt)
        try:
            cell_size = float(strategy.surface_mesh.target_cell_size)
        except Exception:  # noqa: BLE001
            cell_size = 0.0
        await ws.send_json({
            "type": "strategy",
            "selected_tier": selected_tier,
            "quality_level": ql_str,
            "mesh_type": mt_str,
            "cell_size": cell_size,
        })

    # --- 평가(evaluation) + 결과(result) 메시지 ---
    qr = result.quality_report
    if qr is not None:
        cm = qr.evaluation_summary.checkmesh
        verdict = qr.evaluation_summary.verdict
        verdict_str = verdict.value if hasattr(verdict, "value") else str(verdict)
        await ws.send_json({
            "type": "evaluation",
            "iteration": result.iterations,
            "verdict": verdict_str,
            "tier": selected_tier,
            "cells": cm.cells,
            "max_non_ortho": cm.max_non_orthogonality,
            "max_skewness": cm.max_skewness,
            "max_aspect_ratio": cm.max_aspect_ratio,
        })
        await ws.send_json({"type": "log", "level": "info",
            "message": (
                f"[Server] 완료 {verdict_str}: {cm.cells} cells, "
                f"non-ortho={cm.max_non_orthogonality:.1f}°, "
                f"skew={cm.max_skewness:.2f}, "
                f"aspect={cm.max_aspect_ratio:.1f} ({elapsed:.1f}s)"
            )})
    else:
        verdict_str = "FAIL"
        cm = None

    if result.success:
        await send_progress("done", 1.0, f"완료! {verdict_str}")
        job["status"] = "completed"
        job["result"] = {
            "success": True,
            "verdict": verdict_str,
            "cells": cm.cells if cm else 0,
            "tier": selected_tier,
            "output_dir": str(output_dir),
        }
        _touch_job(job)
        await ws.send_json({
            "type": "result",
            "success": True,
            "verdict": verdict_str,
            "cells": cm.cells if cm else 0,
            "tier": selected_tier,
            "max_non_ortho": cm.max_non_orthogonality if cm else 0.0,
            "max_skewness": cm.max_skewness if cm else 0.0,
            "max_aspect_ratio": cm.max_aspect_ratio if cm else 0.0,
            "output_dir": str(output_dir),
        })
    else:
        job["status"] = "failed"
        job["error"] = result.error or "Mesh generation failed"
        _touch_job(job)
        await ws.send_json({
            "type": "result",
            "success": False,
            "verdict": verdict_str,
            "message": result.error or "메쉬 생성 실패",
            "tier": selected_tier,
        })


# ---------------------------------------------------------------------------
# Mesh data endpoint (for Godot 3D viewer)
# ---------------------------------------------------------------------------


def _per_face_quality(poly_dir: Path, raw_points: Any, raw_faces: Any) -> dict[str, list[float]] | None:
    """Per-GLOBAL-face non-orthogonality (deg) + skewness arrays.

    Reuses NativeMeshChecker's geometry helpers so the colours line up with the
    KPI numbers.  For boundary faces the "neighbour" is the face centre, so
    non-ortho = angle(face_centre - owner_centre, face_normal).  Returns arrays
    indexed by global face id, or None on any failure (caller omits quality).
    """
    try:
        import numpy as np

        from core.evaluator.native_checker import NativeMeshChecker
        from core.utils.polymesh_reader import parse_foam_labels

        owner = np.asarray(parse_foam_labels(poly_dir / "owner"), dtype=np.int64)
        nb_file = poly_dir / "neighbour"
        neighbour = (
            np.asarray(parse_foam_labels(nb_file), dtype=np.int64)
            if nb_file.exists() else np.asarray([], dtype=np.int64)
        )
        if neighbour.size:
            neighbour = neighbour[neighbour >= 0]
        points = np.asarray(raw_points, dtype=np.float64)

        chk = NativeMeshChecker()
        geom = chk._compute_face_geometry(points, raw_faces)
        if geom is not None:
            face_centres, face_normals, face_areas = geom
        else:
            face_centres = chk._compute_face_centres(points, raw_faces)
            face_normals, face_areas = chk._compute_face_normals_areas(points, raw_faces)

        n_cells = int(owner.max()) + 1 if owner.size else 0
        if neighbour.size:
            n_cells = max(n_cells, int(neighbour.max()) + 1)
        cell_centres = chk._compute_cell_centres_from_vertices(
            points, raw_faces, owner, n_cells, neighbour
        )

        d = face_centres - cell_centres[owner]                 # owner → face
        nrm = np.linalg.norm(face_normals, axis=1)
        n_hat = face_normals / np.clip(nrm[:, None], 1e-30, None)
        # orient normals owner-outward (match the checker)
        sign = np.sign(np.einsum("ij,ij->i", d, n_hat))
        sign[sign == 0] = 1.0
        n_hat *= sign[:, None]

        dn = np.clip(np.linalg.norm(d, axis=1), 1e-30, None)
        cosang = np.clip(np.einsum("ij,ij->i", d, n_hat) / dn, -1.0, 1.0)
        non_ortho = np.degrees(np.arccos(cosang))
        # lateral offset of face centre from the owner→normal line, normalised
        # by face size → boundary skewness proxy (0 = perfectly orthogonal).
        d_perp = d - (np.einsum("ij,ij->i", d, n_hat))[:, None] * n_hat
        skew = np.linalg.norm(d_perp, axis=1) / np.sqrt(np.clip(face_areas, 1e-30, None))
        return {"non_ortho": non_ortho.tolist(), "skewness": skew.tolist()}
    except Exception as exc:  # noqa: BLE001
        log.warning("per_face_quality_failed", error=str(exc))
        return None


# Above this cell count we do not ship interior faces (payload would balloon);
# the slice UI then falls back to a boundary-only cutaway.
_SLICE_INTERNAL_CELL_CAP = 250_000


def _cell_shape_counts(
    faces: list[list[int]], owner: list[int], neighbour: list[int], n_cells: int
) -> dict[str, int]:
    """Classify each cell by its face-size signature (KPI hover breakdown).

    tet = 4 tri, hex = 6 quad, pyramid = 4 tri + 1 quad, prism = 2 tri + 3 quad;
    anything else counts as poly.
    """
    n_faces_of = [0] * n_cells
    n_tri_of = [0] * n_cells
    n_quad_of = [0] * n_cells

    def _add(cell: int, size: int) -> None:
        if 0 <= cell < n_cells:
            n_faces_of[cell] += 1
            if size == 3:
                n_tri_of[cell] += 1
            elif size == 4:
                n_quad_of[cell] += 1

    for i, f in enumerate(faces):
        sz = len(f)
        if i < len(owner):
            _add(owner[i], sz)
        if i < len(neighbour):
            _add(neighbour[i], sz)

    shapes = {"tet": 0, "hex": 0, "prism": 0, "pyramid": 0, "poly": 0}
    for c in range(n_cells):
        nf, t, q = n_faces_of[c], n_tri_of[c], n_quad_of[c]
        if nf == 4 and t == 4:
            shapes["tet"] += 1
        elif nf == 6 and q == 6:
            shapes["hex"] += 1
        elif nf == 5 and t == 2 and q == 3:
            shapes["prism"] += 1
        elif nf == 5 and t == 4 and q == 1:
            shapes["pyramid"] += 1
        else:
            shapes["poly"] += 1
    return shapes


def _cell_centroids(
    points: Any, faces: list[list[int]], owner: list[int],
    neighbour: list[int], n_cells: int,
) -> list[list[float]]:
    """Approx cell centers = mean of each cell's face centroids.

    Used by the viewer's crinkle-slice, which keeps/drops WHOLE cells by the
    side of the plane their centroid falls on (ParaView "Crinkle Clip").
    """
    import numpy as np

    pts = np.asarray(points, dtype=float)
    acc = np.zeros((n_cells, 3), dtype=float)
    cnt = np.zeros(n_cells, dtype=np.int64)
    n_int = len(neighbour)
    for fi, f in enumerate(faces):
        if not f:
            continue
        fc = pts[np.asarray(f, dtype=np.int64)].mean(axis=0)
        o = owner[fi] if fi < len(owner) else -1
        if 0 <= o < n_cells:
            acc[o] += fc
            cnt[o] += 1
        if fi < n_int:
            nb = neighbour[fi]
            if 0 <= nb < n_cells:
                acc[nb] += fc
                cnt[nb] += 1
    cnt = np.maximum(cnt, 1)
    return (acc / cnt[:, None]).tolist()


def _metric_hist(vals: Any, bins: int = 14) -> dict[str, Any] | None:
    """min/max + fixed-bin histogram for the KPI hover charts."""
    import numpy as np

    a = np.asarray(vals, dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return None
    lo, hi = float(a.min()), float(a.max())
    counts, _ = np.histogram(a, bins=bins, range=(lo, hi if hi > lo else lo + 1e-9))
    return {"min": lo, "max": hi, "counts": counts.tolist()}


@app.get("/jobs/{job_id}/mesh")
async def get_mesh_data(
    job_id: str, quality: int = 0, internal: int = 0
) -> JSONResponse:
    """생성된 메쉬의 vertex/face 데이터를 JSON으로 반환 (3D 뷰어용).

    quality=1 이면 boundary face 별 non-ortho/skewness 배열을 함께 반환한다
    (서버-side 실제 품질 컬러맵용 — boundary_faces 와 동일 순서).
    internal=1 이면 내부 면(interior faces)도 함께 반환한다 (뷰어 slice/cutaway
    가 내부 셀 구조를 드러내도록) — 단 셀 수가 상한을 넘으면 생략한다.
    """
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

        face_quality = _per_face_quality(poly_dir, points, faces) if quality else None

        # Boundary faces만 추출 (3D 뷰어용 — 내부 면은 불필요)
        boundary_faces = []
        boundary_face_ids: list[int] = []  # global face id, aligned to boundary_faces
        bf_non_ortho: list[float] = []
        bf_skew: list[float] = []
        for patch in boundary:
            start = patch["startFace"]
            n = patch["nFaces"]
            for i in range(start, start + n):
                if i < len(faces):
                    boundary_faces.append(faces[i])
                    boundary_face_ids.append(i)
                    if face_quality is not None and i < len(face_quality["non_ortho"]):
                        bf_non_ortho.append(face_quality["non_ortho"][i])
                        bf_skew.append(face_quality["skewness"][i])

        num_cells = int(max(
            parse_foam_labels(poly_dir / "owner") if (poly_dir / "owner").exists() else [0]
        )) + 1 if (poly_dir / "owner").exists() else 0

        resp: dict[str, Any] = {
            "points": points,
            "boundary_faces": boundary_faces,
            "patches": boundary,
            "num_cells": num_cells,
        }
        if face_quality is not None:
            resp["face_non_ortho"] = bf_non_ortho
            resp["face_skewness"] = bf_skew

        if quality:
            # KPI readout stats: counts, shape breakdowns, metric histograms.
            owner_l = (
                parse_foam_labels(poly_dir / "owner")
                if (poly_dir / "owner").exists() else []
            )
            neigh_l = (
                parse_foam_labels(poly_dir / "neighbour")
                if (poly_dir / "neighbour").exists() else []
            )
            face_shapes = {"tri": 0, "quad": 0, "poly": 0}
            for f in faces:
                k = len(f)
                face_shapes["tri" if k == 3 else "quad" if k == 4 else "poly"] += 1

            aspect_hist = None
            try:
                import numpy as np

                from core.evaluator.native_checker import NativeMeshChecker

                _, cell_ars = NativeMeshChecker._per_cell_aspect_ratios(
                    np.asarray(points, dtype=np.float64),
                    faces,
                    np.asarray(owner_l, dtype=np.int64),
                    num_cells,
                    len(neigh_l),
                )
                aspect_hist = _metric_hist(cell_ars)
            except Exception as exc:  # noqa: BLE001
                log.warning("aspect_ratio_stats_failed", error=str(exc))

            resp["stats"] = {
                "n_points": len(points),
                "n_faces": len(faces),
                "n_cells": num_cells,
                "cell_shapes": _cell_shape_counts(faces, owner_l, neigh_l, num_cells),
                "face_shapes": face_shapes,
                "non_ortho": _metric_hist(face_quality["non_ortho"])
                if face_quality else None,
                "skewness": _metric_hist(face_quality["skewness"])
                if face_quality else None,
                "aspect_ratio": aspect_hist,
            }

        if internal:
            # OpenFOAM orders faces as [interior 0..nInternalFaces) then boundary].
            # nInternalFaces == number of entries in the neighbour file.
            nb_file = poly_dir / "neighbour"
            n_internal = 0
            if nb_file.exists():
                n_internal = len(parse_foam_labels(nb_file))
            if 0 < num_cells <= _SLICE_INTERNAL_CELL_CAP:
                resp["internal_faces"] = faces[:n_internal]
                resp["internal_available"] = True
                # crinkle-slice data: whole-cell classification needs cell
                # centroids + which cell each face belongs to.
                owner_l = parse_foam_labels(poly_dir / "owner") if (poly_dir / "owner").exists() else []
                neigh_l = parse_foam_labels(poly_dir / "neighbour") if (poly_dir / "neighbour").exists() else []
                resp["cell_centroids"] = _cell_centroids(
                    points, faces, owner_l, neigh_l, num_cells
                )
                resp["boundary_cells"] = [
                    owner_l[i] if i < len(owner_l) else -1 for i in boundary_face_ids
                ]
                resp["internal_owner"] = owner_l[:n_internal]
                resp["internal_neighbour"] = neigh_l[:n_internal]
            else:
                resp["internal_faces"] = []
                resp["internal_available"] = num_cells == 0  # unknown → let client try
        return JSONResponse(resp)
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
    input_path = Path(job.get("input_path", ""))
    input_ext = input_path.suffix.lower()
    # Preference order: preprocessed surface (post-run) → CAD preview STL
    # (generated at upload for STEP/IGES) → raw input *only if it's an STL*.
    candidates = [
        work_dir / "case" / "_work" / "preprocessed.stl",
        work_dir / "preview.stl",
    ]
    if input_ext == ".stl":
        candidates.append(input_path)
    stl_path = next((p for p in candidates if p and p.exists()), None)
    if stl_path is None:
        # Never hand the raw CAD/non-STL file to the browser STL parser — it
        # would feed it garbage.  Return a clear 404 the client can surface.
        if input_ext in CAD_PREVIEW_EXTS:
            msg = "CAD 미리보기를 생성할 수 없습니다 (OCP/cadquery/gmsh 미설치). 메쉬 생성 후 결과 메쉬를 볼 수 있습니다."
        else:
            msg = "Surface preview not available for this format yet."
        return JSONResponse({"error": msg}, status_code=404)

    return FileResponse(stl_path, filename="surface.stl", media_type="application/octet-stream")


# ---------------------------------------------------------------------------
# Demo data — curated sample meshes bundled with the repo, so a first-time
# user can try the full pipeline with one click (no file needed).
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEMOS: dict[str, dict[str, str]] = {
    "cube": {
        "file": "tests/stl/01_easy_cube.stl",
        "name": "demo_cube.stl",
        "label": "큐브",
        "hint": "가장 단순한 watertight 육면체 · 빠른 확인용",
    },
    "cylinder": {
        "file": "tests/benchmarks/cylinder.stl",
        "name": "demo_cylinder.stl",
        "label": "실린더",
        "hint": "닫힌 solid 원기둥 · 곡면 표면 리메쉬 확인용",
    },
    "bracket": {
        "file": "tests/stl/03_hard_bracket.stl",
        "name": "demo_bracket.stl",
        "label": "브래킷",
        "hint": "기계 부품형 CAD · 특징선/구멍 포함",
    },
}


@app.get("/demos")
async def list_demos() -> Response:
    """설치본에 포함된 데모 메쉬 목록 (파일 존재하는 것만)."""
    items = [
        {"key": k, "label": v["label"], "hint": v["hint"], "name": v["name"]}
        for k, v in _DEMOS.items()
        if (_REPO_ROOT / v["file"]).is_file()
    ]
    return JSONResponse({"demos": items})


@app.get("/demos/{key}")
async def get_demo(key: str) -> Response:
    """데모 메쉬 바이트 반환 — 프런트가 File로 감싸 업로드 경로로 재사용한다."""
    meta = _DEMOS.get(key)
    if not meta:
        return JSONResponse({"error": "Unknown demo"}, status_code=404)
    path = _REPO_ROOT / meta["file"]
    if not path.is_file():
        return JSONResponse({"error": "Demo file missing"}, status_code=404)
    return FileResponse(
        path, filename=meta["name"], media_type="application/octet-stream"
    )


# ---------------------------------------------------------------------------
# Static web GUI (single-page app)
# ---------------------------------------------------------------------------
# Mounted LAST so the explicit API routes above (/health, /upload, /jobs/*,
# /ws/*) always take precedence; the catch-all StaticFiles mount only serves
# the SPA shell and its assets.  ``html=True`` serves ``index.html`` at "/".
class _NoCacheStatic(StaticFiles):
    """Serve SPA assets with ``no-cache`` so edits always show on reload.

    This is a local desktop tool — HTTP caching of ``styles.css``/``app.js``
    buys nothing but stale-asset confusion during live UI iteration.
    """

    def file_response(self, *args: object, **kwargs: object) -> object:
        resp = super().file_response(*args, **kwargs)  # type: ignore[arg-type]
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp


_WEB_DIR = Path(__file__).resolve().parent / "web"
if _WEB_DIR.is_dir():
    app.mount("/", _NoCacheStatic(directory=str(_WEB_DIR), html=True), name="web")
    log.info("web_gui_mounted", directory=str(_WEB_DIR))
else:  # pragma: no cover
    log.warning("web_gui_dir_missing", directory=str(_WEB_DIR))


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

    # Root-logger-based, not at module import time (would clobber pytest's
    # caplog handler for every test that merely imports this module). Without
    # this, structlog runs on its stock PrintLogger default — never touches
    # `logging.getLogger()` at all — so the GUI's per-run detail-log handler
    # (which attaches to the root logger) silently receives nothing, even
    # though the terminal still looks fine (PrintLogger prints on its own).
    configure_logging(verbose=True, json=False)

    port = 9720
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])

    # Electron 셸은 이미 빈 포트를 스캔해 넘겨준다 — 그 경우 근처에서 리슨 중인
    # 프로세스(강제종료 후 남은 고아 서버 등)를 taskkill 하면 연쇄 킬이 된다.
    import os as _os
    if _os.environ.get("AUTO_TESSELL_SKIP_PORT_KILL", "0") != "1":
        _kill_existing(port)

    print(f"Auto-Tessell Server starting on http://localhost:{port}")
    print(f"  Web GUI:   http://localhost:{port}/        ← open this in a browser")
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
