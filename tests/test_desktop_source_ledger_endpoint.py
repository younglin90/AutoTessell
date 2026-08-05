from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from desktop.server import _create_job, _jobs, app


STL = b"""solid one
facet normal 0 0 1
 outer loop
  vertex 0 0 0
  vertex 1 0 0
  vertex 0 1 0
 endloop
endfacet
endsolid one
"""


def test_source_ledger_endpoint_returns_digest_bound_facet_namespace():
    _jobs.clear()
    with TestClient(app) as client:
        job = _create_job("plate.stl")
        path = Path(job["work_dir"]) / "plate.stl"
        path.write_bytes(STL)
        job["input_path"] = str(path)
        response = client.get(f"/jobs/{job['id']}/source-ledger")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_digest"] == payload["source"]["sha256"]
    assert payload["selector_namespaces"]["stl_facet"]["id_ranges"] == [[0, 0]]
    assert payload["selector_namespaces"]["physical_group"]["available"] is False
    _jobs.clear()
