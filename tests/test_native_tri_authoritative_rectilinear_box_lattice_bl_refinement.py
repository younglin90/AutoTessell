from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np
import pytest

from core.preprocessor.native_tri.authoritative_rectilinear_box_lattice_bl_refinement import (
    admit_native_tri_curved_naca_bl,
    make_authoritative_rectilinear_box_lattice_template_anchor,
    write_native_tri_authoritative_rectilinear_box_lattice_bl,
)
from core.preprocessor.native_tri.cad_stl_authority_ingress import (
    make_external_trust_anchor,
    semantic_ledger_from_faces,
    validate_native_tri_authority_source,
)
from core.preprocessor.native_tri.wall_edge_bl_preflight import (
    make_external_edge_trust_anchor,
    validate_native_tri_wall_edge_bl_preflight,
)

sys.path.insert(0, str(Path(__file__).parent))
from test_native_tri_planar_face_pair_bl_template import _canonical_stl, _fixture


def _registered(certificate, rows, pair_faces, active, *, layers, height, growth):
    edge_anchor = make_external_edge_trust_anchor(
        certificate,
        rows,
        loop_policy="closed_nonbranching",
        issuer="tri-box-lattice-edge-registry",
        key_id="tri-box-lattice-edge-v1",
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
    template = make_authoritative_rectilinear_box_lattice_template_anchor(
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


def test_bl0_is_exact_identity_for_rectilinear_box():
    points, faces, certificate, rows, pair_faces, active = _fixture(
        Path("tests/benchmarks/trimesh_box.stl")
    )
    edge_anchor, template = _registered(
        certificate, rows, pair_faces, active, layers=0, height=0.0, growth=1.0
    )
    result = write_native_tri_authoritative_rectilinear_box_lattice_bl(
        certificate, rows, edge_anchor, template,
        requested_layers=0, first_height=0.0, growth_ratio=1.0,
    )
    assert result["accepted"] is True, result
    assert result["status"] == (
        "native_tri_authoritative_rectilinear_box_lattice_bl_identity"
    )
    assert result["bl0_identity"] is True
    assert result["writer_invoked"] is False
    assert np.array_equal(np.asarray(result["output_vertices"]), points)
    assert np.array_equal(np.asarray(result["output_faces"]), faces)
    assert result["generated_faces"] == []


@pytest.mark.parametrize(
    ("layers", "height"),
    ((1, 0.20), (2, 0.20), (3, 0.10)),
)
def test_rectilinear_box_positive_schedule_refuses_when_quality_is_not_admissible(
    layers, height
):
    _points, _faces, certificate, rows, pair_faces, active = _fixture(
        Path("tests/benchmarks/trimesh_box.stl")
    )
    edge_anchor, template = _registered(
        certificate, rows, pair_faces, active,
        layers=layers, height=height, growth=1.0,
    )
    result = write_native_tri_authoritative_rectilinear_box_lattice_bl(
        certificate, rows, edge_anchor, template,
        requested_layers=layers, first_height=height, growth_ratio=1.0,
    )
    assert result["accepted"] is False, result
    assert result["reason"] == "box_quality_gate_failed"
    assert result["actual_layers"] == 0
    assert result["output_faces"] == []
    assert result["atomic_rollback"] is True
    assert result["actual_face_count"] > 0
    assert result["quality"]["metric_aspect_ratio_max"] > 1.60
    assert result["quality"]["metric_skewness_max"] > 0.35
    assert result["quality"]["raw_angle_nonorthogonality_max_degrees"] <= 55.0
    assert len(result["worst_face_vertices"]) == 3


def test_box_unsupported_resolution_refuses_without_artifact():
    _points, _faces, certificate, rows, pair_faces, active = _fixture(
        Path("tests/benchmarks/trimesh_box.stl")
    )
    edge_anchor, template = _registered(
        certificate, rows, pair_faces, active,
        layers=2, height=0.02, growth=1.05,
    )
    result = write_native_tri_authoritative_rectilinear_box_lattice_bl(
        certificate, rows, edge_anchor, template,
        requested_layers=2, first_height=0.02, growth_ratio=1.05,
    )
    assert result["accepted"] is False, result
    assert result["reason"] == "lattice_resolution_out_of_bounds"
    assert result["output_faces"] == []
    assert result["atomic_rollback"] is True


@pytest.mark.parametrize("tamper", ("face", "edge", "digest", "label"))
def test_box_authority_tamper_is_atomic(tamper):
    _points, _faces, certificate, rows, pair_faces, active = _fixture(
        Path("tests/benchmarks/trimesh_box.stl")
    )
    edge_anchor, template = _registered(
        certificate, rows, pair_faces, active,
        layers=1, height=0.20, growth=1.0,
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
    result = write_native_tri_authoritative_rectilinear_box_lattice_bl(
        certificate, forged_rows, edge_anchor, forged_template,
        requested_layers=1, first_height=0.20, growth_ratio=1.0,
    )
    assert result["accepted"] is False, result
    assert result["actual_layers"] == 0
    assert result["output_faces"] == []
    assert result["atomic_rollback"] is True


def test_naca_bl0_identity_and_positive_layer_admission_refusal():
    path = Path("tests/benchmarks/naca0012.stl")
    points, faces = _canonical_stl(path)
    labels = semantic_ledger_from_faces(
        faces,
        feature="naca-wall",
        patch="naca-surface",
        physical_group="naca-physical-wall",
        component="naca0012",
        provenance="registered-naca-source",
    )
    anchor = make_external_trust_anchor(path, labels, issuer="tri-naca-test", key_id="tri-naca-v1")
    certificate = validate_native_tri_authority_source(path, labels, anchor, requested_layers=0)
    assert certificate["accepted"] is True, certificate
    identity = admit_native_tri_curved_naca_bl(
        certificate, requested_layers=0, first_height=0.0, growth_ratio=1.0
    )
    assert identity["accepted"] is True, identity
    assert identity["bl0_identity"] is True
    assert identity["artifact_emitted"] is False
    assert np.array_equal(np.asarray(identity["output_vertices"]), points)
    assert np.array_equal(np.asarray(identity["output_faces"]), faces)
    positive = admit_native_tri_curved_naca_bl(
        certificate, requested_layers=1, first_height=0.02, growth_ratio=1.0
    )
    assert positive["accepted"] is False, positive
    assert positive["reason"] == "curved_front_source_quality_unadmissible"
    assert positive["output_faces"] == []
    assert positive["atomic_rollback"] is True
    assert positive["source_raw_aspect_max"] > 5.5
