from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.evaluator.native_campaign_intake import prepare_native_campaign_corpus
from core.evaluator.native_frozen_corpus import (
    REQUIRED_MESH_FILES,
    copy_locked_case,
    validate_frozen_corpus_lock,
)


def _inputs(root: Path) -> dict[str, Path]:
    source = root / "source.stl"
    source.write_bytes(b"solid frozen\nendsolid frozen\n")
    baseline = root / "baseline"
    mesh = baseline / "constant" / "polyMesh"
    mesh.mkdir(parents=True)
    for filename in REQUIRED_MESH_FILES:
        (mesh / filename).write_text(f"{filename}\n", encoding="utf-8")
    evidence = {}
    for name in ("authority", "semantic", "provenance"):
        path = root / f"{name}.json"
        path.write_text(json.dumps({"name": name, "source_sha256": "locked"}), encoding="utf-8")
        evidence[name] = path
    return {"source": source, "baseline": baseline, **evidence}


def test_campaign_intake_copies_only_explicit_artifacts_and_seals_lock(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path / "inputs") if (tmp_path / "inputs").mkdir() is None else {}
    corpus = tmp_path / "corpus"
    lock = prepare_native_campaign_corpus(
        corpus,
        {
            "cube": {
                "source": inputs["source"],
                "baseline": inputs["baseline"],
                "authority": [inputs["authority"]],
                "semantic": [inputs["semantic"]],
                "provenance": [inputs["provenance"]],
            }
        },
    )
    assert (corpus / "corpus.lock.json").is_file()
    assert validate_frozen_corpus_lock(lock, corpus)["accepted"]
    private = copy_locked_case(corpus / "corpus.lock.json", "cube", tmp_path / "private")
    assert (private / "baseline/constant/polyMesh/points").is_file()
    assert (private / "source/source.stl").read_bytes() == inputs["source"].read_bytes()
    assert (private / "authority/000_authority.json").is_file()


def test_campaign_intake_requires_all_three_evidence_sections_and_never_overwrites(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path / "inputs") if (tmp_path / "inputs").mkdir() is None else {}
    with pytest.raises(ValueError, match="semantic_evidence_missing"):
        prepare_native_campaign_corpus(
            tmp_path / "corpus",
            {
                "sphere": {
                    "source": inputs["source"],
                    "baseline": inputs["baseline"],
                    "authority": [inputs["authority"]],
                    "semantic": [],
                    "provenance": [inputs["provenance"]],
                }
            },
        )
    # Failed intake is not silently reused or overwritten.
    target = tmp_path / "existing"
    target.mkdir()
    with pytest.raises(FileExistsError):
        prepare_native_campaign_corpus(target, {})
