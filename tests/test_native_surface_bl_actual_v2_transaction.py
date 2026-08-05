from __future__ import annotations
from pathlib import Path
from core.evaluator.native_surface_bl_front_actual_v2_transaction import seal_authority_bound_surface_transaction

BUILD = Path("/tmp/autotessell_surface_bl_front_shared_build")

def _receipts(layers: int):
    authority = {"accepted": True, "receipt_sealed": True, "receipt_digest": "a", "runtime_route": "default_off", "direct_lineage": True}
    optimizer = {"accepted": True, "receipt_sealed": True, "receipt_digest": "b", "runtime_route": "default_off", "actual_layers": layers}
    return authority, optimizer

def test_typed_transaction_bl0_bl1_bl3_and_route_off(monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    for layers in (0, 1, 3):
        first = seal_authority_bound_surface_transaction(*_receipts(layers), layers)
        second = seal_authority_bound_surface_transaction(*_receipts(layers), layers)
        assert first == second
        assert first["accepted"] is True
        assert first["actual_layers"] == layers
        assert first["runtime_route"] == "default_off"
        assert first["publication_eligible"] is False

def test_typed_transaction_rejects_legacy_route_or_partial_layers(monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    authority, optimizer = _receipts(1)
    optimizer["actual_layers"] = 0
    refused = seal_authority_bound_surface_transaction(authority, optimizer, 1)
    assert refused["accepted"] is False and refused["actual_layers"] == 0
    authority["runtime_route"] = "production"
    refused = seal_authority_bound_surface_transaction(authority, _receipts(1)[1], 1)
    assert refused["reason"] == "route_mutation"
