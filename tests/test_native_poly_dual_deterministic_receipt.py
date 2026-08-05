from __future__ import annotations
from pathlib import Path
import numpy as np

from core.evaluator.native_poly_dual_deterministic_receipt import (
    validate_canonical_dual_hull_receipt,
)

BUILD = Path("auto_tessell_core/build").resolve()
D = "a" * 64

def _call(monkeypatch, mode="exact", ids=(0, 1, 2), plane=(0., 0., 1.), points=None):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    pts = points if points is not None else np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
    return validate_canonical_dual_hull_receipt(
        mode, D, "b" * 64, "c" * 64, pts, list(ids), list(plane), "wall",
    )

def test_exact_receipt_is_canonical_and_repeatable(monkeypatch):
    first = _call(monkeypatch, ids=(0, 1, 2))
    rotated = _call(monkeypatch, ids=(1, 2, 0))
    reversed_cycle = _call(monkeypatch, ids=(0, 2, 1))
    assert first == rotated == reversed_cycle
    assert first["accepted"] is True
    assert first["hull_mode"] == "exact"
    assert first["canonical_vertices"] == [0, 1, 2]
    assert first["runtime_route"] == "default_off"
    assert first["publication_eligible"] is False

def test_joggle_and_ambiguous_geometry_are_refused(monkeypatch):
    joggle = _call(monkeypatch, mode="joggle")
    assert joggle["accepted"] is False
    assert joggle["reason"] == "joggle_not_source_authoritative"
    ambiguous = _call(monkeypatch, plane=(1., 0., 0.))
    assert ambiguous["accepted"] is False
    assert ambiguous["reason"] == "polygon_ambiguous_orientation"
    zero = _call(monkeypatch, points=np.array([[0.,0.,0.],[1.,0.,0.],[2.,0.,0.]]))
    assert zero["reason"] == "polygon_zero_area"

def test_invalid_digest_or_vertex_binding_rolls_back(monkeypatch):
    bad = _call(monkeypatch)
    assert bad["accepted"] is True
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    result = validate_canonical_dual_hull_receipt(
        "exact", "invalid", "b" * 64, "c" * 64,
        [[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]], [0, 1, 2], [0.,0.,1.], "wall",
    )
    assert result["reason"] == "input_digest_incomplete"
    duplicate = _call(monkeypatch, ids=(0, 1, 1))
    assert duplicate["reason"] == "polygon_vertex_duplicate_or_invalid"
