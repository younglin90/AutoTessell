from __future__ import annotations
from pathlib import Path
import numpy as np

from core.layers.native_tet_hex_authority_bound_consumer import (
    evaluate_native_tet_hex_authority_bound_transaction,
)

BUILD = Path("/tmp/autotessell_surface_bl_front_shared_build")

def _receipt(layers: int):
    return (
        {
            "accepted": True,
            "receipt_sealed": True,
            "receipt_digest": "authority-v2",
            "runtime_route": "default_off",
            "direct_lineage": True,
        },
        {
            "accepted": True,
            "receipt_sealed": True,
            "receipt_digest": "optimizer-v2",
            "runtime_route": "default_off",
            "actual_layers": layers,
        },
    )

def _binding(n: int):
    return [
        {
            "source_edge": f"se-{i}",
            "source_face": f"sf-{i}",
            "wall_edge": f"we-{i}",
            "output_face": f"of-{i}",
            "volume_boundary_face": f"vf-{i}",
            "feature": "flat",
            "patch": "wall",
            "physical_group": "fluid",
            "component": "main",
            "provenance": "direct",
        }
        for i in range(n)
    ]

def _tet():
    return np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]), np.array([[0, 1, 2, 3]], dtype=np.int64)

def _hex():
    return (
        np.array([[0.,0.,0.],[1.,0.,0.],[1.,1.,0.],[0.,1.,0.],
                  [0.,0.,1.],[1.,0.,1.],[1.,1.,1.],[0.,1.,1.]]),
        np.array([[0,1,2,3,4,5,6,7]], dtype=np.int64),
    )

def _invoke(monkeypatch, engine, points, cells, layers, binding=None, authority=None, optimizer=None):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(BUILD))
    a, o = _receipt(layers)
    rows = binding if binding is not None and binding and isinstance(binding[0], dict) else (_binding(len(binding or [])) if binding is not None else [])
    return evaluate_native_tet_hex_authority_bound_transaction(
        engine, authority or a, optimizer or o, rows,
        points, cells, points.copy(), cells.copy(), layers, layers,
    )

def test_tet_and_hex_bl0_positive_layers_are_sealed_and_repeatable(monkeypatch):
    for engine, maker, count in (("tet", _tet, 4), ("hex", _hex, 6)):
        points, cells = maker()
        for layers in (0, 1, 3):
            binding = [] if layers == 0 else list(range(count))
            first = _invoke(monkeypatch, engine, points, cells, layers, binding)
            second = _invoke(monkeypatch, engine, points, cells, layers, binding)
            assert first == second
            assert first["accepted"] is True
            assert first["actual_layers"] == layers
            assert first["runtime_route"] == "default_off"
            assert first["publication_eligible"] is False
            assert first["topology"]["duplicate"] == 0

def test_invalid_authority_and_lineage_roll_back_atomically(monkeypatch):
    points, cells = _tet()
    bad = {"accepted": True, "receipt_sealed": True, "receipt_digest": "a", "runtime_route": "production", "direct_lineage": True}
    result = _invoke(monkeypatch, "tet", points, cells, 1, list(range(4)), authority=bad)
    assert result["accepted"] is False
    assert result["actual_layers"] == 0
    assert result["atomic_rollback"] is True
    rows = _binding(4)
    rows[1]["volume_boundary_face"] = rows[0]["volume_boundary_face"]
    result = _invoke(monkeypatch, "tet", points, cells, 1, rows)
    assert result["reason"] == "duplicate_boundary_consumption"

def test_tet_and_hex_bad_geometry_are_rejected(monkeypatch):
    points, cells = _tet()
    inverted = cells[:, [0, 2, 1, 3]]
    result = _invoke(monkeypatch, "tet", points, inverted, 1, list(range(4)))
    assert result["accepted"] is False
    assert result["actual_layers"] == 0
    points, cells = _hex()
    collapsed = points.copy()
    collapsed[7] = collapsed[6]
    result = _invoke(monkeypatch, "hex", collapsed, cells, 1, list(range(6)))
    assert result["accepted"] is False
    assert result["actual_layers"] == 0
