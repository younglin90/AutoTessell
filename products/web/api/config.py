from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database — use sqlite:///./tessell.db for local dev without PostgreSQL
    database_url: str = "postgresql://postgres:postgres@db:5432/tessell"

    # Redis / Celery — ignored when dev_mode=true (tasks run in-process)
    redis_url: str = "redis://redis:6379/0"

    # Dev mode: local file storage + synchronous Celery (no S3/Redis/Stripe needed)
    dev_mode: bool = False
    dev_storage_path: str = "./dev_storage"

    # S3
    s3_bucket: str = "auto-tessell-jobs"
    s3_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # App
    mesh_price_cents: int = 500  # $5.00 per job
    max_stl_size_bytes: int = 100 * 1024 * 1024  # 100 MB
    max_jobs_per_user: int = 2
    job_timeout_seconds: int = 600  # 10 min hard kill
    job_soft_timeout_seconds: int = 540  # 9 min soft kill
    worker_concurrency: int = 4

    # CORS — comma-separated origins (e.g. "http://localhost:3000,https://app.tessell.io")
    cors_origins: str = "http://localhost:3000"

    # Dev mode: base URL used for mesh download links (overrides hardcoded localhost)
    dev_api_base_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"


settings = Settings()
