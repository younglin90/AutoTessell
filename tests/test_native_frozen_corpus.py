from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.evaluator.native_frozen_corpus import (
    REQUIRED_MESH_FILES,
    build_frozen_corpus_lock,
    copy_locked_case,
    seal_frozen_corpus_lock,
    validate_frozen_corpus_lock,
)


def _make_case(root: Path, name: str) -> Path:
    case = root / name
    (case / "constant" / "polyMesh").mkdir(parents=True)
    for filename in REQUIRED_MESH_FILES:
        (case / "constant" / "polyMesh" / filename).write_text(
            f"{filename}\n", encoding="utf-8"
        )
    (case / "source.certificate.json").write_text('{"authority":true}\n', encoding="utf-8")
    (case / "provenance.ledger.json").write_text('{"bijection":true}\n', encoding="utf-8")
    return case


def test_lock_verifies_copy_only_case_and_rejects_mutation(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _make_case(corpus, "cube")
    lock = build_frozen_corpus_lock(
        corpus,
        {"cube": "cube"},
        required_files={
            "cube": (
                "constant/polyMesh/points",
                "constant/polyMesh/faces",
                "constant/polyMesh/owner",
                "constant/polyMesh/neighbour",
                "constant/polyMesh/boundary",
                "source.certificate.json",
                "provenance.ledger.json",
            )
        },
    )
    lock_path = corpus / "corpus.lock.json"
    seal_frozen_corpus_lock(lock_path, lock)
    assert validate_frozen_corpus_lock(lock, corpus)["accepted"]

    private = copy_locked_case(lock_path, "cube", tmp_path / "private-cube")
    assert private.is_dir()
    assert (private / "constant/polyMesh/points").read_text(encoding="utf-8") == "points\n"

    (corpus / "cube/source.certificate.json").write_text("tampered\n", encoding="utf-8")
    result = validate_frozen_corpus_lock(json.loads(lock_path.read_text()), corpus)
    assert not result["accepted"]
    assert "cube:case_fingerprint_mismatch" in result["reasons"]
    with pytest.raises(ValueError, match="verification_failed"):
        copy_locked_case(lock_path, "cube", tmp_path / "private-after-tamper")


def test_lock_is_write_once_and_missing_required_files_refuse(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _make_case(corpus, "sphere")
    # The builder itself is the admission point for the required ledger.
    # Remove the file only after creating a valid lock in the next assertion.
    with pytest.raises(ValueError, match="required_missing"):
        build_frozen_corpus_lock(
            corpus,
            {"sphere": "sphere"},
            required_files={"sphere": ("source.certificate.json", "missing-authority.json")},
        )
    lock = build_frozen_corpus_lock(
        corpus,
        {"sphere": "sphere"},
        required_files={"sphere": ("source.certificate.json",)},
    )
    assert lock["schema"].endswith("/v1")
    lock_path = corpus / "corpus.lock.json"
    seal_frozen_corpus_lock(lock_path, lock)
    with pytest.raises(FileExistsError):
        seal_frozen_corpus_lock(lock_path, lock)


def test_symlinks_and_unknown_cases_are_not_authoritative(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    case = _make_case(corpus, "naca0012")
    outside = tmp_path / "outside.txt"
    outside.write_text("external\n", encoding="utf-8")
    try:
        os.symlink(outside, case / "external-link")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="symlink"):
        build_frozen_corpus_lock(corpus, {"naca0012": "naca0012"})

    clean = _make_case(corpus, "clean")
    lock = build_frozen_corpus_lock(corpus, {"clean": clean})
    result = validate_frozen_corpus_lock(lock, corpus, case_ids=("unknown",))
    assert not result["accepted"]
    assert result["cases"]["unknown"]["reasons"] == ["case_unknown"]
