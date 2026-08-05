from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np
import pytest

from core.preprocessor.native_tri.authority_bound_diagonal_front_cdt import (
    make_authority_bound_diagonal_front_cdt_template_anchor,
    write_native_tri_authority_bound_diagonal_front_cdt_bl,
)
from core.preprocessor.native_tri.wall_edge_bl_preflight import (
    make_external_edge_trust_anchor,
    validate_native_tri_wall_edge_bl_preflight,
)

sys.path.insert(0, str(Path(__file__).parent))

from test_native_tri_planar_face_pair_bl_template import _fixture


def _registered(certificate, rows, pair_faces, active, *, layers, height, growth):
    edge_anchor = make_external_edge_trust_anchor(
        certificate,
        rows,
        loop_policy="closed_nonbranching",
        issuer="tri-c124-edge",
        key_id="tri-c124-v1",
    )
    preflight = validate_native_tri_wall_edge_bl_preflight(
        certificate,
        rows,
        edge_anchor,
        requested_layers=layers,
        first_height=height,
        growth_ratio=growth,
    )
    assert preflight["accepted"] is True, preflight
    template = make_authority_bound_diagonal_front_cdt_template_anchor(
        certificate,
        edge_anchor,
        preflight,
        source_face_ids=pair_faces,
        wall_edge_ids=[row["edge_id"] for row in rows],
        active_sector_face_ids=active,
        feature="cube-wall",
        patch="cube-pair-wall",
        physical_group="cube-physical-wall",
        component="cube",
        provenance="registered-face-pair",
    )
    return edge_anchor, template


def _result(layers, height):
    points, faces, certificate, rows, pair_faces, active = _fixture(
        Path("tests/benchmarks/trimesh_box.stl")
    )
    edge_anchor, template = _registered(
        certificate,
        rows,
        pair_faces,
        active,
        layers=layers,
        height=height,
        growth=1.0,
    )
    result = write_native_tri_authority_bound_diagonal_front_cdt_bl(
        certificate,
        rows,
        edge_anchor,
        template,
        requested_layers=layers,
        first_height=height,
        growth_ratio=1.0,
    )
    return points, faces, certificate, rows, pair_faces, active, edge_anchor, template, result


def test_bl0_is_exact_identity():
    points, faces, *_rest = _result(0, 0.0)
    result = _rest[-1]
    assert result["accepted"] is True, result
    assert result["status"] == "native_tri_authority_bound_diagonal_front_cdt_identity"
    assert result["bl0_identity"] is True
    assert result["writer_invoked"] is False
    assert np.array_equal(np.asarray(result["output_vertices"]), points)
    assert np.array_equal(np.asarray(result["output_faces"]), faces)
    assert result["generated_faces"] == []


@pytest.mark.parametrize(("layers", "height"), ((1, 0.20), (2, 0.20), (3, 0.10)))
def test_positive_layers_pass_topology_authority_and_quality(layers, height):
    *_, result = _result(layers, height)
    assert result["accepted"] is True, result
    assert result["actual_layers"] == layers
    assert result["artifact_emitted"] is True
    assert result["atomic_rollback"] is False
    quality = result["quality"]
    assert quality["raw_physical_aspect_max"] <= 5.5
    assert quality["raw_mean_ratio_min"] >= 0.30
    assert quality["raw_angle_nonorthogonality_max_degrees"] <= 55.0
    assert quality["metric_skewness_max"] <= 0.35
    assert quality["metric_aspect_ratio_max"] <= 1.60
    assert quality["wall_front_non_orthogonality_max_degrees"] <= 1.0
    topology = result["topology"]
    assert all(topology[key] == 0 for key in (
        "invalid", "degenerate", "inverted", "duplicate",
        "open_edges", "non_manifold", "self_intersection",
    ))
    assert result["collision"]["rejected_contacts"] == 0
    assert result["source_face_coverage_complete"] is True
    assert len(result["output_faces"]) == result["actual_face_count"]
    assert result["actual_face_count"] == 1200
    assert sum(result["pair_ring_face_counts"]) + result["pair_core_face_count"] == 200
    assert result["support_refined_face_count"] == 1000


def test_shared_source_diagonal_uses_one_canonical_chain_and_provenance():
    _points, _faces, _certificate, _rows, _pair, _active, _edge, _template, result = _result(1, 0.20)
    assert result["accepted"] is True, result
    diagonal_vertices = [
        row for row in result["generated_vertices"]
        if set(row["source_face_ids"]) == {0, 2}
    ]
    assert len(diagonal_vertices) == 9
    assert [row["source_face_ids"] for row in diagonal_vertices] == [[0, 2]] * 9
    assert all(row["provenance"] == "registered-face-pair" for row in result["provenance"])
    assert {row["source_face_id"] for row in result["provenance"]} == set(range(12))


def test_positive_route_is_deterministic():
    *_, first = _result(2, 0.20)
    *_, second = _result(2, 0.20)
    assert first["accepted"] is True and second["accepted"] is True
    assert first["deterministic_digest"] == second["deterministic_digest"]
    assert first["output_vertices"] == second["output_vertices"]
    assert first["output_faces"] == second["output_faces"]


@pytest.mark.parametrize("tamper", ("face", "edge", "digest", "label"))
def test_authority_tamper_is_atomic(tamper):
    _points, _faces, certificate, rows, pair, active, edge_anchor, template, _ = _result(1, 0.20)
    forged_rows = copy.deepcopy(rows)
    forged_template = copy.deepcopy(template)
    if tamper == "face":
        forged_template["source_face_ids"] = [0, 1]
    elif tamper == "edge":
        forged_template["wall_edge_ids"][0] = "forged-edge"
    elif tamper == "digest":
        forged_template["preflight_digest"] = "0" * 64
    else:
        forged_rows[0]["feature"] = "forged"
    result = write_native_tri_authority_bound_diagonal_front_cdt_bl(
        certificate,
        forged_rows,
        edge_anchor,
        forged_template,
        requested_layers=1,
        first_height=0.20,
        growth_ratio=1.0,
    )
    assert result["accepted"] is False, result
    assert result["actual_layers"] == 0
    assert result["output_faces"] == []
    assert result["atomic_rollback"] is True


def test_unsupported_schedule_refuses_without_artifact():
    _points, _faces, certificate, rows, pair, active = _fixture(
        Path("tests/benchmarks/trimesh_box.stl")
    )
    edge_anchor, template = _registered(
        certificate, rows, pair, active, layers=2, height=0.02, growth=1.05
    )
    result = write_native_tri_authority_bound_diagonal_front_cdt_bl(
        certificate,
        rows,
        edge_anchor,
        template,
        requested_layers=2,
        first_height=0.02,
        growth_ratio=1.05,
    )
    assert result["accepted"] is False, result
    assert result["output_faces"] == []
    assert result["atomic_rollback"] is True
