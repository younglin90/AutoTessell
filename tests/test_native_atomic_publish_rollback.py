from __future__ import annotations

from pathlib import Path

import pytest


native_atomic_publish = pytest.importorskip("native_atomic_publish")


def test_exchange_publish_can_restore_baseline_after_destination_audit_refusal(tmp_path: Path) -> None:
    destination = tmp_path / "case"
    destination.mkdir()
    (destination / "artifact").write_text("baseline", encoding="utf-8")
    stage = Path(native_atomic_publish.make_stage(str(destination)))
    (stage / "artifact").write_text("candidate", encoding="utf-8")

    published = native_atomic_publish.publish_stage(str(destination), str(stage))
    backup = Path(str(published["rollback_backup"]))
    rollback = native_atomic_publish.rollback_stage(str(destination), str(backup))

    assert rollback["accepted"] is True
    assert rollback["restored_baseline"] is True
    assert (destination / "artifact").read_text(encoding="utf-8") == "baseline"
    assert not backup.exists()


def test_missing_destination_is_removed_after_destination_audit_refusal(tmp_path: Path) -> None:
    destination = tmp_path / "case"
    stage = Path(native_atomic_publish.make_stage(str(destination)))
    (stage / "artifact").write_text("candidate", encoding="utf-8")
    published = native_atomic_publish.publish_stage(str(destination), str(stage))

    rollback = native_atomic_publish.rollback_stage(str(destination), "")

    assert published["rollback_backup"] is None
    assert rollback["accepted"] is True
    assert rollback["restored_baseline"] is True
    assert not destination.exists()
