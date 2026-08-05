from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from core.layers.poly_bl_transition import canonicalize_staged_poly_bl_candidate
from core.utils.native_extensions import load_native_polymesh

_POINTS = """8
(
(0 0 0)
(1 0 0)
(1 1 0)
(0 1 0)
(0 0 1)
(1 0 1)
(1 1 1)
(0 1 1)
)
"""
_FACES = """6
(
4(0 3 2 1)
4(4 5 6 7)
4(0 1 5 4)
4(1 2 6 5)
4(2 3 7 6)
4(3 0 4 7)
)
"""
_OWNER = """6
(
0
0
0
0
0
0
)
"""
_NEIGHBOUR = """0
(
)
"""


def _write_cube(stage: Path) -> Path:
    poly = stage / "constant" / "polyMesh"
    poly.mkdir(parents=True)
    for name, text in {
        "points": _POINTS,
        "faces": _FACES,
        "owner": _OWNER,
        "neighbour": _NEIGHBOUR,
        "boundary": "1\n(\nwall\n{ type wall; nFaces 6; startFace 0; }\n)\n",
    }.items():
        (poly / name).write_text(text, encoding="utf-8")
    return poly / "faces"


def _positive_bl_sidecars(stage: Path) -> None:
    (stage / "native_bl_state.json").write_text(
        json.dumps({"requested_layers": 1, "actual_layers": 1, "state": "completed"}),
        encoding="utf-8",
    )
    (stage / "native_bl_quality.json").write_text(
        json.dumps(
            {
                "total_thickness": 0.1,
                "n_prism_cells": 1,
                "bad_internal_faces": {"n_bad_faces": 0},
            }
        ),
        encoding="utf-8",
    )
    digest = "a" * 64
    (stage / "native_bl_provenance.json").write_text(
        json.dumps(
            {
                "lineage_complete": True,
                "wall_edge_layer_sha256": digest,
                "source_face_preservation_sha256": "b" * 64,
                "outer_front_sha256": "c" * 64,
                "source_sha256": "d" * 64,
                "candidate_source_sha256": "e" * 64,
            }
        ),
        encoding="utf-8",
    )


def test_cpp_finalizer_reverses_only_internal_cycle(monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "auto_tessell_core/build")
    native = load_native_polymesh()
    points = np.array(
        [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.],
         [0., 0., 1.], [0., 0., -1.]],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0],
        [0, 4, 1], [1, 4, 2], [2, 4, 0],
    ]
    owners = np.array([0, 0, 0, 0, 1, 1, 1], dtype=np.int64)
    neighbours = np.array([1], dtype=np.int64)
    result = native.canonicalize_internal_winding_or_refuse(
        points, faces, owners, neighbours, 1e-12
    )
    assert result["accepted"] is True
    assert list(result["reversed_indices"]) == [0]
    assert list(result["faces"][0]) == [0, 2, 1]
    assert result["boundary_cycles_immutable"] is True
    assert list(result["faces"][1]) == faces[1]


def test_cpp_finalizer_refuses_ambiguous_orientation(monkeypatch):
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", "auto_tessell_core/build")
    native = load_native_polymesh()
    points = np.array(
        [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.],
         [0., 0., 1.], [0., 0., -1.]],
        dtype=np.float64,
    )
    faces = [[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0],
             [0, 4, 1], [1, 4, 2], [2, 4, 0]]
    owners = np.array([0, 0, 0, 0, 1, 1, 1], dtype=np.int64)
    neighbours = np.array([1], dtype=np.int64)
    result = native.canonicalize_internal_winding_or_refuse(
        points, faces, owners, neighbours, 2.0
    )
    assert result["accepted"] is False
    assert result["reason"] == "ambiguous_internal_orientation"


def test_bl0_is_observation_only_and_byte_identity_is_preserved(tmp_path: Path):
    faces_path = _write_cube(tmp_path / "bl0")
    (faces_path.parent.parent.parent / "native_bl_state.json").write_text(
        json.dumps({"requested_layers": 0, "actual_layers": 0, "state": "disabled_identity"}),
        encoding="utf-8",
    )
    before = faces_path.read_bytes()
    result = canonicalize_staged_poly_bl_candidate(faces_path.parents[2])
    assert result["accepted"] is True
    assert result["status"] == "observation_only"
    assert faces_path.read_bytes() == before


def test_bl1_missing_lineage_refuses_without_touching_stage(tmp_path: Path):
    stage = tmp_path / "bl1"
    faces_path = _write_cube(stage)
    _positive_bl_sidecars(stage)
    (stage / "native_bl_provenance.json").unlink()
    before = faces_path.read_bytes()
    result = canonicalize_staged_poly_bl_candidate(stage)
    assert result["accepted"] is False
    assert result["reason"] == "bl_lineage_missing"
    assert faces_path.read_bytes() == before


def test_bl1_staged_cube_passes_readback_and_does_not_invent_reversals(tmp_path: Path):
    stage = tmp_path / "bl1"
    faces_path = _write_cube(stage)
    _positive_bl_sidecars(stage)
    before = faces_path.read_bytes()
    result = canonicalize_staged_poly_bl_candidate(stage)
    assert result["accepted"] is True
    assert result["status"] == "staged_measured"
    assert result["reversed_indices"] == []
    assert result["destination_unchanged"] is True
    assert result["strict_topology"]["valid"] is True
    assert result["quality_witness_sha256"]
    assert faces_path.read_bytes() != b"" and hashlib.sha256(faces_path.read_bytes()).hexdigest()
    assert before != b""
