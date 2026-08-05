from __future__ import annotations

import hashlib
import math

import numpy as np

from core.evaluator.native_surface_bl_heterogeneous_zipper_certificate import (
    validate_bl0_identity,
    validate_regular_hex_certificate,
)


TEMPLATE = "regular_hex_outer2_inner1_zipper_v1"
CHAIN = "regular_hex_zipper_chain_v1"
RECEIPT = "f" * 64


def _fixture():
    n = 6
    points = np.asarray(
        [[0.0, 0.0, 0.0]]
        + [
            [2.0 * math.cos(2.0 * math.pi * i / n),
             2.0 * math.sin(2.0 * math.pi * i / n), 0.0]
            for i in range(n)
        ],
        dtype=np.float64,
    )
    triangles = np.asarray(
        [[0, i + 1, ((i + 1) % n) + 1] for i in range(n)],
        dtype=np.int64,
    )
    edges = np.asarray(
        [[100 + i, i + 1, ((i + 1) % n) + 1, i] for i in range(n)],
        dtype=np.int64,
    )
    front_points = np.asarray(points[1:] * 0.5, dtype=np.float64)
    authority = {
        "source_kind": "authoritative-stl-ledger",
        "source_sha256": "a" * 64,
        "boundary_mapping_sha256": "b" * 64,
        "feature_sha256": "c" * 64,
        "physical_group_sha256": "d" * 64,
        "component_sha256": "e" * 64,
        "provenance": "direct-source-ledger",
        "receipt_digest": RECEIPT,
        "canonical_topology_hash": "0" * 64,
    }
    count_ledger = []
    interval_ledger = []
    midpoint_lineage = []
    provenance = []
    for edge_id, a, b, face_id in edges.tolist():
        for layer, count, lower, upper, transition in (
            (0, 2, 2, 1, "two_to_one"),
            (1, 1, 1, 1, "one_to_one"),
        ):
            count_ledger.append(
                {
                    "source_edge_id": edge_id,
                    "layer": layer,
                    "count": count,
                    "lower_count": lower,
                    "upper_count": upper,
                    "transition_kind": transition,
                    "template_id": TEMPLATE,
                    "chain_id": CHAIN,
                    "receipt_digest": RECEIPT,
                }
            )
        for index in range(2):
            interval_ledger.append(
                {
                    "source_edge_id": edge_id,
                    "layer": 0,
                    "interval_index": index,
                    "subdivision_factor": 2,
                    "denominator": 2,
                    "t0_numerator": index,
                    "t1_numerator": index + 1,
                    "chain_id": CHAIN,
                    "receipt_digest": RECEIPT,
                }
            )
        midpoint_lineage.append(
            {
                "source_edge_id": edge_id,
                "source_face_id": face_id,
                "parent_vertex_ids": [a, b],
                "parameter_numerator": 1,
                "parameter_denominator": 2,
                "lineage_role": "midpoint_front_parent",
                "feature": "outer-wall",
                "patch": "wall",
                "physical_group": "fluid-wall",
                "component": "regular-hex",
                "provenance": "direct-source-ledger",
                "receipt_digest": RECEIPT,
            }
        )
        provenance.append(
            {
                "source_edge_id": edge_id,
                "source_face_id": face_id,
                "feature": "outer-wall",
                "patch": "wall",
                "physical_group": "fluid-wall",
                "component": "regular-hex",
                "provenance": "direct-source-ledger",
                "receipt_digest": RECEIPT,
            }
        )
    canonical_key = (
        f"{TEMPLATE}|{CHAIN}|center=0|front=1,2,3,4,5,6,|counts="
        + "".join(
            f"{row['source_edge_id']}:{row['layer']}:{row['count']}:{row['lower_count']}:{row['upper_count']};"
            for row in sorted(
                count_ledger,
                key=lambda item: (item["source_edge_id"], item["layer"]),
            )
        )
        + "|intervals="
        + "".join(
            f"{row['source_edge_id']}:{row['layer']}:{row['interval_index']};"
            for row in sorted(
                interval_ledger,
                key=lambda item: (
                    item["source_edge_id"],
                    item["layer"],
                    item["interval_index"],
                ),
            )
        )
    )
    authority["canonical_topology_hash"] = hashlib.sha256(
        canonical_key.encode("utf-8")
    ).hexdigest()
    return (
        points,
        triangles,
        edges,
        front_points,
        authority,
        count_ledger,
        interval_ledger,
        midpoint_lineage,
        provenance,
    )


def _validate(fixture):
    return validate_regular_hex_certificate(
        *fixture[:4],
        list(range(1, 7)),
        fixture[5],
        fixture[6],
        fixture[7],
        fixture[4],
        fixture[8],
        TEMPLATE,
        CHAIN,
        1,
    )


def test_regular_hex_certificate_is_cpp_admitted_without_mesh_emission():
    result = _validate(_fixture())
    assert result["accepted"] is True, result
    assert result["status"] == "heterogeneous_zipper_certificate_accepted"
    assert result["reason"] == "regular_hex_template_recognized_without_mesh_emission"
    assert result["artifact_emitted"] is False
    assert result["publication_eligible"] is False
    assert result["generated_faces"] == []
    assert result["generated_vertices"] == []
    assert result["certificate_layers"] == 1
    assert result["actual_layers"] == 0
    assert result["max_skewness"] == 0.0
    assert result["max_aspect_ratio"] == 1.0
    assert result["max_non_orthogonality_degrees"] == 0.0


def test_certificate_is_deterministic_and_edge_row_order_independent():
    fixture = _fixture()
    first = _validate(fixture)
    second = _validate(fixture)
    assert first["canonical_contract_key"] == second["canonical_contract_key"]

    reordered = list(fixture)
    permutation = [2, 5, 0, 4, 1, 3]
    reordered[2] = fixture[2][permutation]
    reordered[5] = [fixture[5][2 * i + layer] for i in permutation for layer in (0, 1)]
    reordered[6] = [fixture[6][2 * i + interval] for i in permutation for interval in (0, 1)]
    reordered[7] = [fixture[7][i] for i in permutation]
    reordered[8] = [fixture[8][i] for i in permutation]
    third = _validate(tuple(reordered))
    assert third["accepted"] is True, third
    assert third["canonical_contract_key"] == first["canonical_contract_key"]


def test_unsupported_count_or_interval_tamper_refuses_atomically():
    fixture = list(_fixture())
    fixture[5] = [dict(row) for row in fixture[5]]
    fixture[5][0]["count"] = 3
    result = _validate(tuple(fixture))
    assert result["accepted"] is False, result
    assert result["reason"] == "heterogeneous_zipper_template_unsupported"
    assert result["generated_faces"] == []
    assert result["generated_vertices"] == []
    assert result["candidate_discarded"] is True

    fixture = list(_fixture())
    fixture[6] = [dict(row) for row in fixture[6]]
    fixture[6][0]["t0_numerator"] = 1
    result = _validate(tuple(fixture))
    assert result["accepted"] is False, result
    assert result["reason"] == "heterogeneous_zipper_interval_record_invalid"
    assert result["generated_faces"] == []

    fixture = list(_fixture())
    fixture[4] = dict(fixture[4])
    fixture[4]["canonical_topology_hash"] = "1" * 64
    result = _validate(tuple(fixture))
    assert result["accepted"] is False, result
    assert result["reason"] == "heterogeneous_zipper_canonical_hash_mismatch"
    assert result["generated_faces"] == []


def test_square_and_missing_authority_are_not_heterogeneous_release_evidence():
    fixture = list(_fixture())
    fixture[0] = fixture[0][:5]
    result = _validate(tuple(fixture))
    assert result["accepted"] is False, result
    assert result["reason"] == "heterogeneous_zipper_template_unsupported"
    assert result["generated_faces"] == []

    fixture = list(_fixture())
    fixture[4] = dict(fixture[4])
    fixture[4].pop("feature_sha256")
    result = _validate(tuple(fixture))
    assert result["accepted"] is False, result
    assert result["reason"] == "heterogeneous_zipper_authority_incomplete"


def test_bl0_identity_requires_exact_source_output_digest_equality():
    fixture = _fixture()
    accepted = validate_bl0_identity("a" * 64, "a" * 64, fixture[4], 0)
    assert accepted["accepted"] is True, accepted
    assert accepted["generated_faces"] == []
    refused = validate_bl0_identity("a" * 64, "b" * 64, fixture[4], 0)
    assert refused["accepted"] is False, refused
    assert refused["reason"] == "heterogeneous_zipper_bl0_identity_invalid"
