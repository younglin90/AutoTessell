"""Focused API checks for explicit planar surface OpenFOAM padding export."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from desktop.server import _jobs, app


def _upload_planar_obj(client: TestClient) -> str:
    obj = b"v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3\nf 1 3 4\n"
    response = client.post(
        "/upload",
        files={"file": ("plane.obj", io.BytesIO(obj), "application/octet-stream")},
    )
    assert response.status_code == 200, response.text
    return response.json()["job_id"]


def test_selected_surface_exports_new_openfoam_zip() -> None:
    with TestClient(app) as client:
        job_id = _upload_planar_obj(client)
        source_path = _jobs[job_id]["surfaces"][0]["path"]
        surface_id = _jobs[job_id]["surfaces"][0]["surface_id"]

        def fake_export(vertices, faces, case_dir, **kwargs):
            poly = case_dir / "constant" / "polyMesh"
            poly.mkdir(parents=True)
            for name in ("points", "faces", "owner", "neighbour", "boundary"):
                (poly / name).write_text("0\n(\n)\n")
            return SimpleNamespace(model_dump=lambda mode: {"direction": kwargs["direction"]})

        with patch("core.utils.mesh_exporter.export_planar_surface_volume_to_openfoam", fake_export):
            response = client.get(
                f"/jobs/{job_id}/export/padded-openfoam?surface_id={surface_id}&direction=-1"
            )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "constant/polyMesh/points" in archive.namelist()
        assert "constant/polyMesh/faces" in archive.namelist()
    assert _jobs[job_id]["surfaces"][0]["path"] == source_path


def test_missing_native_padding_kernel_returns_503() -> None:
    with TestClient(app) as client:
        job_id = _upload_planar_obj(client)
        with patch(
            "core.utils.mesh_exporter.export_planar_surface_volume_to_openfoam",
            side_effect=RuntimeError("native_surface_padding is unavailable; build auto_tessell_core target native_surface_padding first"),
        ):
            response = client.get(f"/jobs/{job_id}/export/padded-openfoam")
    assert response.status_code == 503
    assert response.json()["build_target"] == "native_surface_padding"


def test_rejects_invalid_padding_direction() -> None:
    with TestClient(app) as client:
        job_id = _upload_planar_obj(client)
        response = client.get(f"/jobs/{job_id}/export/padded-openfoam?direction=0")
    assert response.status_code == 422


def test_native_tri_remesh_creates_surface_revision_without_volume_mesh() -> None:
    with TestClient(app) as client:
        job_id = _upload_planar_obj(client)
        entry = _jobs[job_id]["surfaces"][0]
        surface_id = entry["surface_id"]
        original_path = entry["path"]
        original_bytes = Path(original_path).read_bytes()

        def fake_remesh(source_path, output_path, request):
            assert str(source_path) == original_path
            output_path.write_bytes(b"native tri revised STL")
            return {
                "accepted": True,
                "diagnostics": {"gates": {"watertight": True}},
                "n_vertices": 4,
                "n_faces": 4,
            }

        with patch("desktop.server._native_tri_remesh_file", fake_remesh):
            response = client.post(
                f"/jobs/{job_id}/surfaces/{surface_id}/native-tri-remesh",
                json={"expected_revision": 1, "iterations": 2},
            )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["accepted"] is True
        assert data["revision"] == 2
        assert data["original_preserved"] is True
        assert Path(original_path).read_bytes() == original_bytes
        assert _jobs[job_id]["surfaces"][0]["path"] != original_path
        assert not (Path(_jobs[job_id]["work_dir"]) / "case" / "constant" / "polyMesh").exists()
