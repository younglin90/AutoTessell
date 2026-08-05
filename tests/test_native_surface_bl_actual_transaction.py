from __future__ import annotations

import numpy as np

from core.evaluator.native_surface_bl_actual_transaction import (
    seal_authoritative_surface_bl_transaction,
)
from core.evaluator.native_surface_bl_strip_writer import (
    write_authoritative_surface_wall_edge_strip,
)


def _authority() -> dict[str, str]:
    return {
        "source_kind": "synthetic_surface",
        "source_sha256": "source-digest",
        "boundary_mapping_sha256": "boundary-digest",
        "physical_group_sha256": "group-digest",
        "provenance": "sealed-ledger",
    }


def _source_rows() -> list[dict[str, object]]:
    return [
        {
            "source_wall_edge": "source",
            "source_face": 0,
            "side": "source",
            "layer": 0,
            "patch": "wall",
            "feature": "smooth",
            "physical_group": "fluid_wall",
            "component": "main",
            "provenance": "source-ledger",
        }
    ]


def _fixture():
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [-0.5, 0.0, -0.8660254038],
            [0.5, 0.0, -0.8660254038],
        ],
        dtype=float,
    )
    source = np.array([[0, 2, 1]], dtype=np.int64)
    normals = np.array([[0.0, 0.0, -1.0]], dtype=float)
    return points, source, normals


def test_bl0_is_exact_identity_transaction():
    points, source, normals = _fixture()
    result = seal_authoritative_surface_bl_transaction(
        points,
        source,
        source,
        normals,
        _authority(),
        {"accepted": True, "status": "disabled_identity"},
        [],
        0,
    )
    assert result["accepted"] is True
    assert result["status"] == "surface_bl_actual_transaction_bl0_identity"
    assert result["artifact_digest"] == result["source_geometry_digest"]
    assert result["publication_eligible"] is False


def test_bl1_binds_writer_direct_ids_and_independent_quality():
    points, source, normals = _fixture()
    writer = write_authoritative_surface_wall_edge_strip(
        points,
        source,
        np.array([[11, 0, 1, 0]], dtype=np.int64),
        np.array([[[3, 4]]], dtype=np.int64),
        normals,
        _authority(),
        [
            {
                "source_wall_edge": 11,
                "source_face": 0,
                "side": "wall",
                "patch": "wall",
                "feature": "smooth",
                "physical_group": "fluid_wall",
                "component": "main",
                "provenance": "writer-ledger",
            }
        ],
        1,
    )
    assert writer["accepted"] is True
    generated = []
    for row in writer["generated_faces"]:
        generated.append(row)
    generated_prov = []
    for row in writer["provenance"]:
        generated_prov.append({**dict(row), "side": "wall"})
    candidate = np.asarray(writer["generated_faces"], dtype=np.int64)
    result = seal_authoritative_surface_bl_transaction(
        points,
        source,
        candidate,
        normals,
        _authority(),
        writer,
        generated_prov,
        1,
        source_provenance=_source_rows(),
    )
    assert result["accepted"] is True, result
    assert result["status"] == "surface_bl_actual_artifact_sealed"
    assert result["source_immutable"] is True
    assert result["independent"]["verdict"] == "PASS_FOR_REVIEW"
    assert result["quality"]["accepted"] is True
    assert result["topology_invalid"] == 0
    assert result["topology_duplicate"] == 0
    assert len(result["provenance"]) == 1
    assert result["publication_eligible"] is False


def test_source_mutation_and_missing_lineage_refuse_atomically():
    points, source, normals = _fixture()
    mutated = np.array([[0, 1, 2]], dtype=np.int64)
    refused = seal_authoritative_surface_bl_transaction(
        points,
        source,
        mutated,
        normals,
        _authority(),
        {"accepted": True},
        [],
        1,
        source_provenance=_source_rows(),
    )
    assert refused["accepted"] is False
    assert refused["reason"] in {"source_faces_not_preserved", "source_face_prefix_changed"}
    assert refused["candidate_discarded"] is True

    refused = seal_authoritative_surface_bl_transaction(
        points,
        source,
        np.vstack([source, [[0, 1, 4], [0, 4, 3]]]),
        normals,
        _authority(),
        {"accepted": True},
        [
            {
                "source_wall_edge": 11,
                "source_face": 0,
                "patch": "wall",
                "feature": "smooth",
                "physical_group": "fluid_wall",
                "component": "main",
                "provenance": "missing-side",
                "final_face_ids": (1, 2),
            }
        ],
        1,
        source_provenance=_source_rows(),
    )
    assert refused["accepted"] is False
    assert refused["reason"] in {"independent_lineage_side_missing", "direct_id_or_provenance_missing"}
    assert refused["candidate_discarded"] is True
