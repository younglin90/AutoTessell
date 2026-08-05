from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np
import pytest

from core.preprocessor.native_tri.authoritative_cube_lattice_bl_refinement import (
    make_authoritative_cube_lattice_template_anchor,
    write_native_tri_authoritative_cube_lattice_bl,
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
        issuer="tri-cube-lattice-edge-registry",
        key_id="tri-cube-lattice-edge-v1",
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
    template = make_authoritative_cube_lattice_template_anchor(
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


def test_bl0_is_exact_identity():
    points, faces, certificate, rows, pair_faces, active = _fixture(
        Path("tests/benchmarks/cube.stl")
    )
    edge_anchor, template = _registered(
        certificate, rows, pair_faces, active, layers=0, height=0.0, growth=1.0
    )
    result = write_native_tri_authoritative_cube_lattice_bl(
        certificate, rows, edge_anchor, template,
        requested_layers=0, first_height=0.0, growth_ratio=1.0,
    )
    assert result["accepted"] is True, result
    assert result["status"] == "native_tri_authoritative_cube_lattice_bl_identity"
    assert result["bl0_identity"] is True
    assert np.array_equal(np.asarray(result["output_vertices"]), points)
    assert np.array_equal(np.asarray(result["output_faces"]), faces)
    assert result["generated_faces"] == []


@pytest.mark.parametrize(
    ("layers", "height", "expected_n", "expected_ring", "expected_core"),
    ((1, 0.20, 5, [32], 18), (2, 0.20, 5, [32, 16], 2), (3, 0.15, 20, [408, 264, 120], 8)),
)
def test_cube_positive_quality_schedule_and_conforming_counts(
    layers, height, expected_n, expected_ring, expected_core
):
    _points, faces, certificate, rows, pair_faces, active = _fixture(
        Path("tests/benchmarks/cube.stl")
    )
    edge_anchor, template = _registered(
        certificate, rows, pair_faces, active,
        layers=layers, height=height, growth=1.0,
    )
    results = [
        write_native_tri_authoritative_cube_lattice_bl(
            certificate, rows, edge_anchor, template,
            requested_layers=layers, first_height=height, growth_ratio=1.0,
        )
        for _ in range(3 if layers == 1 else 1)
    ]
    assert all(result["accepted"] for result in results), results
    result = results[0]
    assert result["actual_layers"] == layers
    assert result["lattice_N"] == expected_n
    assert len(result["output_faces"]) == 12 * expected_n * expected_n
    assert len(result["generated_faces"]) == len(result["output_faces"])
    assert result["pair_ring_face_counts"] == expected_ring
    assert result["pair_core_face_count"] == expected_core
    assert result["quality"]["raw_quality_gate_pass"] is True
    assert result["quality"]["metric_quality_gate_pass"] is True
    assert result["quality"]["raw_physical_aspect_max"] == pytest.approx(2**0.5)
    assert result["quality"]["raw_angle_nonorthogonality_max_degrees"] <= 30.0 + 1e-12
    assert result["quality"]["raw_mean_ratio_min"] == pytest.approx(3**0.5 / 2.0)
    assert result["quality"]["metric_aspect_ratio_max"] == pytest.approx(2**0.5)
    assert result["quality"]["wall_front_non_orthogonality_max_degrees"] == 0.0
    for key in ("invalid", "degenerate", "inverted", "duplicate", "open_edges", "non_manifold", "self_intersection"):
        assert result["topology"][key] == 0, result
    assert result["collision"]["rejected_contacts"] == 0
    assert len(result["provenance"]) == len(result["output_faces"])
    assert all(
        "source_face_id" in row
        and "feature" in row
        and "patch" in row
        and "physical_group" in row
        and "component" in row
        and "provenance" in row
        for row in result["provenance"]
    )
    if layers == 1:
        assert len({r["deterministic_digest"] for r in results}) == 1
        assert len(result["output_vertices"]) == 152


def test_non_integral_large_lattice_refuses_without_artifact():
    _points, _faces, certificate, rows, pair_faces, active = _fixture(
        Path("tests/benchmarks/cube.stl")
    )
    edge_anchor, template = _registered(
        certificate, rows, pair_faces, active, layers=2, height=0.02, growth=1.05
    )
    result = write_native_tri_authoritative_cube_lattice_bl(
        certificate, rows, edge_anchor, template,
        requested_layers=2, first_height=0.02, growth_ratio=1.05,
    )
    assert result["accepted"] is False, result
    assert result["reason"] == "lattice_resolution_out_of_bounds"
    assert result["output_faces"] == []
    assert result["atomic_rollback"] is True


@pytest.mark.parametrize("tamper", ("face", "edge", "digest", "label"))
def test_authority_tamper_is_atomic(tamper):
    _points, _faces, certificate, rows, pair_faces, active = _fixture(
        Path("tests/benchmarks/cube.stl")
    )
    edge_anchor, template = _registered(
        certificate, rows, pair_faces, active, layers=1, height=0.20, growth=1.0
    )
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
    result = write_native_tri_authoritative_cube_lattice_bl(
        certificate, forged_rows, edge_anchor, forged_template,
        requested_layers=1, first_height=0.20, growth_ratio=1.0,
    )
    assert result["accepted"] is False, result
    assert result["actual_layers"] == 0
    assert result["output_faces"] == []
    assert result["atomic_rollback"] is True
