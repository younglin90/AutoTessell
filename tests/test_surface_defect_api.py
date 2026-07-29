"""Surface defect localization and revisioned repair API tests."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from core.utils.stl_writer import write_stl_binary
from desktop.server import _jobs, app


@pytest.fixture(autouse=True)
def clear_jobs() -> None:
    _jobs.clear()
    yield
    _jobs.clear()


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _upload_open_tetra(client: TestClient, tmp_path) -> str:
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2]], dtype=np.int64)
    path = tmp_path / "open_tetra.stl"
    assert write_stl_binary(vertices, faces, path).success
    response = client.post(
        "/upload",
        files={"file": (path.name, io.BytesIO(path.read_bytes()), "application/octet-stream")},
    )
    assert response.status_code == 200
    return response.json()["job_id"]


def test_localize_repair_and_revision_conflict(client: TestClient, tmp_path) -> None:
    job_id = _upload_open_tetra(client, tmp_path)
    entry = _jobs[job_id]["surfaces"][0]
    surface_id = entry["surface_id"]
    original_path = Path(entry["original_path"])
    original_bytes = original_path.read_bytes()

    report = client.get(f"/jobs/{job_id}/surfaces/{surface_id}/defects")
    assert report.status_code == 200
    payload = report.json()
    hole = next(item for item in payload["defects"] if item["type"] == "boundary_loop")
    assert payload["revision"] == 1
    assert len(payload["points"]) == 4
    assert len(payload["faces"]) == 3

    repaired = client.post(
        f"/jobs/{job_id}/surfaces/{surface_id}/repair",
        json={
            "defect_id": hole["defect_id"],
            "action": "fill_hole",
            "expected_revision": 1,
        },
    )
    assert repaired.status_code == 200, repaired.text
    assert repaired.json()["revision"] == 2
    assert repaired.json()["original_preserved"] is True
    assert original_path.read_bytes() == original_bytes
    assert entry["path"] != str(original_path)

    refreshed = client.get(f"/jobs/{job_id}/surfaces/{surface_id}/defects").json()
    assert refreshed["revision"] == 2
    assert len(refreshed["faces"]) == 4
    assert not any(item["type"] == "boundary_loop" for item in refreshed["defects"])

    stale = client.post(
        f"/jobs/{job_id}/surfaces/{surface_id}/repair",
        json={
            "defect_id": hole["defect_id"],
            "action": "fill_hole",
            "expected_revision": 1,
        },
    )
    assert stale.status_code == 409
