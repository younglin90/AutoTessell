from __future__ import annotations

import copy
from collections import defaultdict
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.preprocessor.native_tri.cad_stl_authority_ingress import (
    make_external_trust_anchor,
    semantic_ledger_from_faces,
    validate_native_tri_authority_source,
)
from core.preprocessor.native_tri.wall_edge_bl_preflight import (
    make_external_edge_trust_anchor,
    validate_native_tri_wall_edge_bl_preflight,
)


def _canonical_stl(path: Path) -> tuple[np.ndarray, np.ndarray]:
    mesh = read_stl(path, dedupe=False)
    point_ids: dict[tuple[float, float, float], int] = {}
    points: list[tuple[float, float, float]] = []
    for point in np.asarray(mesh.vertices, dtype=np.float64):
        key = tuple(0.0 if float(value) == 0.0 else float(value) for value in point)
        if key not in point_ids:
            point_ids[key] = len(points)
            points.append(key)
    faces: list[list[int]] = []
    for face in np.asarray(mesh.faces, dtype=np.int64):
        faces.append(
            [
                point_ids[
                    tuple(
                        0.0 if float(value) == 0.0 else float(value)
                        for value in mesh.vertices[int(vertex)]
                    )
                ]
                for vertex in face
            ]
        )
    return np.asarray(points, dtype=np.float64), np.asarray(faces, dtype=np.int64)


def _fixture() -> tuple[Path, np.ndarray, np.ndarray, dict, list[dict]]:
    source = Path("tests/benchmarks/cube.stl")
    points, faces = _canonical_stl(source)
    face_ledger = semantic_ledger_from_faces(
        faces,
        feature="cube-surface",
        patch="cube-wall",
        physical_group="cube-fluid-wall",
        component="cube",
        provenance="registered-release-stl-facet",
    )
    source_trust = make_external_trust_anchor(
        source, face_ledger, issuer="tri-wall-edge-registry", key_id="tri-edge-v1"
    )
    certificate = validate_native_tri_authority_source(
        source, face_ledger, source_trust, requested_layers=0
    )
    assert certificate["accepted"] is True, certificate

    occurrences: dict[tuple[int, int], list[tuple[int, int, int]]] = defaultdict(list)
    for face_id, face in enumerate(faces):
        for local in range(3):
            first = int(face[local])
            second = int(face[(local + 1) % 3])
            occurrences[tuple(sorted((first, second)))].append(
                (face_id, first, second)
            )
    base = faces[0]
    rows: list[dict] = []
    for local in range(3):
        first = int(base[local])
        second = int(base[(local + 1) % 3])
        incident = sorted(
            face_id
            for face_id, _from, _to in occurrences[tuple(sorted((first, second)))]
        )
        rows.append(
            {
                "edge_id": f"cube-wall-edge-{local}",
                "endpoint_vertex_ids": [first, second],
                "incident_face_ids": incident,
                "directed_sector_face_ids": incident,
                "directed_sector_ids": [f"sector-face-{face}" for face in incident],
                "wall_role": "wall",
                "patch_boundary_role": "cube-patch-boundary",
                "feature": "cube-surface",
                "patch": "cube-wall",
                "physical_group": "cube-fluid-wall",
                "component": "cube",
                "provenance": "registered-release-stl-facet",
            }
        )
    return source, points, faces, certificate, rows


def _anchor(
    certificate: dict,
    rows: list[dict],
    *,
    policy: str = "closed_nonbranching",
    endpoints: tuple[int, ...] = (),
) -> dict:
    return make_external_edge_trust_anchor(
        certificate,
        rows,
        loop_policy=policy,
        loop_endpoint_vertex_ids=endpoints,
        issuer="tri-wall-edge-registry",
        key_id="tri-edge-v1",
    )


def _assert_atomic_refusal(result: dict) -> None:
    assert result["accepted"] is False, result
    assert result["preflight_accepted"] is False
    assert result["actual_layers"] == 0
    assert result["writer_invoked"] is False
    assert result["artifact_emitted"] is False
    assert result["generated_vertices"] == []
    assert result["generated_faces"] == []
    assert result["provenance"] == []


def test_bl0_and_positive_preflight_are_deterministic_and_artifact_free():
    _source, _points, _faces, certificate, rows = _fixture()
    anchor = _anchor(certificate, rows)

    zero = validate_native_tri_wall_edge_bl_preflight(
        certificate, rows, anchor, requested_layers=0
    )
    assert zero["accepted"] is True, zero
    assert zero["status"] == "native_tri_wall_edge_bl_identity_sealed"
    assert zero["bl0_identity"] is True
    assert zero["edge_count"] == 3
    assert zero["layer_heights"] == []
    assert zero["release_eligible"] is False
    assert zero["generated_faces"] == []

    results = [
        validate_native_tri_wall_edge_bl_preflight(
            certificate, rows, anchor, requested_layers=layers,
            first_height=0.05, growth_ratio=1.2
        )
        for layers in (1, 3, 8)
        for _ in range(3)
    ]
    assert all(result["accepted"] for result in results), results
    assert all(result["preflight_accepted"] for result in results)
    assert all(result["status"] == "native_tri_wall_edge_bl_preflight_sealed"
               for result in results)
    assert {result["preflight_digest"] for result in results[0:3]}.__len__() == 1
    assert results[0]["layer_heights"] == pytest.approx([0.05])
    assert results[3]["layer_heights"] == pytest.approx([0.05, 0.06, 0.072])
    assert results[0]["actual_layers"] == 0
    assert results[0]["artifact_emitted"] is False
    assert results[0]["eligible_for_tri_bl"] is False


def test_explicit_open_loop_policy_is_bound_without_inference():
    _source, _points, _faces, certificate, rows = _fixture()
    open_rows = rows[:2]
    endpoints = (open_rows[0]["endpoint_vertex_ids"][0],
                 open_rows[-1]["endpoint_vertex_ids"][1])
    anchor = _anchor(
        certificate, open_rows, policy="open_nonbranching", endpoints=endpoints
    )
    result = validate_native_tri_wall_edge_bl_preflight(
        certificate, open_rows, anchor, requested_layers=1,
        first_height=0.02, growth_ratio=1.0
    )
    assert result["accepted"] is True, result
    assert result["loop_policy"] == "open_nonbranching"
    assert result["loop_endpoint_vertex_ids"] == list(endpoints)
    assert result["edge_count"] == 2


@pytest.mark.parametrize("case", ("hash", "reverse", "missing", "label", "sector", "height", "policy"))
def test_edge_authority_and_schedule_tamper_refuse_atomically(case: str):
    _source, _points, _faces, certificate, rows = _fixture()
    candidate = copy.deepcopy(rows)
    policy = "closed_nonbranching"
    endpoints: tuple[int, ...] = ()
    if case == "reverse":
        candidate[0]["endpoint_vertex_ids"].reverse()
        anchor = _anchor(certificate, rows)
    elif case == "missing":
        candidate = candidate[:-1]
        anchor = _anchor(certificate, candidate)
    elif case == "label":
        candidate[0]["feature"] = "forged-feature"
        anchor = _anchor(certificate, candidate)
    elif case == "sector":
        candidate[0]["directed_sector_face_ids"] = list(
            reversed(candidate[0]["directed_sector_face_ids"])
        )
        anchor = _anchor(certificate, candidate)
    elif case == "policy":
        anchor = _anchor(certificate, rows, policy="")
    else:
        anchor = _anchor(certificate, rows)
        if case == "hash":
            anchor["edge_ledger_sha256"] = "0" * 64
    result = validate_native_tri_wall_edge_bl_preflight(
        certificate,
        candidate,
        anchor,
        requested_layers=1,
        first_height=-0.01 if case == "height" else 0.05,
        growth_ratio=1.2,
    )
    _assert_atomic_refusal(result)


def test_source_certificate_tamper_refuses_before_edge_validation():
    _source, _points, _faces, certificate, rows = _fixture()
    forged = copy.deepcopy(certificate)
    forged["certificate"]["canonical_triangles"][0] = (0, 0, 0)
    anchor = _anchor(certificate, rows)
    result = validate_native_tri_wall_edge_bl_preflight(
        forged, rows, anchor, requested_layers=0
    )
    _assert_atomic_refusal(result)
