from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from core.evaluator.native_poly_source_transaction import (
    SCHEMA,
    build_certificate,
    canonical_sha256,
    write_certificate_atomic,
)


def test_certificate_binds_source_config_and_boundary_layer_profile() -> None:
    source = SimpleNamespace(
        original_path="/input/model.stl",
        snapshot_path="/out/_evidence/gate4-source/model.stl",
        sha256="abc123",
        byte_count=1234,
    )
    certificate = build_certificate(
        source,
        source_authority_ledger={"source": "cad", "faces": 12},
        input_config={"target_cells": 100, "quality": "high"},
        boundary_layer_profile={"layers": 2, "first_height": 0.01},
    )

    assert certificate["schema"] == SCHEMA
    assert certificate["immutable"] is True
    assert certificate["raw_source_sha256"] == "abc123"
    assert certificate["source_authority_ledger_status"] == "provided"
    assert certificate["authority_chain_complete"] is True
    assert certificate["boundary_layer_profile"]["layers"] == 2
    body = dict(certificate)
    digest = body.pop("certificate_sha256")
    assert digest == canonical_sha256(body)


def test_certificate_write_is_atomic_and_round_trips(tmp_path: Path) -> None:
    source = SimpleNamespace(
        original_path="/input/model.step",
        snapshot_path="/out/gate4-source/model.step",
        sha256="deadbeef",
        byte_count=8,
    )
    certificate = build_certificate(
        source,
        source_authority_ledger=None,
        input_config={},
        boundary_layer_profile={"layers": 0},
    )
    destination = tmp_path / "_evidence" / "native-poly-source-transaction.json"
    write_certificate_atomic(destination, certificate)

    assert json.loads(destination.read_text(encoding="utf-8")) == certificate
    assert not destination.with_name(f".{destination.name}.tmp").exists()
