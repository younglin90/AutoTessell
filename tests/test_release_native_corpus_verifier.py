"""Focused fail-closed contracts for release-native corpus evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.release_native_corpus_verifier import (
    _polymesh_identity,
    verify_release_native_corpus,
)


def _write_run(
    root: Path,
    *,
    negative_volumes: int = 0,
    unverified_fields: object = None,
    legacy_gate4_fields: bool = False,
) -> None:
    poly_mesh = root / "constant" / "polyMesh"
    poly_mesh.mkdir(parents=True, exist_ok=True)
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        (poly_mesh / name).write_text(f"stable-{name}", encoding="utf-8")
    fields = (
        ["distance.signed_mean", "patches.compared"]
        if unverified_fields is None
        else unverified_fields
    )
    (root / "quality-report.json").write_text(
        json.dumps(
            {
                "evaluation_summary": {
                    "checkmesh": {"negative_volumes": negative_volumes},
                    "gate4_evidence": (
                        {"gate4_pass": False, "unverified_fields": fields}
                        if legacy_gate4_fields
                        else {
                            "gate4_pass": False,
                            "actual_surface_metrics": {"unverified_fields": fields},
                        }
                    ),
                }
            }
        ),
        encoding="utf-8",
    )


def _manifest(source_root: Path, first: Path, second: Path, third: Path) -> dict[str, object]:
    source = source_root / "source.stl"
    source.write_bytes(b"frozen-source")
    first_identity = _polymesh_identity(first)
    second_identity = _polymesh_identity(second)
    third_identity = _polymesh_identity(third)
    assert first_identity is not None and second_identity is not None and third_identity is not None
    return {
        "schema": "autotessell/release-native-corpus/v1",
        "cases": [
            {
                "id": "native-tet-cube",
                "source_snapshot": {
                    "artifact_dir": str(source_root.resolve()),
                    "path": "source.stl",
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                },
                "runs": [
                    {
                        "artifact_dir": str(first.resolve()),
                        "poly_mesh": first_identity,
                        "quality_report": "quality-report.json",
                        "quality_report_sha256": hashlib.sha256(
                            (first / "quality-report.json").read_bytes()
                        ).hexdigest(),
                    },
                    {
                        "artifact_dir": str(second.resolve()),
                        "poly_mesh": second_identity,
                        "quality_report": "quality-report.json",
                        "quality_report_sha256": hashlib.sha256(
                            (second / "quality-report.json").read_bytes()
                        ).hexdigest(),
                    },
                    {
                        "artifact_dir": str(third.resolve()),
                        "poly_mesh": third_identity,
                        "quality_report": "quality-report.json",
                        "quality_report_sha256": hashlib.sha256(
                            (third / "quality-report.json").read_bytes()
                        ).hexdigest(),
                    },
                ],
            }
        ],
    }


def test_complete_bounded_evidence_still_never_returns_release_pass(tmp_path: Path) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first)
    _write_run(second)
    _write_run(third)
    manifest = _manifest(first, first, second, third)

    report = verify_release_native_corpus(manifest, [first, second, third])

    assert report["status"] == "UNVERIFIED"
    assert report["reason"] == "release_gate_evidence_incomplete"
    row = report["cases"][0]
    assert row["status"] == "UNVERIFIED"
    assert row["reason"] == "measured_evidence_release_incomplete"
    assert row["runs"][0]["gate4_unverified_fields"] == (
        "distance.signed_mean",
        "patches.compared",
    )
    assert (
        row["runs"][0]["quality_report_sha256"]
        == hashlib.sha256((first / "quality-report.json").read_bytes()).hexdigest()
    )


def test_exactly_two_runs_are_unverified_before_artifact_inspection(tmp_path: Path) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first)
    _write_run(second)
    _write_run(third)
    manifest = _manifest(first, first, second, third)
    manifest["cases"][0]["runs"] = manifest["cases"][0]["runs"][:2]

    report = verify_release_native_corpus(manifest, [first, second, third])

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "repeat_runs_required"


def test_polymesh_change_after_manifest_is_unverified(tmp_path: Path) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first)
    _write_run(second)
    _write_run(third)
    manifest = _manifest(first, first, second, third)
    (second / "constant" / "polyMesh" / "points").write_text("changed", encoding="utf-8")

    report = verify_release_native_corpus(manifest, [first, second, third])

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "polymesh_identity_mismatch"


def test_negative_volume_or_missing_gate4_inventory_is_unverified(tmp_path: Path) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first, negative_volumes=1)
    _write_run(second)
    _write_run(third)
    manifest = _manifest(first, first, second, third)

    report = verify_release_native_corpus(manifest, [first, second, third])

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "negative_volumes_not_zero"

    _write_run(first, negative_volumes=0, unverified_fields=[])
    manifest = _manifest(first, first, second, third)
    report = verify_release_native_corpus(manifest, [first, second, third])

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "invalid_quality_report_schema"


def test_repeat_hash_mismatch_is_unverified_even_when_each_identity_matches(tmp_path: Path) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first)
    _write_run(second)
    _write_run(third)
    (second / "constant" / "polyMesh" / "faces").write_text("different-faces", encoding="utf-8")
    manifest = _manifest(first, first, second, third)

    report = verify_release_native_corpus(manifest, [first, second, third])

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "repeat_polymesh_hash_mismatch"


def test_split_legacy_reports_cannot_replace_one_quality_report(tmp_path: Path) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first)
    _write_run(second)
    _write_run(third)
    manifest = _manifest(first, first, second, third)
    for run in manifest["cases"][0]["runs"]:
        run.pop("quality_report")
        run["native_checker_report"] = "native-checker.json"
        run["gate4_evidence"] = "gate4-evidence.json"

    report = verify_release_native_corpus(manifest, [first, second, third])

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "missing_quality_report"


def test_quality_report_hash_is_required_and_exact(tmp_path: Path) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first)
    _write_run(second)
    _write_run(third)
    manifest = _manifest(first, first, second, third)
    manifest["cases"][0]["runs"][0].pop("quality_report_sha256")

    report = verify_release_native_corpus(manifest, [first, second, third])

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "quality_report_hash_required"

    manifest = _manifest(first, first, second, third)
    manifest["cases"][0]["runs"][0]["quality_report_sha256"] = "A" * 64
    report = verify_release_native_corpus(manifest, [first, second, third])

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "quality_report_hash_required"

    manifest = _manifest(first, first, second, third)
    (second / "quality-report.json").write_bytes(
        (second / "quality-report.json").read_bytes() + b"\n"
    )
    report = verify_release_native_corpus(manifest, [first, second, third])

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "quality_report_hash_mismatch"


def test_legacy_top_level_fields_are_explicitly_supported_but_ambiguous_shape_rejects(
    tmp_path: Path,
) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first, legacy_gate4_fields=True)
    _write_run(second, legacy_gate4_fields=True)
    _write_run(third, legacy_gate4_fields=True)
    manifest = _manifest(first, first, second, third)

    report = verify_release_native_corpus(manifest, [first, second, third])

    assert report["cases"][0]["reason"] == "measured_evidence_release_incomplete"
    report_path = first / "quality-report.json"
    value = json.loads(report_path.read_text(encoding="utf-8"))
    value["evaluation_summary"]["gate4_evidence"]["actual_surface_metrics"] = {
        "unverified_fields": ["distance.signed_mean"]
    }
    report_path.write_text(json.dumps(value), encoding="utf-8")
    manifest["cases"][0]["runs"][0]["quality_report_sha256"] = hashlib.sha256(
        report_path.read_bytes()
    ).hexdigest()

    report = verify_release_native_corpus(manifest, [first, second, third])

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "invalid_quality_report_schema"
