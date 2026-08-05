from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.evaluator.native_poly_fresh_stage_profile import profile_poly_bl_stage
from core.evaluator.native_poly_bl_producer_certificate import (
    build_producer_certificate,
    write_producer_certificate,
)


def _valid_kwargs() -> dict[str, object]:
    return {
        "source_faces": [
            {
                "source_face_id": 0,
                "ordered_vertex_ids": [0, 1, 2],
                "canonical_vertex_ids": [0, 1, 2],
                "patch_id": "wall",
                "feature_id": "f0",
                "physical_group": "fluid-wall",
                "component_id": "component-0",
            }
        ],
        "wall_edges": [
            {"edge_id": 0, "vertex_ids": [0, 1], "incident_source_face_ids": [0]},
            {"edge_id": 1, "vertex_ids": [1, 2], "incident_source_face_ids": [0]},
            {"edge_id": 2, "vertex_ids": [2, 0], "incident_source_face_ids": [0]},
        ],
        "layer_entities": [
            {
                "layer": 1,
                "source_face_id": 0,
                "generated_vertex_ids": [3, 4, 5],
                "generated_face_ids": [10, 11],
                "generated_cell_ids": [1],
            }
        ],
        "outer_front": [{"final_face_id": 20, "source_face_id": 0, "layer": 1, "cell_id": 1}],
        "cell_partitions": {"core": [0], "boundary_layer": [1], "transition": []},
        "final_cell_ids": [0, 1],
        "requested_layers": 1,
        "actual_layers": 1,
        "total_thickness": 0.1,
        "source_sha256": "a" * 64,
        "candidate_file_sha256": {"points": "b" * 64, "faces": "c" * 64},
        "transition_not_applicable": True,
    }


def test_producer_certificate_has_real_lineage_and_exact_partition(tmp_path: Path) -> None:
    provenance, partition = build_producer_certificate(**_valid_kwargs())
    assert provenance["schema"].endswith("/v2")
    assert provenance["lineage_complete"] is True
    assert len(provenance["candidate_source_sha256"]) == 64
    assert partition["cell_ids"] == {"core": [0], "boundary_layer": [1], "transition": []}
    paths = write_producer_certificate(tmp_path, provenance, partition)
    assert all(path.is_file() for path in paths)
    assert json.loads(paths[0].read_text(encoding="utf-8"))["producer_mapping_sha256"] == provenance["producer_mapping_sha256"]


@pytest.mark.parametrize(
    ("field", "replacement", "reason"),
    [
        ("source_faces", [], "source_faces_missing"),
        ("wall_edges", [], "wall_edges_missing"),
        ("outer_front", [], "outer_front_missing"),
        ("cell_partitions", {"core": [0], "boundary_layer": [1], "transition": [1]}, "cell_partition_overlap_or_duplicate"),
        ("candidate_file_sha256", {}, "candidate_file_digests_missing"),
    ],
)
def test_certificate_refuses_missing_or_forged_authority(field, replacement, reason) -> None:
    kwargs = _valid_kwargs()
    kwargs[field] = replacement
    with pytest.raises(ValueError, match=reason):
        build_producer_certificate(**kwargs)


def test_certificate_refuses_transition_without_explicit_proof() -> None:
    kwargs = _valid_kwargs()
    kwargs["transition_not_applicable"] = False
    with pytest.raises(ValueError, match="transition_not_applicable_certificate_missing"):
        build_producer_certificate(**kwargs)


def test_profile_reads_v2_sidecars_and_checks_explicit_coverage(tmp_path: Path) -> None:
    provenance, partition = build_producer_certificate(**_valid_kwargs())
    write_producer_certificate(tmp_path, provenance, partition)
    report = profile_poly_bl_stage(
        tmp_path,
        requested_layers=1,
        input_sha256="d" * 64,
        build_sha256="e" * 64,
        fingerprint_fn=lambda _path: {"tree_sha256": "f" * 64, "entry_count": 4},
    )
    assert report["status"] == "PASS"
    assert report["partitions"]["counts"] == {"core": 1, "boundary_layer": 1, "transition": 0}
