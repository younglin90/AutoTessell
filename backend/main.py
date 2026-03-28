"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.download import router as download_router
from api.jobs import router as jobs_router
from api.payment import router as payment_router
from api.upload import router as upload_router
from db import create_tables

app = FastAPI(title="auto-tessell", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    create_tables()


app.include_router(upload_router, prefix="/api/v1")
app.include_router(payment_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(download_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
