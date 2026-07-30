"""Cycle39 process-ownership tests for native hex BL transactions."""

from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path

import numpy as np
import pytest

_AUTHORITATIVE = ("points", "faces", "owner", "neighbour", "boundary")


def _write_hex_case(case_dir: Path) -> None:
    from core.generator.polymesh_writer import write_generic_polymesh

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
    write_generic_polymesh(points, faces, case_dir, strict=True)


def _authoritative_bytes(case_dir: Path) -> dict[str, bytes]:
    poly_mesh = case_dir / "constant" / "polyMesh"
    return {name: (poly_mesh / name).read_bytes() for name in _AUTHORITATIVE}


def _tree(path: Path, label: str) -> None:
    path.mkdir(parents=True)
    (path / "identity").write_text(label, encoding="ascii")


def _child_hold_live_transaction(constant_text: str, status, release) -> None:
    try:
        from core.layers.native_hex_inward_lock import acquire_hexbl_transaction_lock
        from core.layers.native_hex_inward_transaction import (
            begin_hexbl_transaction,
            recover_hexbl_transaction,
        )

        with acquire_hexbl_transaction_lock(Path(constant_text)) as lock:
            begin_hexbl_transaction(lock)
            status.put("locked")
            if not release.wait(20.0):
                raise RuntimeError("parent did not release child")
            recover_hexbl_transaction(lock)
    except BaseException as exc:  # pragma: no cover - surfaced through process status
        status.put(f"error:{type(exc).__name__}:{exc}")


def _child_crash_with_live_transaction(constant_text: str, status) -> None:
    try:
        from core.layers.native_hex_inward_lock import acquire_hexbl_transaction_lock
        from core.layers.native_hex_inward_transaction import begin_hexbl_transaction

        with acquire_hexbl_transaction_lock(Path(constant_text)) as lock:
            begin_hexbl_transaction(lock)
            status.put("crashing")
            status.close()
            status.join_thread()
            os._exit(23)
    except BaseException as exc:  # pragma: no cover - surfaced through process status
        status.put(f"error:{type(exc).__name__}:{exc}")


def test_transaction_mutation_requires_held_lock(tmp_path: Path) -> None:
    import core.layers.native_hex_inward_transaction as transaction
    from core.layers.native_hex_inward_lock import acquire_hexbl_transaction_lock

    constant = tmp_path / "constant"
    constant.mkdir()
    _tree(constant / "polyMesh", "old")

    with pytest.raises(transaction.HexBLTransactionError, match="held transaction lock"):
        transaction.recover_hexbl_transaction(constant)  # type: ignore[arg-type]

    lock = acquire_hexbl_transaction_lock(constant)
    lock.release()
    with pytest.raises(transaction.HexBLTransactionError, match="held transaction lock"):
        transaction.begin_hexbl_transaction(lock)


@pytest.mark.skipif(os.name != "posix", reason="Linux directory flock contract")
@pytest.mark.parametrize("kind", ["symlink", "regular"])
def test_lock_refuses_non_directory_or_symlink_target(
    tmp_path: Path,
    kind: str,
) -> None:
    from core.layers.native_hex_inward_lock import (
        HexBLTransactionError,
        acquire_hexbl_transaction_lock,
    )

    constant = tmp_path / "constant"
    if kind == "symlink":
        real_constant = tmp_path / "real-constant"
        real_constant.mkdir()
        constant.symlink_to(real_constant, target_is_directory=True)
    else:
        constant.write_bytes(b"not-a-directory")

    with pytest.raises(HexBLTransactionError, match="lock open failed"):
        acquire_hexbl_transaction_lock(constant)


@pytest.mark.skipif(os.name != "posix", reason="Linux directory flock contract")
def test_live_child_transaction_blocks_off_path_without_touching_stage(
    tmp_path: Path,
) -> None:
    from core.generator.tier_layers_post import _run_native_hex_bl

    case_dir = tmp_path / "case"
    _write_hex_case(case_dir)
    constant = case_dir / "constant"
    before = _authoritative_bytes(case_dir)
    context = mp.get_context("spawn")
    status = context.Queue()
    release = context.Event()
    process = context.Process(
        target=_child_hold_live_transaction,
        args=(str(constant), status, release),
    )
    process.start()
    try:
        assert status.get(timeout=15.0) == "locked"
        marker = constant / ".autotessell_hexbl_transaction.json"
        stage_paths = list(constant.glob(".autotessell_hexbl_stage_*"))
        assert len(stage_paths) == 1
        marker_before = marker.read_bytes()

        ok, message, actual = _run_native_hex_bl(
            case_dir,
            num_layers=1,
            growth_ratio=1.2,
            first_thickness=0.05,
            params={},
        )
        assert not ok
        assert message == "native_hex_bl_transaction_active"
        assert actual == 0
        assert process.is_alive()
        assert _authoritative_bytes(case_dir) == before
        assert marker.read_bytes() == marker_before
        assert stage_paths[0].is_dir()
    finally:
        release.set()
        process.join(timeout=15.0)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5.0)
    assert process.exitcode == 0
    assert not list(constant.glob(".autotessell_hexbl_*"))


@pytest.mark.skipif(os.name != "posix", reason="Linux directory flock contract")
def test_child_crash_releases_lock_and_next_off_invocation_recovers(
    tmp_path: Path,
) -> None:
    from core.generator.tier_layers_post import _run_native_hex_bl

    case_dir = tmp_path / "case"
    _write_hex_case(case_dir)
    constant = case_dir / "constant"
    before = _authoritative_bytes(case_dir)
    context = mp.get_context("spawn")
    status = context.Queue()
    process = context.Process(
        target=_child_crash_with_live_transaction,
        args=(str(constant), status),
    )
    process.start()
    assert status.get(timeout=15.0) == "crashing"
    process.join(timeout=15.0)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5.0)
    assert process.exitcode == 23
    assert list(constant.glob(".autotessell_hexbl_stage_*"))

    ok, message, actual = _run_native_hex_bl(
        case_dir,
        num_layers=1,
        growth_ratio=1.2,
        first_thickness=0.05,
        params={},
    )
    assert not ok
    assert message.startswith("native_hex_bl_source_surface_not_preserved:")
    assert actual == 0
    assert _authoritative_bytes(case_dir) == before
    assert not list(constant.glob(".autotessell_hexbl_*"))


def test_same_process_stage_exception_recovers_before_lock_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.generator.polymesh_writer as writer
    from core.generator.tier_layers_post import _run_native_hex_bl

    case_dir = tmp_path / "case"
    _write_hex_case(case_dir)
    before = _authoritative_bytes(case_dir)

    def fail_stage_writer(*_args, **_kwargs):
        raise OSError("injected stage writer failure")

    monkeypatch.setattr(writer, "write_generic_polymesh", fail_stage_writer)
    ok, message, actual = _run_native_hex_bl(
        case_dir,
        num_layers=1,
        growth_ratio=1.2,
        first_thickness=0.05,
        params={"post_layers_hex_inward_shell": True},
    )
    assert not ok
    assert message.startswith("native_hex_bl_inward_transaction_failed:")
    assert "recovery=rolled_back_before_backup" in message
    assert actual == 0
    assert _authoritative_bytes(case_dir) == before
    assert not list((case_dir / "constant").glob(".autotessell_hexbl_*"))


def test_unsupported_platform_refuses_only_experimental_inward_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.layers.native_hex_inward_lock as lock_module
    from core.generator.tier_layers_post import _run_native_hex_bl

    case_dir = tmp_path / "case"
    _write_hex_case(case_dir)
    before = _authoritative_bytes(case_dir)
    monkeypatch.setattr(lock_module, "hexbl_transaction_lock_supported", lambda: False)

    inward_ok, inward_message, inward_actual = _run_native_hex_bl(
        case_dir,
        num_layers=1,
        growth_ratio=1.2,
        first_thickness=0.05,
        params={"post_layers_hex_inward_shell": True},
    )
    assert not inward_ok
    assert inward_message == "native_hex_bl_inward_transaction_unsupported_platform"
    assert inward_actual == 0
    assert _authoritative_bytes(case_dir) == before

    outward_ok, outward_message, outward_actual = _run_native_hex_bl(
        case_dir,
        num_layers=1,
        growth_ratio=1.2,
        first_thickness=0.05,
        params={},
    )
    assert not outward_ok
    assert outward_message.startswith("native_hex_bl_source_surface_not_preserved:")
    assert outward_actual == 0
    assert _authoritative_bytes(case_dir) == before
