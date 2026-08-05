from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from core.generator.native_tet.staged_runner import run_tet_in_private_stage


def test_destination_audit_refusal_rolls_back_exchange(tmp_path: Path) -> None:
    destination = tmp_path / "case"
    destination.mkdir()
    (destination / "artifact").write_text("baseline", encoding="utf-8")

    def runner(_vertices: object, _faces: object, stage: Path, **_kwargs: object) -> SimpleNamespace:
        (stage / "artifact").write_text("candidate", encoding="utf-8")
        return SimpleNamespace(success=True)

    result = run_tet_in_private_stage(
        runner,
        [],
        [],
        destination,
        audit_callback=lambda _stage: {"accepted": True},
        post_publish_audit_callback=lambda _destination: {
            "accepted": False,
            "reason": "destination_graph_mismatch",
        },
    )

    assert result.published is False
    assert result.refused_reason == "destination_graph_mismatch"
    assert (destination / "artifact").read_text(encoding="utf-8") == "baseline"
    assert result.publish["rollback"]["restored_baseline"] is True
    assert not list(tmp_path.glob(".autotessell-stage-*"))


def test_destination_audit_pass_is_recorded_after_publish(tmp_path: Path) -> None:
    destination = tmp_path / "case"
    destination.mkdir()
    (destination / "old").write_text("baseline", encoding="utf-8")
    seen: list[Path] = []

    def runner(_vertices: object, _faces: object, stage: Path, **_kwargs: object) -> SimpleNamespace:
        (stage / "mesh").write_text("candidate", encoding="utf-8")
        return SimpleNamespace(success=True)

    def destination_audit(path: Path) -> dict[str, object]:
        seen.append(path)
        assert (path / "mesh").read_text(encoding="utf-8") == "candidate"
        return {"accepted": True, "reason": "destination_reread_pass"}

    result = run_tet_in_private_stage(
        runner,
        [],
        [],
        destination,
        audit_callback=lambda _stage: {"accepted": True},
        post_publish_audit_callback=destination_audit,
    )

    assert result.published is True
    assert result.destination_audit["accepted"] is True
    assert result.publish["destination_audit"]["reason"] == "destination_reread_pass"
    assert seen == [destination]
