"""Cycle39 crash-window tests for the directory-level hex BL transaction."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

_TOKEN = "0123456789abcdef0123456789abcdef"


def _tree(path: Path, label: str) -> None:
    path.mkdir(parents=True)
    (path / "identity").write_text(label, encoding="ascii")
    (path / "cellZones").write_bytes(f"zones-{label}".encode("ascii"))


def _identity(path: Path) -> str:
    return (path / "identity").read_text(encoding="ascii")


def _paths(constant: Path):
    from core.layers.native_hex_inward_transaction import _validated_paths

    return _validated_paths(constant, _TOKEN)


def _marker(paths, state: str) -> None:
    paths.marker.write_text(
        json.dumps(
            {"version": 1, "token": paths.token, "state": state},
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="ascii",
    )


def _recover(constant: Path) -> str:
    from core.layers.native_hex_inward_lock import acquire_hexbl_transaction_lock
    from core.layers.native_hex_inward_transaction import recover_hexbl_transaction

    with acquire_hexbl_transaction_lock(constant) as lock:
        return recover_hexbl_transaction(lock)


def _assert_clean(paths) -> None:
    assert not paths.marker.exists()
    assert not paths.marker_update.exists()
    assert not paths.stage_root.exists()
    assert not paths.candidate.exists()
    assert not paths.backup.exists()


def test_recovery_cleans_interrupted_staging_and_keeps_target(tmp_path: Path) -> None:
    constant = tmp_path / "constant"
    constant.mkdir()
    paths = _paths(constant)
    _tree(paths.target, "old")
    _tree(paths.stage_root, "partial")
    _marker(paths, "staging")

    assert _recover(constant) == "rolled_back_before_backup"
    assert _identity(paths.target) == "old"
    _assert_clean(paths)


def test_recovery_restores_backup_after_first_rename(tmp_path: Path) -> None:
    constant = tmp_path / "constant"
    constant.mkdir()
    paths = _paths(constant)
    _tree(paths.target, "old")
    _tree(paths.candidate, "new")
    _tree(paths.stage_root, "stage")
    os.replace(paths.target, paths.backup)
    _marker(paths, "backed_up")

    assert _recover(constant) == "restored_backup"
    assert _identity(paths.target) == "old"
    _assert_clean(paths)


def test_recovery_finalizes_candidate_after_second_rename(tmp_path: Path) -> None:
    constant = tmp_path / "constant"
    constant.mkdir()
    paths = _paths(constant)
    _tree(paths.target, "old")
    _tree(paths.candidate, "new")
    _tree(paths.stage_root, "stage")
    os.replace(paths.target, paths.backup)
    os.replace(paths.candidate, paths.target)
    _marker(paths, "backed_up")

    assert _recover(constant) == "finalized_commit"
    assert _identity(paths.target) == "new"
    assert (paths.target / "cellZones").read_bytes() == b"zones-new"
    _assert_clean(paths)


def test_recovery_cleans_marker_after_backup_was_deleted(tmp_path: Path) -> None:
    constant = tmp_path / "constant"
    constant.mkdir()
    paths = _paths(constant)
    _tree(paths.target, "new")
    _tree(paths.stage_root, "stage")
    _marker(paths, "committed")

    assert _recover(constant) == "finalized_commit"
    assert _identity(paths.target) == "new"
    _assert_clean(paths)


def test_recovery_preserves_ambiguous_target_backup_candidate(tmp_path: Path) -> None:
    from core.layers.native_hex_inward_transaction import HexBLTransactionError

    constant = tmp_path / "constant"
    constant.mkdir()
    paths = _paths(constant)
    _tree(paths.target, "target")
    _tree(paths.backup, "backup")
    _tree(paths.candidate, "candidate")
    _marker(paths, "prepared")

    with pytest.raises(HexBLTransactionError, match="ambiguous transaction topology"):
        _recover(constant)
    assert _identity(paths.target) == "target"
    assert _identity(paths.backup) == "backup"
    assert _identity(paths.candidate) == "candidate"
    assert paths.marker.exists()


@pytest.mark.parametrize("state", ["staging", "prepared"])
def test_recovery_preserves_target_and_untrusted_backup_before_backup_state(
    tmp_path: Path,
    state: str,
) -> None:
    from core.layers.native_hex_inward_transaction import HexBLTransactionError

    constant = tmp_path / "constant"
    constant.mkdir()
    paths = _paths(constant)
    _tree(paths.target, "target")
    _tree(paths.backup, "untrusted-backup")
    _marker(paths, state)

    with pytest.raises(HexBLTransactionError, match="ambiguous transaction topology"):
        _recover(constant)
    assert _identity(paths.target) == "target"
    assert _identity(paths.backup) == "untrusted-backup"
    assert paths.marker.exists()


def test_recovery_rejects_untrusted_marker_token_without_deletion(tmp_path: Path) -> None:
    from core.layers.native_hex_inward_transaction import HexBLTransactionError

    constant = tmp_path / "constant"
    constant.mkdir()
    target = constant / "polyMesh"
    _tree(target, "old")
    marker = constant / ".autotessell_hexbl_transaction.json"
    marker.write_text(
        json.dumps({"version": 1, "token": "../escape", "state": "staging"}),
        encoding="ascii",
    )

    with pytest.raises(HexBLTransactionError, match="marker token"):
        _recover(constant)
    assert _identity(target) == "old"
    assert marker.exists()


def test_recovery_rejects_symlink_polymesh_even_without_marker(tmp_path: Path) -> None:
    from core.layers.native_hex_inward_transaction import HexBLTransactionError

    constant = tmp_path / "constant"
    real_target = tmp_path / "real-polyMesh"
    constant.mkdir()
    _tree(real_target, "old")
    (constant / "polyMesh").symlink_to(real_target, target_is_directory=True)

    with pytest.raises(HexBLTransactionError, match="polyMesh is a symlink"):
        _recover(constant)
    assert _identity(real_target) == "old"


@pytest.mark.parametrize("slot", ["candidate", "backup"])
def test_begin_refuses_preexisting_slot_without_deletion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    slot: str,
) -> None:
    import core.layers.native_hex_inward_transaction as transaction
    from core.layers.native_hex_inward_lock import acquire_hexbl_transaction_lock

    constant = tmp_path / "constant"
    constant.mkdir()
    paths = _paths(constant)
    _tree(paths.target, "old")
    preexisting = getattr(paths, slot)
    _tree(preexisting, "preexisting")
    monkeypatch.setattr(transaction.uuid, "uuid4", lambda: SimpleNamespace(hex=_TOKEN))

    with acquire_hexbl_transaction_lock(constant) as lock:
        with pytest.raises(transaction.HexBLTransactionError, match=f"pre-existing {slot}"):
            transaction.begin_hexbl_transaction(lock)
    assert _identity(preexisting) == "preexisting"
    assert _identity(paths.target) == "old"
    assert not paths.marker.exists()


def test_marker_file_fsync_failure_is_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.layers.native_hex_inward_transaction as transaction
    from core.layers.native_hex_inward_lock import acquire_hexbl_transaction_lock

    constant = tmp_path / "constant"
    constant.mkdir()
    paths = _paths(constant)
    _tree(paths.target, "old")
    monkeypatch.setattr(transaction.uuid, "uuid4", lambda: SimpleNamespace(hex=_TOKEN))
    monkeypatch.setattr(
        transaction.os,
        "fsync",
        lambda _fd: (_ for _ in ()).throw(OSError("injected fsync failure")),
    )

    with acquire_hexbl_transaction_lock(constant) as lock:
        with pytest.raises(transaction.HexBLTransactionError, match="marker durability failed"):
            transaction.begin_hexbl_transaction(lock)
    assert _identity(paths.target) == "old"


def test_marker_directory_fsync_failure_is_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.layers.native_hex_inward_transaction as transaction
    from core.layers.native_hex_inward_lock import acquire_hexbl_transaction_lock

    constant = tmp_path / "constant"
    constant.mkdir()
    paths = _paths(constant)
    _tree(paths.target, "old")
    monkeypatch.setattr(transaction.uuid, "uuid4", lambda: SimpleNamespace(hex=_TOKEN))

    def fail_directory_fsync(_path: Path) -> None:
        raise transaction.HexBLTransactionError("injected directory fsync failure")

    monkeypatch.setattr(transaction, "_fsync_directory", fail_directory_fsync)
    with acquire_hexbl_transaction_lock(constant) as lock:
        with pytest.raises(transaction.HexBLTransactionError, match="directory fsync failure"):
            transaction.begin_hexbl_transaction(lock)
    assert _identity(paths.target) == "old"


def test_run_recovers_crash_before_read_even_when_inward_flag_off(tmp_path: Path) -> None:
    from core.generator.polymesh_writer import write_generic_polymesh
    from core.generator.tier_layers_post import _run_native_hex_bl

    points = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [1, 1, 0],
            [0, 1, 0],
            [0, 0, 1],
            [1, 0, 1],
            [1, 1, 1],
            [0, 1, 1],
        ],
        dtype=np.float64,
    )
    faces = [
        [
            [0, 3, 2, 1],
            [4, 5, 6, 7],
            [0, 1, 5, 4],
            [1, 2, 6, 5],
            [2, 3, 7, 6],
            [3, 0, 4, 7],
        ]
    ]
    case_dir = tmp_path / "case"
    write_generic_polymesh(points, faces, case_dir, strict=True)
    constant = case_dir / "constant"
    paths = _paths(constant)
    shutil.copytree(paths.target, paths.candidate)
    os.replace(paths.target, paths.backup)
    _marker(paths, "backed_up")

    ok, message, actual = _run_native_hex_bl(
        case_dir,
        num_layers=1,
        growth_ratio=1.2,
        first_thickness=0.05,
        params={},
    )
    assert not ok
    assert actual == 0
    assert message.startswith("native_hex_bl_source_surface_not_preserved:")
    assert (paths.target / "points").is_file()
    _assert_clean(paths)
