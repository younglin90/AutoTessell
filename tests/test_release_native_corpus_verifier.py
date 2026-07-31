"""Focused fail-closed contracts for release-native corpus evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.release_native_corpus_verifier import (
    _polymesh_identity,
    verify_release_native_corpus,
)

_REQUIRED_CASES = (
    ("native-tet-cube", "tier_native_tet", "tet"),
    ("native-tet-sphere", "tier_native_tet", "tet"),
    ("native-hex-cube", "tier_native_hex", "hex_dominant"),
    ("native-poly-cube", "tier_native_poly", "poly"),
)


def _write_run(
    root: Path,
    *,
    tier_evaluated: str = "tier_native_tet",
    mesh_type: str = "tet",
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
                    "tier_evaluated": tier_evaluated,
                    "mesh_type": mesh_type,
                    "checker_engine_used": "native",
                    "quality_level": "draft",
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
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    case_runs: dict[str, tuple[Path, Path, Path]] = {
        "native-tet-cube": (first, second, third),
    }
    for case_id, tier_evaluated, mesh_type in _REQUIRED_CASES[1:]:
        runs = tuple(source_root.parent / f"{case_id}-run-{index}" for index in range(3))
        for root in runs:
            _write_run(root, tier_evaluated=tier_evaluated, mesh_type=mesh_type)
        case_runs[case_id] = runs

    cases: list[dict[str, object]] = []
    artifact_dirs: list[str] = []
    for case_id, tier_evaluated, mesh_type in _REQUIRED_CASES:
        runs = case_runs[case_id]
        run_rows: list[dict[str, object]] = []
        for root in runs:
            identity = _polymesh_identity(root)
            assert identity is not None
            report_path = root / "quality-report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["evaluation_summary"]["gate4_evidence"]["source"] = {"sha256": source_hash}
            report["evaluation_summary"]["gate4_evidence"]["output"] = identity
            report_path.write_text(json.dumps(report), encoding="utf-8")
            run_rows.append(
                {
                    "artifact_dir": str(root.resolve()),
                    "poly_mesh": identity,
                    "quality_report": "quality-report.json",
                    "quality_report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
                }
            )
            artifact_dirs.append(str(root.resolve()))
        cases.append(
            {
                "id": case_id,
                "native_product_contract": {
                    "tier_evaluated": tier_evaluated,
                    "mesh_type": mesh_type,
                    "checker_engine_used": "native",
                    "quality_level": "draft",
                },
                "source_snapshot": {
                    "artifact_dir": str(source_root.resolve()),
                    "path": "source.stl",
                    "sha256": source_hash,
                },
                "runs": run_rows,
            }
        )
    return {
        "schema": "autotessell/release-native-corpus/v1",
        "cases": cases,
        "_test_artifact_dirs": artifact_dirs,
    }


def _verify(manifest: dict[str, object]) -> dict[str, object]:
    return verify_release_native_corpus(manifest, manifest["_test_artifact_dirs"])


def test_complete_bounded_evidence_still_never_returns_release_pass(tmp_path: Path) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first)
    _write_run(second)
    _write_run(third)
    manifest = _manifest(first, first, second, third)

    report = _verify(manifest)

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
    assert row["runs"][0]["native_product_contract"] == {
        "checker_engine_used": "native",
        "mesh_type": "tet",
        "quality_level": "draft",
        "tier_evaluated": "tier_native_tet",
    }
    assert row["runs"][0]["gate4_attestation"] == {
        "source_sha256": hashlib.sha256((first / "source.stl").read_bytes()).hexdigest(),
        "poly_mesh": _polymesh_identity(first),
    }


def test_required_native_matrix_rejects_missing_extra_and_contract_mismatch(tmp_path: Path) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first)
    _write_run(second)
    _write_run(third)
    manifest = _manifest(first, first, second, third)

    report = _verify(manifest)

    assert report["reason"] == "release_gate_evidence_incomplete"
    assert [row["id"] for row in report["cases"]] == [
        "native-tet-cube",
        "native-tet-sphere",
        "native-hex-cube",
        "native-poly-cube",
    ]

    manifest = _manifest(first, first, second, third)
    manifest["cases"].pop()
    report = _verify(manifest)
    assert report == {
        "status": "UNVERIFIED",
        "reason": "required_native_case_missing",
        "cases": (),
    }

    manifest = _manifest(first, first, second, third)
    strict_quad = json.loads(json.dumps(manifest["cases"][0]))
    strict_quad["id"] = "native-strict-quad-cube"
    manifest["cases"].append(strict_quad)
    report = _verify(manifest)
    assert report == {
        "status": "UNVERIFIED",
        "reason": "required_native_case_extra",
        "cases": (),
    }

    manifest = _manifest(first, first, second, third)
    manifest["cases"][1]["native_product_contract"]["mesh_type"] = "quad"
    report = _verify(manifest)
    assert report == {
        "status": "UNVERIFIED",
        "reason": "required_native_case_contract_mismatch",
        "cases": (),
    }


def test_exactly_two_runs_are_unverified_before_artifact_inspection(tmp_path: Path) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first)
    _write_run(second)
    _write_run(third)
    manifest = _manifest(first, first, second, third)
    manifest["cases"][0]["runs"] = manifest["cases"][0]["runs"][:2]

    report = _verify(manifest)

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "repeat_runs_required"


def test_case_ids_and_run_artifacts_are_unique_across_the_manifest(tmp_path: Path) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first)
    _write_run(second)
    _write_run(third)
    manifest = _manifest(first, first, second, third)
    manifest["cases"].append(json.loads(json.dumps(manifest["cases"][0])))

    report = _verify(manifest)

    assert report == {"status": "UNVERIFIED", "reason": "duplicate_case_id", "cases": ()}

    manifest = _manifest(first, first, second, third)
    manifest["cases"][1]["runs"][0]["artifact_dir"] = manifest["cases"][0]["runs"][0][
        "artifact_dir"
    ]

    report = _verify(manifest)

    assert report == {
        "status": "UNVERIFIED",
        "reason": "artifact_dir_reused_across_cases",
        "cases": (),
    }


def test_polymesh_change_after_manifest_is_unverified(tmp_path: Path) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first)
    _write_run(second)
    _write_run(third)
    manifest = _manifest(first, first, second, third)
    (second / "constant" / "polyMesh" / "points").write_text("changed", encoding="utf-8")

    report = _verify(manifest)

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "polymesh_identity_mismatch"


def test_negative_volume_or_missing_gate4_inventory_is_unverified(tmp_path: Path) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first, negative_volumes=1)
    _write_run(second)
    _write_run(third)
    manifest = _manifest(first, first, second, third)

    report = _verify(manifest)

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "negative_volumes_not_zero"

    _write_run(first, negative_volumes=0, unverified_fields=[])
    manifest = _manifest(first, first, second, third)
    report = _verify(manifest)

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "invalid_quality_report_schema"


def test_repeat_hash_mismatch_is_unverified_even_when_each_identity_matches(tmp_path: Path) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first)
    _write_run(second)
    _write_run(third)
    (second / "constant" / "polyMesh" / "faces").write_text("different-faces", encoding="utf-8")
    manifest = _manifest(first, first, second, third)

    report = _verify(manifest)

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

    report = _verify(manifest)

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "missing_quality_report"


def test_quality_report_hash_is_required_and_exact(tmp_path: Path) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first)
    _write_run(second)
    _write_run(third)
    manifest = _manifest(first, first, second, third)
    manifest["cases"][0]["runs"][0].pop("quality_report_sha256")

    report = _verify(manifest)

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "quality_report_hash_required"

    manifest = _manifest(first, first, second, third)
    manifest["cases"][0]["runs"][0]["quality_report_sha256"] = "A" * 64
    report = _verify(manifest)

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "quality_report_hash_required"

    manifest = _manifest(first, first, second, third)
    (second / "quality-report.json").write_bytes(
        (second / "quality-report.json").read_bytes() + b"\n"
    )
    report = _verify(manifest)

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "quality_report_hash_mismatch"


def test_native_product_contract_is_required_typed_and_exact(tmp_path: Path) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first)
    _write_run(second)
    _write_run(third)
    manifest = _manifest(first, first, second, third)
    manifest["cases"][0].pop("native_product_contract")

    report = _verify(manifest)

    assert report["status"] == "UNVERIFIED"
    assert report == {
        "status": "UNVERIFIED",
        "reason": "required_native_case_contract_mismatch",
        "cases": (),
    }

    manifest = _manifest(first, first, second, third)
    manifest["cases"][0]["native_product_contract"]["quality_level"] = 0
    report = _verify(manifest)

    assert report["status"] == "UNVERIFIED"
    assert report == {
        "status": "UNVERIFIED",
        "reason": "required_native_case_contract_mismatch",
        "cases": (),
    }

    manifest = _manifest(first, first, second, third)
    manifest["cases"][0]["native_product_contract"] = {
        "tier_evaluated": "tier_native_tet",
        "mesh_type": "tet",
        "checker_engine_used": "native",
    }
    report = _verify(manifest)

    assert report["status"] == "UNVERIFIED"
    assert report == {
        "status": "UNVERIFIED",
        "reason": "required_native_case_contract_mismatch",
        "cases": (),
    }

    manifest = _manifest(first, first, second, third)
    report_path = first / "quality-report.json"
    report_value = json.loads(report_path.read_text(encoding="utf-8"))
    report_value["evaluation_summary"]["mesh_type"] = "hex_dominant"
    report_path.write_text(json.dumps(report_value), encoding="utf-8")
    manifest["cases"][0]["runs"][0]["quality_report_sha256"] = hashlib.sha256(
        report_path.read_bytes()
    ).hexdigest()
    report = _verify(manifest)

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "native_product_contract_mismatch"


def test_quality_report_gate4_identity_is_required_and_crossbound(tmp_path: Path) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first)
    _write_run(second)
    _write_run(third)
    manifest = _manifest(first, first, second, third)
    report_path = first / "quality-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["evaluation_summary"]["gate4_evidence"].pop("output")
    report_path.write_text(json.dumps(report), encoding="utf-8")
    manifest["cases"][0]["runs"][0]["quality_report_sha256"] = hashlib.sha256(
        report_path.read_bytes()
    ).hexdigest()

    outcome = _verify(manifest)

    assert outcome["status"] == "UNVERIFIED"
    assert outcome["cases"][0]["reason"] == "quality_report_gate4_identity_invalid"

    manifest = _manifest(first, first, second, third)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["evaluation_summary"]["gate4_evidence"]["source"]["sha256"] = "0" * 64
    report_path.write_text(json.dumps(report), encoding="utf-8")
    manifest["cases"][0]["runs"][0]["quality_report_sha256"] = hashlib.sha256(
        report_path.read_bytes()
    ).hexdigest()
    outcome = _verify(manifest)

    assert outcome["status"] == "UNVERIFIED"
    assert outcome["cases"][0]["reason"] == "quality_report_source_identity_mismatch"

    manifest = _manifest(first, first, second, third)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["evaluation_summary"]["gate4_evidence"]["output"]["sha256"] = "0" * 64
    report_path.write_text(json.dumps(report), encoding="utf-8")
    manifest["cases"][0]["runs"][0]["quality_report_sha256"] = hashlib.sha256(
        report_path.read_bytes()
    ).hexdigest()
    outcome = _verify(manifest)

    assert outcome["status"] == "UNVERIFIED"
    assert outcome["cases"][0]["reason"] == "quality_report_output_identity_mismatch"


def test_legacy_top_level_fields_are_explicitly_supported_but_ambiguous_shape_rejects(
    tmp_path: Path,
) -> None:
    first, second, third = tmp_path / "run-one", tmp_path / "run-two", tmp_path / "run-three"
    _write_run(first, legacy_gate4_fields=True)
    _write_run(second, legacy_gate4_fields=True)
    _write_run(third, legacy_gate4_fields=True)
    manifest = _manifest(first, first, second, third)

    report = _verify(manifest)

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

    report = _verify(manifest)

    assert report["status"] == "UNVERIFIED"
    assert report["cases"][0]["reason"] == "invalid_quality_report_schema"
