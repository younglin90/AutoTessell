"""
Integration tests for FastAPI HTTP endpoints.

Uses FastAPI TestClient with an in-memory SQLite database.
Stripe, S3, and background mesh tasks are patched.
"""
import io
import json
import struct
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# App setup — override settings before importing app
# ---------------------------------------------------------------------------

import config as _cfg
_cfg.settings.dev_mode = True
_cfg.settings.database_url = "sqlite:///:memory:"
_cfg.settings.dev_storage_path = "/tmp/tessell_test"
_cfg.settings.max_jobs_per_user = 10

# Re-bind the DB engine to in-memory SQLite
import db as _db
from sqlalchemy import create_engine as _ce

_TEST_ENGINE = _ce(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(bind=_TEST_ENGINE)
_db.engine = _TEST_ENGINE
_db.SessionLocal = _TestSession

from main import app
from db import get_db, Base, Job, JobStatus


def override_get_db():
    s = _TestSession()
    try:
        yield s
    finally:
        s.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.create_all(bind=_TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=_TEST_ENGINE)


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stl() -> bytes:
    """Minimal binary STL (1 triangle)."""
    header = b"\x00" * 80
    count = struct.pack("<I", 1)
    tri = struct.pack("<3f", 0, 0, 1)        # normal
    tri += struct.pack("<3f", 0, 0, 0)       # v1
    tri += struct.pack("<3f", 1, 0, 0)       # v2
    tri += struct.pack("<3f", 0, 1, 0)       # v3
    tri += b"\x00\x00"
    return header + count + tri


def _upload(client, *, user_id="u1", target_cells=100_000, mesh_purpose="cfd",
            mesh_params=None, stl=None):
    params = {"user_id": user_id, "target_cells": target_cells,
              "mesh_purpose": mesh_purpose}
    if mesh_params:
        params["mesh_params"] = json.dumps(mesh_params)
    with patch("api.upload._run_mesh_background"):
        return client.post(
            "/api/v1/upload",
            params=params,
            files={"file": ("test.stl", io.BytesIO(stl or _make_stl()),
                            "application/octet-stream")},
        )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_200(self, client):
        assert client.get("/health").status_code == 200

    def test_dev_mode_flag(self, client):
        r = client.get("/health").json()
        assert r["dev_mode"] is True

    def test_db_ok(self, client):
        r = client.get("/health").json()
        assert r["db"] is True


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

class TestUpload:
    def test_returns_200(self, client):
        assert _upload(client).status_code == 200

    def test_returns_uuid_job_id(self, client):
        job_id = _upload(client).json()["job_id"]
        assert len(job_id) == 36
        assert job_id.count("-") == 4

    def test_client_secret_is_dev_mode(self, client):
        assert _upload(client).json()["client_secret"] == "dev_mode"

    def test_amount_cents_zero(self, client):
        assert _upload(client).json()["amount_cents"] == 0

    def test_non_stl_extension_rejected(self, client):
        with patch("api.upload._run_mesh_background"):
            r = client.post(
                "/api/v1/upload",
                params={"user_id": "u1"},
                files={"file": ("test.obj", io.BytesIO(b"v 0 0 0"), "text/plain")},
            )
        assert r.status_code == 400

    def test_empty_file_rejected(self, client):
        with patch("api.upload._run_mesh_background"):
            r = client.post(
                "/api/v1/upload",
                params={"user_id": "u1"},
                files={"file": ("test.stl", io.BytesIO(b""), "application/octet-stream")},
            )
        assert r.status_code == 400

    def test_target_cells_stored(self, client):
        job_id = _upload(client, target_cells=777_000).json()["job_id"]
        db = _TestSession()
        job = db.query(Job).filter(Job.id == job_id).first()
        assert job.target_cells == 777_000
        db.close()

    def test_mesh_purpose_stored(self, client):
        job_id = _upload(client, mesh_purpose="fea").json()["job_id"]
        db = _TestSession()
        job = db.query(Job).filter(Job.id == job_id).first()
        assert job.mesh_purpose == "fea"
        db.close()

    def test_valid_pro_params_accepted(self, client):
        r = _upload(client, mesh_params={"tet_stop_energy": 3.0})
        assert r.status_code == 200

    def test_invalid_pro_params_json_rejected(self, client):
        with patch("api.upload._run_mesh_background"):
            r = client.post(
                "/api/v1/upload",
                params={"user_id": "u1", "mesh_params": "{{invalid"},
                files={"file": ("test.stl", io.BytesIO(_make_stl()),
                                "application/octet-stream")},
            )
        assert r.status_code == 400

    def test_pro_params_stored_as_json(self, client):
        params = {"tet_stop_energy": 4.5, "mmg_enabled": False}
        job_id = _upload(client, mesh_params=params).json()["job_id"]
        db = _TestSession()
        job = db.query(Job).filter(Job.id == job_id).first()
        stored = json.loads(job.mesh_params_json)
        assert stored["tet_stop_energy"] == 4.5
        db.close()

    def test_job_starts_as_paid_in_dev(self, client):
        job_id = _upload(client).json()["job_id"]
        db = _TestSession()
        job = db.query(Job).filter(Job.id == job_id).first()
        assert job.status == JobStatus.PAID
        db.close()


# ---------------------------------------------------------------------------
# Jobs status
# ---------------------------------------------------------------------------

class TestJobList:
    def test_empty_list(self, client):
        r = client.get("/api/v1/jobs", params={"user_id": "nobody"})
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_own_jobs(self, client):
        _upload(client, user_id="list_user")
        _upload(client, user_id="list_user")
        r = client.get("/api/v1/jobs", params={"user_id": "list_user"}).json()
        assert len(r) == 2

    def test_does_not_return_other_users_jobs(self, client):
        _upload(client, user_id="alice_l")
        _upload(client, user_id="bob_l")
        r = client.get("/api/v1/jobs", params={"user_id": "alice_l"}).json()
        assert len(r) == 1

    def test_newest_first(self, client):
        j1 = _upload(client, user_id="order_user").json()["job_id"]
        j2 = _upload(client, user_id="order_user").json()["job_id"]
        items = client.get("/api/v1/jobs", params={"user_id": "order_user"}).json()
        assert items[0]["job_id"] == j2  # newest first

    def test_item_has_expected_fields(self, client):
        _upload(client, user_id="fields_user", target_cells=222_000, mesh_purpose="fea")
        item = client.get("/api/v1/jobs", params={"user_id": "fields_user"}).json()[0]
        assert item["stl_filename"] == "test.stl"
        assert item["target_cells"] == 222_000
        assert item["mesh_purpose"] == "fea"
        assert item["status"] == "PAID"
        assert "created_at" in item

    def test_has_pro_params_flag(self, client):
        _upload(client, user_id="pro_list", mesh_params={"tet_stop_energy": 3.0})
        item = client.get("/api/v1/jobs", params={"user_id": "pro_list"}).json()[0]
        assert item["has_pro_params"] is True

    def test_limit_default_20(self, client):
        import config as _cfg
        orig = _cfg.settings.max_jobs_per_user
        _cfg.settings.max_jobs_per_user = 100
        try:
            for _ in range(25):
                _upload(client, user_id="many_user")
        finally:
            _cfg.settings.max_jobs_per_user = orig
        items = client.get("/api/v1/jobs", params={"user_id": "many_user"}).json()
        assert len(items) == 20

    def test_custom_limit(self, client):
        for _ in range(5):
            _upload(client, user_id="limit_user")
        items = client.get("/api/v1/jobs", params={"user_id": "limit_user", "limit": 3}).json()
        assert len(items) == 3


class TestJobs:
    def test_get_own_job_200(self, client):
        job_id = _upload(client, user_id="alice").json()["job_id"]
        r = client.get(f"/api/v1/jobs/{job_id}", params={"user_id": "alice"})
        assert r.status_code == 200

    def test_get_other_users_job_404(self, client):
        job_id = _upload(client, user_id="alice").json()["job_id"]
        r = client.get(f"/api/v1/jobs/{job_id}", params={"user_id": "bob"})
        assert r.status_code == 404

    def test_nonexistent_job_404(self, client):
        r = client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000",
                       params={"user_id": "u1"})
        assert r.status_code == 404

    def test_echo_target_cells(self, client):
        job_id = _upload(client, target_cells=250_000).json()["job_id"]
        r = client.get(f"/api/v1/jobs/{job_id}", params={"user_id": "u1"}).json()
        assert r["target_cells"] == 250_000

    def test_echo_mesh_purpose(self, client):
        job_id = _upload(client, mesh_purpose="fea").json()["job_id"]
        r = client.get(f"/api/v1/jobs/{job_id}", params={"user_id": "u1"}).json()
        assert r["mesh_purpose"] == "fea"

    def test_echo_pro_params_json(self, client):
        params = {"tet_stop_energy": 7.0}
        job_id = _upload(client, mesh_params=params).json()["job_id"]
        r = client.get(f"/api/v1/jobs/{job_id}", params={"user_id": "u1"}).json()
        assert r["mesh_params_json"] is not None
        assert json.loads(r["mesh_params_json"])["tet_stop_energy"] == 7.0

    def test_result_fields_null_before_done(self, client):
        job_id = _upload(client).json()["job_id"]
        r = client.get(f"/api/v1/jobs/{job_id}", params={"user_id": "u1"}).json()
        assert r["result_num_cells"] is None
        assert r["result_tier"] is None


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _make_done_job(*, user_id="u1") -> str:
    """Insert a DONE job directly into the DB and return its ID."""
    import uuid
    from db import Job, JobStatus
    job_id = str(uuid.uuid4())
    db = _TestSession()
    job = Job(
        id=job_id,
        user_id=user_id,
        status=JobStatus.DONE,
        stl_s3_key="stl/test.stl",
        mesh_s3_key="meshes/test/mesh.zip",
        stl_filename="test.stl",
        amount_cents=0,
    )
    db.add(job)
    db.commit()
    db.close()
    return job_id


class TestDeleteJob:
    def test_delete_done_job_204(self, client):
        job_id = _make_done_job()
        r = client.delete(f"/api/v1/jobs/{job_id}", params={"user_id": "u1"})
        assert r.status_code == 204

    def test_deleted_job_not_found_after(self, client):
        job_id = _make_done_job()
        client.delete(f"/api/v1/jobs/{job_id}", params={"user_id": "u1"})
        r = client.get(f"/api/v1/jobs/{job_id}", params={"user_id": "u1"})
        assert r.status_code == 404

    def test_wrong_user_cannot_delete(self, client):
        job_id = _make_done_job(user_id="alice")
        r = client.delete(f"/api/v1/jobs/{job_id}", params={"user_id": "bob"})
        assert r.status_code == 404

    def test_active_job_cannot_be_deleted(self, client):
        job_id = _upload(client, user_id="u1").json()["job_id"]
        # PAID status
        r = client.delete(f"/api/v1/jobs/{job_id}", params={"user_id": "u1"})
        assert r.status_code == 409

    def test_nonexistent_job_404(self, client):
        r = client.delete("/api/v1/jobs/00000000-0000-0000-0000-000000000000",
                          params={"user_id": "u1"})
        assert r.status_code == 404


class TestDownload:
    def test_done_job_returns_200(self, client):
        job_id = _make_done_job()
        r = client.get(f"/api/v1/jobs/{job_id}/download", params={"user_id": "u1"})
        assert r.status_code == 200

    def test_done_job_returns_url(self, client):
        job_id = _make_done_job()
        r = client.get(f"/api/v1/jobs/{job_id}/download", params={"user_id": "u1"}).json()
        assert "url" in r
        assert "meshes/test/mesh.zip" in r["url"]

    def test_dev_mode_url_is_localhost(self, client):
        job_id = _make_done_job()
        r = client.get(f"/api/v1/jobs/{job_id}/download", params={"user_id": "u1"}).json()
        assert r["url"].startswith("http://localhost")

    def test_wrong_user_404(self, client):
        job_id = _make_done_job(user_id="alice")
        r = client.get(f"/api/v1/jobs/{job_id}/download", params={"user_id": "bob"})
        assert r.status_code == 404

    def test_non_done_status_409(self, client):
        job_id = _upload(client).json()["job_id"]  # status=PAID
        r = client.get(f"/api/v1/jobs/{job_id}/download", params={"user_id": "u1"})
        assert r.status_code == 409

    def test_nonexistent_job_404(self, client):
        r = client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000/download",
                       params={"user_id": "u1"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimit:
    def test_over_limit_returns_429(self, client):
        # max_jobs_per_user is set to 10 in test setup, lower it for this test
        import config as _cfg
        original = _cfg.settings.max_jobs_per_user
        _cfg.settings.max_jobs_per_user = 2
        try:
            _upload(client, user_id="heavy")
            _upload(client, user_id="heavy")
            r = _upload(client, user_id="heavy")
            assert r.status_code == 429
        finally:
            _cfg.settings.max_jobs_per_user = original

    def test_different_users_independent_limits(self, client):
        import config as _cfg
        original = _cfg.settings.max_jobs_per_user
        _cfg.settings.max_jobs_per_user = 1
        try:
            _upload(client, user_id="user_a")
            _upload(client, user_id="user_b")
            r_a = _upload(client, user_id="user_a")
            r_b = _upload(client, user_id="user_b")
            assert r_a.status_code == 429
            assert r_b.status_code == 429
        finally:
            _cfg.settings.max_jobs_per_user = original


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

def _build_webhook_payload(event_type: str, job_id: str, pi_id: str = "pi_test") -> dict:
    return {
        "type": event_type,
        "data": {
            "object": {
                "id": pi_id,
                "metadata": {"job_id": job_id},
            }
        },
    }


def _post_webhook(client, payload: dict):
    """Post a Stripe webhook with mocked signature verification."""
    import stripe as _stripe_module
    with patch.object(_stripe_module.Webhook, "construct_event", return_value=payload):
        return client.post(
            "/api/v1/webhook",
            content=json.dumps(payload),
            headers={"stripe-signature": "t=1,v1=fake"},
        )


class TestWebhook:
    def test_invalid_signature_returns_400(self, client):
        import stripe as _stripe_module
        # SignatureVerificationError is a real exception class (set in conftest)
        with patch.object(
            _stripe_module.Webhook, "construct_event",
            side_effect=_stripe_module.SignatureVerificationError("bad sig"),
        ):
            r = client.post(
                "/api/v1/webhook",
                content=b"{}",
                headers={"stripe-signature": "bad"},
            )
        assert r.status_code == 400

    def test_payment_succeeded_marks_job_paid(self, client):
        job_id = _upload(client).json()["job_id"]
        # Reset to PENDING to simulate pre-payment state
        db = _TestSession()
        job = db.query(Job).filter(Job.id == job_id).first()
        job.status = JobStatus.PENDING
        db.commit()
        db.close()

        with patch("api.payment.run_mesh") as mock_task:
            mock_task.apply_async = lambda **_kw: None
            _post_webhook(client, _build_webhook_payload("payment_intent.succeeded", job_id))

        db = _TestSession()
        job = db.query(Job).filter(Job.id == job_id).first()
        assert job.status == JobStatus.PAID
        db.close()

    def test_payment_failed_marks_job_failed(self, client):
        job_id = _upload(client).json()["job_id"]
        db = _TestSession()
        job = db.query(Job).filter(Job.id == job_id).first()
        job.status = JobStatus.PENDING
        db.commit()
        db.close()

        _post_webhook(client, _build_webhook_payload("payment_intent.payment_failed", job_id))

        db = _TestSession()
        job = db.query(Job).filter(Job.id == job_id).first()
        assert job.status == JobStatus.FAILED
        db.close()

    def test_unknown_event_returns_200(self, client):
        r = _post_webhook(client, {"type": "some.unknown.event", "data": {"object": {}}})
        assert r.status_code == 200

    def test_nonexistent_job_in_webhook_is_ignored(self, client):
        payload = _build_webhook_payload("payment_intent.succeeded", "00000000-0000-0000-0000-000000000000")
        with patch("api.payment.run_mesh") as mock_task:
            mock_task.apply_async = lambda **_kw: None
            r = _post_webhook(client, payload)
        assert r.status_code == 200  # logged + ignored, not an error
