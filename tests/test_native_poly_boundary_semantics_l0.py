"""L0/L1 audit tests for native-poly classified boundary-cap semantics."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.generator.native_poly import tet_to_poly_dual
from core.generator.native_poly.boundary_semantics_l0 import (
    audit_classified_dual_boundary_l0,
)
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)


def test_l0_exact_source_faces_accept_and_patch_mismatch_rejects() -> None:
    primal = np.asarray(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        dtype=np.float64,
    )
    tets = np.asarray(((0, 1, 2, 3),), dtype=np.int64)
    faces = ((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3))
    entities = {
        (0, 1, 2): {"patch": "source", "type": "wall"},
        (0, 1, 3): {"patch": "source", "type": "wall"},
        (0, 2, 3): {"patch": "source", "type": "wall"},
        (1, 2, 3): {"patch": "source", "type": "wall"},
    }
    entries = ({"name": "source", "type": "wall", "startFace": 0, "nFaces": 4},)

    accepted = audit_classified_dual_boundary_l0(
        primal, tets, primal, faces, (0, 0, 0, 0), (), entries, entities
    )
    assert accepted.accepted, accepted
    assert accepted.max_relative_source_area_error == 0.0

    rejected = audit_classified_dual_boundary_l0(
        primal,
        tets,
        primal,
        faces,
        (0, 0, 0, 0),
        (),
        ({"name": "wrong", "type": "wall", "startFace": 0, "nFaces": 4},),
        entities,
    )
    assert not rejected.accepted
    assert rejected.label_mismatch_face_indices == (0, 1, 2, 3)


def test_l1_classified_bipyramid_caps_preserve_source_partition(tmp_path: Path) -> None:
    primal = np.asarray(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
         (0.3, 0.3, 1.0), (0.3, 0.3, -1.0)),
        dtype=np.float64,
    )
    tets = np.asarray(((0, 1, 2, 3), (0, 2, 1, 4)), dtype=np.int64)
    entities = {
        (0, 1, 3): {"patch": "source_high", "type": "wall"},
        (1, 2, 3): {"patch": "source_high", "type": "wall"},
        (0, 2, 3): {"patch": "source_high", "type": "wall"},
        (0, 1, 4): {"patch": "source_low", "type": "patch"},
        (1, 2, 4): {"patch": "source_low", "type": "patch"},
        (0, 2, 4): {"patch": "source_low", "type": "patch"},
    }
    result = tet_to_poly_dual(primal, tets, tmp_path, boundary_face_entities=entities)
    assert result.success, result.message
    poly_dir = tmp_path / "constant" / "polyMesh"
    audit = audit_classified_dual_boundary_l0(
        primal,
        tets,
        np.asarray(parse_foam_points(poly_dir / "points"), dtype=np.float64),
        parse_foam_faces(poly_dir / "faces"),
        parse_foam_labels(poly_dir / "owner"),
        parse_foam_labels(poly_dir / "neighbour"),
        parse_foam_boundary(poly_dir / "boundary"),
        entities,
    )

    assert audit.accepted, audit
    assert audit.mapped_faces == audit.boundary_face_count
    assert audit.max_relative_source_area_error is not None
    assert audit.max_relative_source_area_error <= 1e-12
