"""FastAPI application entry point."""

from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from api.download import router as download_router
from api.jobs import router as jobs_router
from api.payment import router as payment_router
from api.upload import router as upload_router
from config import settings
from db import create_tables

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(title="auto-tessell", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(upload_router, prefix="/api/v1")
app.include_router(payment_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(download_router, prefix="/api/v1")


@app.get("/api/v1/config")
def public_config():
    """Return public configuration needed by the frontend (no auth required)."""
    return {
        "mesh_price_cents": settings.mesh_price_cents,
        "max_stl_size_mb": settings.max_stl_size_bytes // (1024 * 1024),
        "max_jobs_per_user": settings.max_jobs_per_user,
        "dev_mode": settings.dev_mode,
    }


@app.get("/health")
def health():
    from sqlalchemy import text
    from db import SessionLocal
    db_ok = False
    try:
        with SessionLocal() as s:
            s.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    return {"status": "ok" if db_ok else "degraded", "db": db_ok, "dev_mode": settings.dev_mode}


if settings.dev_mode:
    @app.get("/dev/files/{path:path}")
    def serve_dev_file(path: str):
        """Serve local mesh files in dev mode (replaces S3 presigned URLs)."""
        storage_root = Path(settings.dev_storage_path).resolve()
        file_path = (storage_root / path).resolve()
        # Guard against path traversal (e.g. "../../etc/passwd").
        # is_relative_to() is robust to prefix confusion (e.g. /dev vs /dev2).
        if not file_path.is_relative_to(storage_root):
            raise HTTPException(status_code=400, detail="Invalid file path")
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(str(file_path), filename=file_path.name)
