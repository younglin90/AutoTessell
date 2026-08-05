from __future__ import annotations

from pathlib import Path

from core.evaluator.native_poly_bl_producer_certificate import canonical_sha256
from core.evaluator.native_poly_source_ledger import ledger_sha256
from core.evaluator.native_poly_bl_private_stage import (
    polymesh_hashes,
    prepare_private_poly_bl_stage,
    run_private_poly_bl_trace,
)


_POLY = {
    "points": "points\n",
    "faces": "faces\n",
    "owner": "owner\n",
    "neighbour": "neighbour\n",
    "boundary": "boundary\n",
}


def _source(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    case = tmp_path / "source"
    poly = case / "constant" / "polyMesh"
    poly.mkdir(parents=True)
    for name, content in _POLY.items():
        (poly / name).write_text(content, encoding="utf-8")
    hashes = polymesh_hashes(case)
    ledger = {
        "schema": "native-poly-source-ledger/v1",
        "producer": "authoritative-test-ingress",
        "source_kind": "stl",
        "raw_source_sha256": "f" * 64,
        "importer": {"name": "test-stl-reader", "version": "1"},
        "authority_source": {"status": "source_authored", "id": "test-sidecar", "raw_source_sha256": "f" * 64},
        "lineage_mode": "primal_1_to_1",
        "immutable": True,
        "polymesh_sha256": hashes,
        "source_sha256": canonical_sha256(hashes),
        "authority": {name: True for name in ("source_face", "wall_edge", "patch", "feature", "physical_group", "component")},
        "selected_polymesh_face_indices": [0],
        "source_faces": [{
            "polymesh_face_index": 0,
            "source_face_id": 0,
            "ordered_vertex_ids": [0, 1, 2],
            "canonical_vertex_ids": [0, 1, 2],
            "patch_id": "wall",
            "feature_id": "f0",
            "physical_group": "wall",
            "component_id": "component-0",
        }],
        "wall_edges": [
            {"edge_id": 0, "vertex_ids": [0, 1], "incident_source_face_ids": [0]},
        ],
    }
    ledger["ledger_sha256"] = ledger_sha256(ledger)
    return case, ledger


def _trace() -> dict[str, object]:
    return {
        "source_faces": [{
            "source_face_id": 0,
            "ordered_vertex_ids": [0, 1, 2],
            "canonical_vertex_ids": [0, 1, 2],
            "patch_id": "wall",
            "feature_id": "f0",
            "physical_group": "wall",
            "component_id": "component-0",
        }],
        "wall_edges": [{"edge_id": 0, "vertex_ids": [0, 1], "incident_source_face_ids": [0]}],
        "layer_entities": [{
            "layer": 1,
            "source_face_id": 0,
            "generated_vertex_ids": [3, 4, 5],
            "generated_face_ids": [10],
            "generated_cell_ids": [1],
        }],
        "outer_front": [{"final_face_id": 20, "source_face_id": 0, "layer": 1, "cell_id": 1}],
        "cell_partitions": {"core": [0], "boundary_layer": [1], "transition": []},
        "final_cell_ids": [0, 1],
        "actual_layers": 1,
        "total_thickness": 0.1,
        "candidate_file_sha256": {"points": "b" * 64, "faces": "c" * 64},
        "transition_not_applicable": True,
    }


def test_bl0_clones_private_stage_and_bypasses_producer(tmp_path: Path) -> None:
    source, ledger = _source(tmp_path)
    called = []
    result = run_private_poly_bl_trace(
        source, tmp_path / "stage", ledger, requested_layers=0,
        producer_callback=lambda *_: called.append(True),
    )
    assert result["status"] == "PASS"
    assert result["producer_called"] is False
    assert called == []
    assert result["source_polymesh_sha256"] == result["stage_polymesh_sha256"]
    assert not (tmp_path / "stage" / "native_bl_provenance.v2.json").exists()


def test_bl1_emits_v2_sidecars_only_in_private_stage(tmp_path: Path) -> None:
    source, ledger = _source(tmp_path)
    result = run_private_poly_bl_trace(
        source, tmp_path / "stage", ledger, requested_layers=1,
        producer_callback=lambda _stage, _ledger: _trace(),
    )
    assert result["status"] == "PASS"
    assert result["publish_allowed"] is False
    assert Path(result["provenance_path"]).is_file()
    assert not (source / "native_bl_provenance.v2.json").exists()


def test_preflight_rejects_same_stage_or_ledger_digest_mismatch(tmp_path: Path) -> None:
    source, ledger = _source(tmp_path)
    same = prepare_private_poly_bl_stage(source, source, ledger)
    assert same["reason"] == "stage_equals_source"
    bad = dict(ledger)
    bad["polymesh_sha256"] = {name: "0" * 64 for name in _POLY}
    result = prepare_private_poly_bl_stage(source, tmp_path / "bad", bad)
    assert result["reason"] == "source_ledger_polymesh_digest_mismatch"


def test_callback_timeout_or_dualization_refuses_and_removes_stage(tmp_path: Path) -> None:
    source, ledger = _source(tmp_path)
    timeout = run_private_poly_bl_trace(
        source, tmp_path / "timeout", ledger, requested_layers=1,
        producer_callback=lambda *_: (_ for _ in ()).throw(TimeoutError("budget")),
    )
    assert timeout["status"] == "TIMEOUT"
    assert not (tmp_path / "timeout").exists()
    dual = run_private_poly_bl_trace(
        source, tmp_path / "dual", ledger, requested_layers=1, apply_bulk_dual=True,
    )
    assert dual["reason"] == "dualization_not_supported"


def test_source_mutation_is_refused_and_private_stage_is_rolled_back(tmp_path: Path) -> None:
    source, ledger = _source(tmp_path)

    def mutate(source_stage: Path, _ledger):
        (source / "constant" / "polyMesh" / "faces").write_text("mutated", encoding="utf-8")
        return _trace()

    result = run_private_poly_bl_trace(source, tmp_path / "mutate", ledger, requested_layers=1, producer_callback=mutate)
    assert result["status"] == "REFUSED"
    assert result["reason"] == "producer_trace_invalid:source_case_mutated"
    assert not (tmp_path / "mutate").exists()
