from __future__ import annotations

import numpy as np


def _module():
    import native_tet_bl_admission

    return native_tet_bl_admission


def _policy(**overrides):
    values = {
        "min_signed_volume": 0.1,
        "min_scaled_jacobian": 0.3,
        "max_skewness": 0.4,
        "max_non_orthogonality": 40.0,
        "max_aspect_ratio": 1.5,
        "policy_sha256": "0" * 64,
    }
    values.update(overrides)
    return values


def _authority():
    return {
        "source_sha256": "1" * 64,
        "semantic_ledger_sha256": "2" * 64,
    }


def _ledger():
    return {
        "schema": "native-tet-bl-writer-ledger/v2",
        "writer_owned": True,
        "actual_layers": 1,
        "source_sha256": "1" * 64,
        "semantic_ledger_sha256": "2" * 64,
        "bl_config_sha256": "3" * 64,
        "quality_policy_sha256": "0" * 64,
        "graph_sha256": "4" * 64,
        "artifact_tree_sha256": "5" * 64,
        "source_faces": [],
        "boundary_children": [],
        "interface_children": [],
        "edge_children": [],
        "prisms": [],
        "cells": [],
        "inverse": {
            "boundary_face_to_source": {},
            "tet_to_prism": {},
        },
    }


def _tetra():
    return np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    ), np.asarray([[0, 1, 2, 3]], dtype=np.int64)


def test_admission_bl0_is_bitwise_identity_and_sidecar_free() -> None:
    points, tets = _tetra()
    empty_triangles = np.empty((0, 3), dtype=np.int64)
    result = _module().admit(
        points,
        np.empty((0, 4), dtype=np.int64),
        empty_triangles,
        {},
        0,
        base_points=points.copy(),
    )

    assert result["accepted"] is True
    assert result["status"] == "bl0_identity_admitted"
    assert result["writer_sidecar_emitted"] is False
    assert result["collision_checked"] is False
    assert result["publication_eligible"] is False


def test_admission_accepts_a_valid_positive_candidate_with_v2_authority() -> None:
    points, tets = _tetra()
    result = _module().admit(
        points,
        tets,
        np.empty((0, 3), dtype=np.int64),
        _policy(),
        1,
        ledger=_ledger(),
        authority=_authority(),
    )

    assert result["accepted"] is True
    assert result["status"] == "candidate_admitted"
    assert result["candidate_discarded"] is False
    assert result["publication_eligible"] is False
    assert result["full_ledger_admitted"] is True
    assert result["quality"]["max_aspect_ratio"] <= 1.5


def test_admission_refuses_a_v1_or_missing_full_ledger_before_geometry() -> None:
    points, tets = _tetra()
    result = _module().admit(
        points,
        tets,
        np.empty((0, 3), dtype=np.int64),
        _policy(),
        1,
        authority=_authority(),
    )

    assert result["accepted"] is False
    assert result["candidate_discarded"] is True
    assert result["refusal_stage"] == "ledger"
    assert result["refusal_reason"] == "full_ledger_v2_required"


def test_admission_refuses_self_intersecting_candidate_surface_deterministically() -> None:
    points, tets = _tetra()
    points = np.vstack(
        [points, [[0.5, 0.5, 0.0], [1.5, 0.5, 0.0], [0.5, 1.5, 0.0]]]
    )
    collision_triangles = np.asarray([[0, 1, 2], [4, 5, 6]], dtype=np.int64)
    result = _module().admit(
        points,
        tets,
        collision_triangles,
        _policy(),
        1,
        ledger=_ledger(),
        authority=_authority(),
    )

    assert result["accepted"] is False
    assert result["candidate_discarded"] is True
    assert result["refusal_stage"] == "collision"
    assert result["refusal_reason"] == "candidate_surface_self_intersection"


def test_admission_refuses_quality_before_any_publication() -> None:
    points, tets = _tetra()
    result = _module().admit(
        points,
        tets,
        np.empty((0, 3), dtype=np.int64),
        _policy(max_skewness=0.1),
        1,
        ledger=_ledger(),
        authority=_authority(),
    )

    assert result["accepted"] is False
    assert result["candidate_discarded"] is True
    assert result["refusal_stage"] == "quality"
    assert result["refusal_reason"] == "quality_policy_failed"
    assert result["publication_eligible"] is False

def test_admission_refuses_inverted_tet_by_signed_orientation() -> None:
    points, _ = _tetra()
    inverted = np.asarray([[0, 2, 1, 3]], dtype=np.int64)
    result = _module().admit(
        points,
        inverted,
        np.empty((0, 3), dtype=np.int64),
        _policy(),
        1,
        ledger=_ledger(),
        authority=_authority(),
    )

    assert result["accepted"] is False
    assert result["candidate_discarded"] is True
    assert result["refusal_stage"] == "volume"
    assert result["refusal_reason"] == "tet_signed_volume_nonpositive"

