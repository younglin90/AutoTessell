"""Process-crash-safe ownership lock for native hex BL transactions."""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path


class HexBLTransactionError(RuntimeError):
    """Transaction state is unsafe or cannot be made durable."""


class HexBLTransactionActive(HexBLTransactionError):
    """Another process owns the case transaction lock."""


class HexBLTransactionUnsupported(HexBLTransactionError):
    """Crash-safe transaction locking is unavailable on this platform."""


_LOCK_PROOF = object()


class HexBLTransactionLock:
    """Process-scoped exclusive lock on the ``constant`` directory inode."""

    __slots__ = ("_constant_dir", "_device", "_fd", "_inode", "_proof", "_released")

    def __init__(
        self,
        constant_dir: Path,
        descriptor: int,
        device: int,
        inode: int,
        proof: object,
    ) -> None:
        if proof is not _LOCK_PROOF:
            raise HexBLTransactionError("transaction lock cannot be constructed directly")
        self._constant_dir = constant_dir
        self._fd = descriptor
        self._device = device
        self._inode = inode
        self._proof = proof
        self._released = False

    @property
    def constant_dir(self) -> Path:
        return self._constant_dir

    def __enter__(self) -> HexBLTransactionLock:
        _require_held_lock(self)
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.release()

    def release(self) -> None:
        if self._released:
            return
        descriptor = self._fd
        self._released = True
        self._fd = -1
        try:
            os.close(descriptor)
        except OSError as exc:
            raise HexBLTransactionError(f"transaction lock close failed:{exc}") from exc


def _load_fcntl():
    if os.name != "posix":
        raise HexBLTransactionUnsupported("fcntl flock unavailable")
    try:
        import fcntl  # noqa: PLC0415
    except ImportError as exc:
        raise HexBLTransactionUnsupported("fcntl flock unavailable") from exc
    return fcntl


def hexbl_transaction_lock_supported() -> bool:
    """Return whether process-crash-safe directory locking is available."""
    try:
        _load_fcntl()
    except HexBLTransactionUnsupported:
        return False
    return True


def acquire_hexbl_transaction_lock(constant_dir: Path) -> HexBLTransactionLock:
    """Acquire non-blocking exclusive ownership of the ``constant`` inode."""
    module = _load_fcntl()
    constant = Path(constant_dir)
    flags = os.O_RDONLY | os.O_DIRECTORY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(constant, flags)
    except OSError as exc:
        raise HexBLTransactionError(f"constant directory lock open failed:{exc}") from exc
    try:
        descriptor_stat = os.fstat(descriptor)
        if not stat.S_ISDIR(descriptor_stat.st_mode):
            raise HexBLTransactionError("constant lock target is not a directory")
        try:
            module.flock(descriptor, module.LOCK_EX | module.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise HexBLTransactionActive("transaction already active") from exc
            raise HexBLTransactionError(f"constant directory lock failed:{exc}") from exc
        resolved = constant.resolve(strict=True)
        path_stat = os.stat(resolved, follow_symlinks=False)
        if path_stat.st_dev != descriptor_stat.st_dev or path_stat.st_ino != descriptor_stat.st_ino:
            raise HexBLTransactionError("constant directory changed during lock acquisition")
        return HexBLTransactionLock(
            resolved,
            descriptor,
            descriptor_stat.st_dev,
            descriptor_stat.st_ino,
            _LOCK_PROOF,
        )
    except Exception:
        os.close(descriptor)
        raise


def _require_held_lock(
    lock: HexBLTransactionLock,
    constant_dir: Path | None = None,
) -> Path:
    if (
        not isinstance(lock, HexBLTransactionLock)
        or lock._proof is not _LOCK_PROOF
        or lock._released
        or lock._fd < 0
    ):
        raise HexBLTransactionError("held transaction lock required")
    try:
        descriptor_stat = os.fstat(lock._fd)
        path_stat = os.stat(lock.constant_dir, follow_symlinks=False)
        if not stat.S_ISDIR(descriptor_stat.st_mode):
            raise HexBLTransactionError("held transaction lock is not a directory")
        if (
            descriptor_stat.st_dev != lock._device
            or descriptor_stat.st_ino != lock._inode
            or path_stat.st_dev != lock._device
            or path_stat.st_ino != lock._inode
        ):
            raise HexBLTransactionError("held transaction directory identity changed")
    except OSError as exc:
        raise HexBLTransactionError(f"held transaction lock invalid:{exc}") from exc
    if constant_dir is not None and Path(constant_dir).resolve() != lock.constant_dir:
        raise HexBLTransactionError("transaction lock covers another constant directory")
    return lock.constant_dir
