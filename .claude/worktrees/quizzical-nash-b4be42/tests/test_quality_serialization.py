"""Round 80 — QualitySnapshot JSON 직렬화 tests."""
from __future__ import annotations

import json

import numpy as np
import pytest


def test_snapshot_to_dict_none() -> None:
    from core.generator.native_tet.quality import snapshot_to_dict

    d = snapshot_to_dict(None)
    assert d == {}


def test_snapshot_to_dict_roundtrip() -> None:
    from core.generator.native_tet.quality import snapshot, snapshot_to_dict

    pts = np.array(
        [[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    s = snapshot(pts, tets)
    d = snapshot_to_dict(s)

    # JSON round-trip.
    raw = json.dumps(d)
    parsed = json.loads(raw)
    assert parsed["n_tets"] == 1
    assert parsed["min_q"] == pytest.approx(s.min_q, abs=1e-5)
    assert parsed["mean_q"] == pytest.approx(s.mean_q, abs=1e-5)
    assert parsed["min_dihedral_deg"] == pytest.approx(s.min_dihedral_deg, abs=1e-2)


def test_snapshot_to_dict_contains_all_fields() -> None:
    from core.generator.native_tet.quality import snapshot, snapshot_to_dict

    pts = np.array(
        [[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    d = snapshot_to_dict(snapshot(pts, tets))
    for key in (
        "n_tets", "min_q", "mean_q", "median_q", "max_aspect",
        "mean_aspect", "min_dihedral_deg", "median_dihedral_deg",
        "vol_weighted_mean_q", "p10_q", "p10_dihedral_deg",
    ):
        assert key in d
