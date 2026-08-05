from __future__ import annotations

from pathlib import Path

import numpy as np

from core.evaluator.native_surface_bl_front_actual_v2_folded_plate import produce_folded_plate_evidence


def _case():
    positions = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    triangles = np.asarray([[0, 1, 2], [0, 1, 3]], dtype=np.int64)
    ridge = np.asarray([0, 1], dtype=np.int64)
    normals = np.asarray([[0, 0, 1], [0, -1, 0]], dtype=np.float64)
    semantics = [
        {"source_edge": "101", "source_face": "0", "feature": "plate-0", "patch": "wall-0", "physical_group": "fluid-0", "component": "folded", "provenance": "explicit-step-map"},
        {"source_edge": "101", "source_face": "1", "feature": "plate-1", "patch": "wall-1", "physical_group": "fluid-1", "component": "folded", "provenance": "explicit-step-map"},
    ]
    return positions, triangles, ridge, normals, semantics


def test_folded_plate_bl0_bl1_bl3_persisted_and_repeatable(tmp_path: Path) -> None:
    args = _case()
    for layers, growth in ((0, 1.0), (1, 1.0), (3, 1.2)):
        result = produce_folded_plate_evidence(
            tmp_path / f"evidence-{layers}", *args,
            # Keep the three-layer geometric stack inside the strict metric
            # envelope; the producer must reject over-thick schedules.
            requested_layers=layers, first_height=0.20,
            growth_ratio=growth, strict_quality=True,
        )
        assert result["accepted"] is True, result
        assert len(set(result["run_digests"])) == 1
        producer = result["producer"]
        assert producer["actual_layers"] == layers
        assert producer["quality"]["dihedral_degrees"] == 90.0
        assert producer["quality"]["duplicate"] == 0
        assert producer["quality"]["non_manifold"] == 0
        if layers:
            assert len(producer["provenance"]) >= 2 * layers
            assert all(row["role"] in {"strip", "residual"} for row in producer["provenance"])
            assert producer["quality"]["collision_predicate"] == "long-double-aabb-sat-filtered-v1"
            assert producer["quality"]["collision_uncertain"] == 0
            assert producer["quality"]["collision_contacts"] == 0
        else:
            assert producer["status"] == "disabled_identity"
        assert Path(result["evidence_root"], "evidence.json").is_file()
        assert Path(result["evidence_root"], "lineage.json").is_file()


def test_folded_plate_rejects_missing_semantics_atomically(tmp_path: Path) -> None:
    positions, triangles, ridge, normals, semantics = _case()
    semantics[1] = {**semantics[1], "physical_group": ""}
    result = produce_folded_plate_evidence(
        tmp_path / "rejected", positions, triangles, ridge, normals,
        semantics, requested_layers=1, first_height=0.25, growth_ratio=1.0,
    )
    assert result["accepted"] is False
    assert result["candidate_discarded"] is True
    assert result["atomic_rollback"] is True
    assert not (tmp_path / "rejected").exists()


def test_folded_plate_rejects_over_thick_schedule_for_quality(tmp_path: Path) -> None:
    result = produce_folded_plate_evidence(
        tmp_path / "over-thick", *_case(), requested_layers=3,
        first_height=0.25, growth_ratio=1.2, strict_quality=True,
    )
    assert result["accepted"] is False
    assert result["candidate_discarded"] is True
    assert result["atomic_rollback"] is True
    assert not (tmp_path / "over-thick").exists()
