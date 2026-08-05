from __future__ import annotations

import copy
from pathlib import Path

import pytest

from core.evaluator.native_artifact_tree import fingerprint_staged_artifact_tree
from core.evaluator.native_baseline_manifest import (
    build_baseline_manifest_v1,
    compare_bl0_candidate_to_baseline,
    seal_immutable_baseline_manifest,
    validate_baseline_manifest_v1,
)


def _manifest(tmp_path: Path) -> dict[str, object]:
    artifact_root = tmp_path / "stage"
    artifact_root.mkdir(parents=True)
    (artifact_root / "polyMesh").write_text("points\nfaces\n", encoding="utf-8")
    return build_baseline_manifest_v1(
        engine="tet",
        product_kind="volume",
        source={
            "kind": "stl",
            "bytes": "stl-bytes",
            "canonical_geometry": [[0, 0, 0]],
            "authority_certificate": {"sha": "stl"},
            "parser_version": "stl-reader-v1",
            "unit_orientation_profile": "mm-right-handed",
        },
        mesh={
            "geometry": [[0, 0, 0]],
            "topology": [[0, 1, 2, 3]],
            "boundary_binding": {"wall": [1]},
            "feature_patch_group_multimap": {"wall": "fluid"},
            "component": [0],
            "provenance": {"source_face": 1},
        },
        route_context={"route_contract": "native-tet-v1", "native_build_manifest": "build-a"},
        artifact_root=artifact_root,
    )


def test_exact_bl0_identity_accepts_and_mutations_refuse(tmp_path: Path) -> None:
    baseline = _manifest(tmp_path)
    assert validate_baseline_manifest_v1(baseline) == (True, ())
    assert compare_bl0_candidate_to_baseline(copy.deepcopy(baseline), baseline)["accepted"]
    for key in ("source", "mesh", "route_context"):
        changed = copy.deepcopy(baseline)
        if key == "mesh":
            changed[key]["topology_sha256"] = "0" * 64
        else:
            changed[key][next(iter(changed[key]))] = "0" * 64
        changed["manifest_sha256"] = __import__(
            "core.evaluator.native_authority_transaction_gate",
            fromlist=["canonical_sha256"],
        ).canonical_sha256({k: v for k, v in changed.items() if k != "manifest_sha256"})
        result = compare_bl0_candidate_to_baseline(changed, baseline)
        assert not result["accepted"]


def test_key_order_and_path_like_context_do_not_change_digest(tmp_path: Path) -> None:
    first = _manifest(tmp_path)
    second = copy.deepcopy(first)
    second["route_context"] = dict(reversed(list(second["route_context"].items())))
    second["manifest_sha256"] = __import__(
        "core.evaluator.native_authority_transaction_gate",
        fromlist=["canonical_sha256"],
    ).canonical_sha256({k: v for k, v in second.items() if k != "manifest_sha256"})
    assert compare_bl0_candidate_to_baseline(second, first)["accepted"]


def test_seal_is_write_once_and_missing_fields_refuse(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    target = tmp_path / "baseline.json"
    seal_immutable_baseline_manifest(target, manifest)
    with pytest.raises(FileExistsError):
        seal_immutable_baseline_manifest(target, manifest)
    with pytest.raises(ValueError, match="source.parser_version_missing"):
        build_baseline_manifest_v1(
            engine="tet",
            product_kind="volume",
            source={
                "kind": "stl",
                "bytes": "stl",
                "canonical_geometry": "geometry",
                "authority_certificate": "cert",
                "unit_orientation_profile": "mm-right-handed",
            },
            mesh={},
            route_context={},
            artifact_root=tmp_path / "stage-missing",
        )


def test_stage_mutation_changes_fingerprint_and_manifest(tmp_path: Path) -> None:
    _manifest(tmp_path)
    before = fingerprint_staged_artifact_tree(tmp_path / "stage")
    (tmp_path / "stage" / "polyMesh").write_text("tampered", encoding="utf-8")
    after = fingerprint_staged_artifact_tree(tmp_path / "stage")
    assert before["tree_sha256"] != after["tree_sha256"]
