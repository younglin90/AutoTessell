from __future__ import annotations

from pathlib import Path

from core.evaluator.native_volume_transaction_adapter import (
    evaluate_and_publish_native_volume_artifact,
)


def _evidence(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "invalid": 0, "duplicate": 0, "non_manifold": 0,
        "self_intersecting": 0, "inverted": 0, "negative_measure": 0,
        "non_orthogonality_p95": 20.0, "non_orthogonality_max": 35.0,
        "skewness_p95": 0.1, "skewness_max": 0.2,
        "metric_distortion_max": 1.0,
        "source_sha256": "source", "candidate_source_sha256": "source",
        "authority_complete": True, "collision_free": True,
    }
    value.update(overrides)
    return value


def _stage(root: Path, name: str, value: str) -> Path:
    path = root / name
    path.mkdir()
    (path / "artifact.txt").write_text(value, encoding="utf-8")
    return path


def test_bl0_identity_swaps_staged_artifact(tmp_path: Path) -> None:
    destination = tmp_path / "polyMesh"
    _stage(tmp_path, "polyMesh", "old")
    staged = _stage(tmp_path, "staged", "baseline")
    baseline = {"mesh": [1], "provenance": "same"}
    result = evaluate_and_publish_native_volume_artifact(
        destination, staged, baseline, baseline,
        requested_layers=0, actual_layers=0, evidence=_evidence(),
    )
    assert result.published and result.transaction.accepted
    assert (destination / "artifact.txt").read_text(encoding="utf-8") == "baseline"


def test_positive_bl_commits_and_failed_quality_keeps_destination(tmp_path: Path) -> None:
    destination = tmp_path / "polyMesh"
    _stage(tmp_path, "polyMesh", "old")
    staged = _stage(tmp_path, "staged", "candidate")
    baseline = {"mesh": [1]}
    candidate = {"mesh": [1, 2], "layers": 1}
    refused = evaluate_and_publish_native_volume_artifact(
        destination, staged, baseline, candidate,
        requested_layers=1, actual_layers=1,
        evidence=_evidence(skewness_max=0.9),
    )
    assert not refused.published and refused.transaction.rolled_back
    assert (destination / "artifact.txt").read_text(encoding="utf-8") == "old"
    assert staged.exists()


def test_missing_evidence_is_not_interpreted_as_zero(tmp_path: Path) -> None:
    destination = tmp_path / "polyMesh"
    _stage(tmp_path, "polyMesh", "old")
    staged = _stage(tmp_path, "staged", "candidate")
    result = evaluate_and_publish_native_volume_artifact(
        destination, staged, {"mesh": [1]}, {"mesh": [1, 2]},
        requested_layers=1, actual_layers=1,
        evidence={"source_sha256": "source"},
    )
    assert not result.published
    assert result.transaction.reasons[0].startswith("missing_required_evidence:")
    assert (destination / "artifact.txt").read_text(encoding="utf-8") == "old"
