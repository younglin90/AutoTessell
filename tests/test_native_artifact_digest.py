from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("native_artifact_fingerprint")

from core.evaluator.native_artifact_digest import native_artifact_witness, native_tree_fingerprint


def test_adapter_recomputes_three_equal_native_witnesses(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root in (first, second):
        (root / "nested").mkdir(parents=True)
        (root / "nested" / "mesh").write_bytes(b"mesh")
        (root / "meta.json").write_text("{}\n", encoding="ascii")
    witness = native_artifact_witness((first, second, first), ".")
    assert witness["valid"] is True
    assert witness["status"] == "native_recomputed"
    assert witness["algorithm"] == "SHA-256"
    assert witness["implementation"] == "native_artifact_fingerprint"
    assert witness["recomputed"] is True
    assert len(witness["witness_repeats"]) == 3
    assert witness["witness_repeats"] == [witness["tree_sha256"]] * 3
    assert witness["entry_counts"] == [witness["entry_count"]] * 3


def test_adapter_rejects_missing_root(tmp_path: Path) -> None:
    result = native_tree_fingerprint(tmp_path / "missing")
    assert result["valid"] is False
    assert result["status"] == "artifact_root_not_directory"
