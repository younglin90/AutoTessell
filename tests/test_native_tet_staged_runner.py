from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.generator.native_tet import staged_runner


def test_runner_sees_only_private_stage_and_publish_is_after_readback(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "case"
    destination.mkdir()
    (destination / "old").write_text("old", encoding="utf-8")
    seen: list[Path] = []

    def runner(_vertices: object, _faces: object, stage: Path, **_kwargs: object) -> SimpleNamespace:
        seen.append(stage)
        assert stage != destination
        (stage / "mesh").write_text("new", encoding="utf-8")
        return SimpleNamespace(success=True, n_cells=1, n_points=4)

    audit = SimpleNamespace(valid=True, artifact_sha256="a", n_cells=1)
    result = staged_runner.run_tet_in_private_stage(
        runner, [[0.0, 0.0, 0.0]], [[0, 0, 0]], destination,
        audit_callback=lambda _stage: audit,
    )
    assert result.published and result.audit is audit
    assert seen and seen[0].name.startswith(".autotessell-stage-")
    assert (destination / "mesh").read_text(encoding="utf-8") == "new"
    backup = Path(result.publish["rollback_backup"])
    assert (backup / "old").read_text(encoding="utf-8") == "old"


def test_readback_refusal_keeps_destination_and_discards_stage(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "case"
    destination.mkdir()
    (destination / "old").write_text("old", encoding="utf-8")

    def runner(_vertices: object, _faces: object, stage: Path, **_kwargs: object) -> SimpleNamespace:
        (stage / "mesh").write_text("candidate", encoding="utf-8")
        return SimpleNamespace(success=True)

    result = staged_runner.run_tet_in_private_stage(
        runner, [], [], destination,
        audit_callback=lambda _stage: SimpleNamespace(valid=False, malformed_reason="bad_topology"),
    )
    assert not result.published
    assert result.refused_reason == "full_audit_refused"
    assert (destination / "old").read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".autotessell-stage-*"))


def test_runner_refusal_never_publishes(tmp_path: Path) -> None:
    destination = tmp_path / "case"
    destination.mkdir()
    (destination / "old").write_text("old", encoding="utf-8")

    def runner(_vertices: object, _faces: object, _stage: Path, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(success=False, message="writer refused")

    result = staged_runner.run_tet_in_private_stage(
        runner, [], [], destination, audit_callback=lambda _stage: SimpleNamespace(valid=True)
    )
    assert not result.published and result.refused_reason == "runner_refused"
    assert (destination / "old").read_text(encoding="utf-8") == "old"


def test_artifact_mutation_after_audit_refuses_publish(tmp_path: Path) -> None:
    destination = tmp_path / "case"
    destination.mkdir()
    (destination / "old").write_text("old", encoding="utf-8")

    def runner(_vertices: object, _faces: object, stage: Path, **_kwargs: object) -> SimpleNamespace:
        (stage / "mesh").write_text("candidate", encoding="utf-8")
        return SimpleNamespace(success=True)

    def mutating_audit(stage: Path) -> SimpleNamespace:
        (stage / "late-mutation").write_text("tampered", encoding="utf-8")
        return SimpleNamespace(valid=True)

    result = staged_runner.run_tet_in_private_stage(
        runner, [], [], destination, audit_callback=mutating_audit
    )
    assert not result.published
    assert result.refused_reason == "artifact_changed_after_audit"
    assert (destination / "old").read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".autotessell-stage-*"))


def test_positive_bl_contract_refuses_before_stage_without_sealed_authority(tmp_path: Path) -> None:
    destination = tmp_path / "case"
    destination.mkdir()
    (destination / "old").write_text("old", encoding="utf-8")
    result = staged_runner.run_tet_bl_contract_in_private_stage(
        destination,
        run_callback=lambda *_args: SimpleNamespace(success=True),
        audit_callback=lambda _stage: {"accepted": True},
        source_authority=None,
        requested_layers=1,
    )
    assert not result.published
    assert result.refused_reason == "native_tet_positive_bl_source_authority_missing"
    assert (destination / "old").read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".autotessell-stage-*"))


def test_positive_bl_contract_refuses_missing_sidecar_before_publish(tmp_path: Path) -> None:
    destination = tmp_path / "case"
    destination.mkdir()
    (destination / "old").write_text("old", encoding="utf-8")
    authority = {
        "accepted": True,
        "receipt_sealed": True,
        "direct_lineage": True,
        "source_sha256": "a" * 64,
        "wall_edge_eligible": True,
        "source_authority_status": "SOURCE_VERIFIED",
        "provisional": False,
    }

    def run_callback(stage: Path, _authority: dict, _run: int) -> SimpleNamespace:
        (stage / "candidate").write_text("actual-writer-output", encoding="utf-8")
        return SimpleNamespace(success=True)

    result = staged_runner.run_tet_bl_contract_in_private_stage(
        destination,
        run_callback=run_callback,
        audit_callback=lambda _stage: {
            "accepted": False,
            "reason": "native_tet_positive_bl_contract_audit_refused",
        },
        source_authority=authority,
        requested_layers=1,
    )
    assert not result.published
    assert result.refused_reason == (
        "native_tet_direct_id_capsule_unavailable:native_bl_capsule_missing"
    )
    assert (destination / "old").read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".autotessell-stage-*"))
    assert not list(tmp_path.glob(".autotessell-tet-bl-run-*"))


def test_zero_layer_contract_is_sidecar_free_and_repeatable(tmp_path: Path) -> None:
    destination = tmp_path / "case"
    destination.mkdir()
    (destination / "old").write_text("old", encoding="utf-8")
    runs: list[int] = []

    def audit(stage: Path) -> dict[str, object]:
        runs.append(1)
        assert not (stage / "evidence.atne").exists()
        assert not (stage / "binding.tsv").exists()
        assert not (stage / "layers.tsv").exists()
        return {"accepted": True}

    result = staged_runner.run_tet_bl_contract_in_private_stage(
        destination,
        run_callback=lambda *_args: SimpleNamespace(success=True),
        audit_callback=audit,
        source_authority=None,
        requested_layers=0,
    )
    assert result.published
    assert len(runs) == 3
    assert (destination / "old").read_text(encoding="utf-8") == "old"
