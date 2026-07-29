"""Minimal L0 contract for source vertices before fallback replacement."""

from __future__ import annotations

import numpy as np

from core.generator.native_tet.mesher import _input_vertices_exactly_present_l0


def test_input_vertex_presence_accepts_a_reordered_exact_copy() -> None:
    source = np.asarray(((0, 0, 0), (1, 0, 0), (0, 1, 0)), dtype=np.float64)
    candidate = np.asarray(((0, 1, 0), (2, 2, 2), (0, 0, 0), (1, 0, 0)), dtype=np.float64)

    accepted, missing = _input_vertices_exactly_present_l0(source, candidate)

    assert accepted
    assert missing == 0


def test_input_vertex_presence_rejects_a_dropped_sharp_corner() -> None:
    source = np.asarray(((0, 0, 0), (1, 0, 0), (0, 1, 0)), dtype=np.float64)
    candidate = np.asarray(((0, 0, 0), (1, 0, 0), (0.0, 1.0 + 1e-12, 0)), dtype=np.float64)

    accepted, missing = _input_vertices_exactly_present_l0(source, candidate)

    assert not accepted
    assert missing == 1
