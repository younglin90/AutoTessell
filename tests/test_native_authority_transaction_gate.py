from __future__ import annotations

from core.evaluator.native_baseline_manifest import build_baseline_manifest_v1
from core.evaluator.native_authority_transaction_gate import (
    commit_native_authority_transaction,
    evaluate_native_authority_transaction,
)


def _evidence(*, metric_distortion_max: float = 1.0) -> dict[str, float]:
    return {
        "non_orthogonality_p95": 20.0,
        "non_orthogonality_max": 35.0,
        "skewness_p95": 0.10,
        "skewness_max": 0.20,
        "metric_distortion_max": metric_distortion_max,
    }


def _topology() -> dict[str, int]:
    return {
        "invalid": 0,
        "duplicate": 0,
        "non_manifold": 0,
        "self_intersecting": 0,
        "inverted": 0,
        "negative_measure": 0,
    }


def test_bl0_requires_exact_baseline_identity_and_commits() -> None:
    baseline = {"mesh": [1, 2], "provenance": "p"}
    destination = {"old": True}
    result = evaluate_native_authority_transaction(
        baseline,
        baseline,
        requested_layers=0,
        actual_layers=0,
        source_sha256="source",
        candidate_source_sha256="source",
        topology=_topology(),
        quality=_evidence(),
        authority_complete=True,
    )
    commit_native_authority_transaction(destination, baseline, result)
    assert result.accepted and result.committed and not result.rolled_back
    assert destination == baseline


def test_positive_bl_requires_complete_layers_and_commits_atomically() -> None:
    baseline = {"mesh": [1]}
    candidate = {"mesh": [1, 2], "layers": 2}
    destination: dict[str, object] = {"mesh": [0]}
    result = evaluate_native_authority_transaction(
        baseline,
        candidate,
        requested_layers=2,
        actual_layers=2,
        source_sha256="source",
        candidate_source_sha256="source",
        topology=_topology(),
        quality=_evidence(),
        authority_complete=True,
    )
    commit_native_authority_transaction(destination, candidate, result)
    assert result.accepted and destination == candidate


def test_quality_or_authority_failure_rolls_back_without_mutation() -> None:
    baseline = {"mesh": [1]}
    candidate = {"mesh": [1, 2]}
    destination: dict[str, object] = {"mesh": [1]}
    before = dict(destination)
    result = evaluate_native_authority_transaction(
        baseline,
        candidate,
        requested_layers=1,
        actual_layers=1,
        source_sha256="source",
        candidate_source_sha256="stale-source",
        topology=_topology(),
        quality=_evidence(metric_distortion_max=4.0),
        authority_complete=False,
    )
    commit_native_authority_transaction(destination, candidate, result)
    assert not result.accepted and result.rolled_back
    assert destination == before
    assert "source_output_binding_mismatch" in result.reasons
    assert "quality:metric_distortion_max" in result.reasons


def _baseline_manifest(tmp_path: Path) -> dict[str, object]:
    artifact_root = tmp_path / "stage"
    artifact_root.mkdir(parents=True)
    (artifact_root / "polyMesh").write_text("mesh", encoding="utf-8")
    return build_baseline_manifest_v1(
        engine="tet",
        product_kind="volume",
        source={
            "kind": "stl",
            "bytes": "bytes",
            "canonical_geometry": "geometry",
            "authority_certificate": {"sha": "source"},
            "parser_version": "stl-reader-v1",
            "unit_orientation_profile": "mm-right-handed",
        },
        mesh={
            "geometry": "mesh-geometry",
            "topology": "mesh-topology",
            "artifact_tree": {"points": "points"},
            "boundary_binding": {"wall": [1]},
            "feature_patch_group_multimap": {"wall": "wall"},
            "component": [0],
            "provenance": {"source_face": 1},
        },
        route_context={"route_contract": "native-tet-v1", "native_build_manifest": "build-a"},
        artifact_root=artifact_root,
    )


def test_manifest_pair_is_required_and_exact_bl0_pair_is_accepted(tmp_path: Path) -> None:
    baseline_manifest = _baseline_manifest(tmp_path)
    missing_pair = evaluate_native_authority_transaction(
        {"mesh": [1]},
        {"mesh": [1]},
        requested_layers=0,
        actual_layers=0,
        source_sha256="source",
        candidate_source_sha256="source",
        topology=_topology(),
        quality=_evidence(),
        authority_complete=True,
        baseline_manifest=baseline_manifest,
    )
    assert not missing_pair.accepted
    assert "baseline_manifest_pair_required" in missing_pair.reasons

    accepted = evaluate_native_authority_transaction(
        {"mesh": [1]},
        {"mesh": [1]},
        requested_layers=0,
        actual_layers=0,
        source_sha256="source",
        candidate_source_sha256="source",
        topology=_topology(),
        quality=_evidence(),
        authority_complete=True,
        baseline_manifest=baseline_manifest,
        candidate_manifest=baseline_manifest,
    )
    assert accepted.accepted


def test_manifest_mutation_refuses_bl0_transaction(tmp_path: Path) -> None:
    baseline_manifest = _baseline_manifest(tmp_path)
    candidate_manifest = dict(baseline_manifest)
    candidate_manifest["manifest_sha256"] = "0" * 64
    result = evaluate_native_authority_transaction(
        {"mesh": [1]},
        {"mesh": [1]},
        requested_layers=0,
        actual_layers=0,
        source_sha256="source",
        candidate_source_sha256="source",
        topology=_topology(),
        quality=_evidence(),
        authority_complete=True,
        baseline_manifest=baseline_manifest,
        candidate_manifest=candidate_manifest,
    )
    assert not result.accepted
    assert any(reason.startswith("baseline_manifest:") for reason in result.reasons)
