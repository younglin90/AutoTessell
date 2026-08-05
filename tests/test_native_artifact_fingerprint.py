from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

native_artifact_fingerprint = pytest.importorskip("native_artifact_fingerprint")


def test_tree_fingerprint_is_sorted_root_independent_and_byte_sensitive(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root in (first, second):
        (root / "nested").mkdir(parents=True)
        (root / "nested" / "z.txt").write_bytes(b"z")
        (root / "a.txt").write_bytes(b"a")
        (root / "empty").mkdir()
    left = native_artifact_fingerprint.fingerprint_tree(str(first))
    right = native_artifact_fingerprint.fingerprint_tree(str(second))
    assert left["tree_sha256"] == right["tree_sha256"]
    assert [item["path"] for item in left["entries"]] == ["a.txt", "empty", "nested", "nested/z.txt"]
    assert left["symlinks_forbidden"] and left["special_files_forbidden"]
    (second / "nested" / "z.txt").write_bytes(b"changed")
    assert native_artifact_fingerprint.fingerprint_tree(str(second))["tree_sha256"] != left["tree_sha256"]


def test_tree_fingerprint_matches_canonical_record_digest(tmp_path: Path) -> None:
    (tmp_path / "mesh").write_bytes(b"mesh")
    result = native_artifact_fingerprint.fingerprint_tree(str(tmp_path))
    file_hash = hashlib.sha256(b"mesh").hexdigest()
    canonical = f"mesh\0regular\0{len(b'mesh')}\0{file_hash}\n".encode()
    assert result["tree_sha256"] == hashlib.sha256(canonical).hexdigest()


def test_symlinks_and_special_files_refuse(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"x")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(RuntimeError, match="artifact_symlink_forbidden"):
        native_artifact_fingerprint.fingerprint_tree(str(tmp_path))
    link.unlink()
    fifo = tmp_path / "fifo"
    if not hasattr(os, "mkfifo"):
        pytest.skip("mkfifo unavailable")
    os.mkfifo(fifo)
    with pytest.raises(RuntimeError, match="artifact_special_file_forbidden"):
        native_artifact_fingerprint.fingerprint_tree(str(tmp_path))

def test_native_sha256_bytes_vectors() -> None:
    assert native_artifact_fingerprint.algorithm == "SHA-256"
    assert native_artifact_fingerprint.implementation == "native_artifact_fingerprint"
    assert native_artifact_fingerprint.sha256_bytes(b"") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert native_artifact_fingerprint.sha256_bytes(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
