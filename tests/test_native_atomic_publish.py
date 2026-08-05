from __future__ import annotations

from pathlib import Path

import pytest

native_atomic_publish = pytest.importorskip("native_atomic_publish")


def test_same_filesystem_stage_and_atomic_exchange_retains_rollback_backup(tmp_path: Path) -> None:
    destination = tmp_path / "polyMesh"
    destination.mkdir()
    (destination / "artifact").write_text("old", encoding="utf-8")
    stage = Path(native_atomic_publish.make_stage(str(destination)))
    (stage / "artifact").write_text("new", encoding="utf-8")
    result = native_atomic_publish.publish_stage(str(destination), str(stage))
    assert result["accepted"] and result["atomic"] and result["fsynced"]
    assert (destination / "artifact").read_text(encoding="utf-8") == "new"
    backup = Path(result["rollback_backup"])
    assert backup.is_dir()
    assert (backup / "artifact").read_text(encoding="utf-8") == "old"
    native_atomic_publish.discard_stage(str(backup))
    assert not backup.exists()


def test_publish_to_missing_destination_is_atomic_and_consumes_stage(tmp_path: Path) -> None:
    destination = tmp_path / "polyMesh"
    stage = Path(native_atomic_publish.make_stage(str(destination)))
    (stage / "artifact").write_text("new", encoding="utf-8")
    result = native_atomic_publish.publish_stage(str(destination), str(stage))
    assert result["accepted"] and result["atomic"]
    assert destination.is_dir()
    assert (destination / "artifact").read_text(encoding="utf-8") == "new"
    assert not stage.exists()
    assert result["rollback_backup"] is None


def test_stage_sibling_and_owned_name_are_fail_closed(tmp_path: Path) -> None:
    destination = tmp_path / "polyMesh"
    destination.mkdir()
    foreign = tmp_path / "foreign" / "nested"
    foreign.mkdir(parents=True)
    (foreign / "artifact").write_text("x", encoding="utf-8")
    with pytest.raises(RuntimeError, match="stage_must_be_destination_sibling"):
        native_atomic_publish.publish_stage(str(destination), str(foreign))
    with pytest.raises(RuntimeError, match="stage_name_not_owned"):
        native_atomic_publish.discard_stage(str(foreign))
