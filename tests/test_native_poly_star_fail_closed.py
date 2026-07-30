"""Fail-closed regression for residual star-invalid native-poly duals."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from core.generator.native_poly.dual import tet_to_poly_dual
from core.utils.polymesh_reader import parse_foam_boundary

_INVALID_CUBE_PRIMAL_POINTS = np.asarray(
    (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 0.0, 1.0),
        (1.0, 1.0, 1.0),
        (0.0, 1.0, 1.0),
        (0.5, 0.5, 0.5),
        (0.9, 0.5, 0.5),
        (0.1, 0.5, 0.5),
        (0.5, 0.9, 0.5),
        (0.5, 0.1, 0.5),
        (0.5, 0.5, 0.9),
        (0.5, 0.5, 0.1),
    ),
    dtype=np.float64,
)
_INVALID_CUBE_PRIMAL_TETS = np.asarray(
    (
        (12, 10, 0, 4),
        (12, 9, 5, 1),
        (14, 12, 0, 1),
        (14, 9, 1, 2),
        (14, 10, 3, 0),
        (14, 12, 10, 0),
        (14, 12, 8, 10),
        (14, 12, 1, 9),
        (14, 12, 9, 8),
        (13, 7, 10, 4),
        (13, 12, 4, 10),
        (13, 12, 10, 8),
        (13, 12, 5, 4),
        (13, 12, 9, 5),
        (13, 12, 8, 9),
        (11, 13, 8, 9),
        (11, 14, 2, 9),
        (11, 14, 9, 8),
        (11, 13, 10, 8),
        (11, 13, 7, 10),
        (11, 14, 3, 2),
        (11, 7, 3, 10),
        (11, 14, 10, 3),
        (11, 14, 8, 10),
        (6, 13, 9, 5),
        (6, 11, 9, 13),
        (6, 11, 13, 7),
        (6, 11, 2, 9),
        (12, 4, 0, 1),
        (12, 5, 4, 1),
        (14, 2, 1, 0),
        (14, 3, 2, 0),
        (7, 10, 4, 0),
        (7, 10, 0, 3),
        (6, 9, 1, 5),
        (6, 9, 2, 1),
        (6, 13, 4, 7),
        (6, 13, 5, 4),
        (6, 11, 7, 3),
        (6, 11, 3, 2),
    ),
    dtype=np.int64,
)

_VALID_BIPYRAMID_POINTS = np.asarray(
    (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.3, 0.3, 1.0),
        (0.3, 0.3, -1.0),
    ),
    dtype=np.float64,
)
_VALID_BIPYRAMID_TETS = np.asarray(((0, 1, 2, 3), (0, 2, 1, 4)), dtype=np.int64)
_VALID_BIPYRAMID_ENTITIES = {
    (0, 1, 3): {"patch": "source_high", "type": "wall"},
    (1, 2, 3): {"patch": "source_high", "type": "wall"},
    (0, 2, 3): {"patch": "source_high", "type": "wall"},
    (0, 1, 4): {"patch": "source_low", "type": "patch"},
    (1, 2, 4): {"patch": "source_low", "type": "patch"},
    (0, 2, 4): {"patch": "source_low", "type": "patch"},
}
_VALID_POLYMESH_HASHES = {
    "points": "fdab8bddd008ad6fc003427a6a153c4ae4898ddb540dee684cc2be2134a25957",
    "faces": "e34a8b7e92d198a658ef33227d71ecbba55dba2c9c8ebd66c9db16fa297c854c",
    "owner": "2f3f3f3e97e28db3e2c4ad74ec0b55690bb399ab97098b15d97172ae488873ca",
    "neighbour": "8d80df3c7b13898717eb271b3913d3e577179c3f85e9441418159002f9374873",
    "boundary": "d29e59ca7dede8b5d1b3ecd5e7858923ab3e5ca459dafcf1d8b2ebd0281d88c0",
}


def _array_digest(points: np.ndarray, tets: np.ndarray) -> str:
    return hashlib.sha256(points.tobytes() + tets.tobytes()).hexdigest()


def test_residual_star_invalid_cube_refuses_deterministically_without_artifacts(
    tmp_path: Path,
) -> None:
    input_digest = _array_digest(_INVALID_CUBE_PRIMAL_POINTS, _INVALID_CUBE_PRIMAL_TETS)
    observations: list[tuple[object, ...]] = []

    for repeat in range(3):
        case_dir = tmp_path / f"invalid_{repeat}"
        result = tet_to_poly_dual(
            _INVALID_CUBE_PRIMAL_POINTS,
            _INVALID_CUBE_PRIMAL_TETS,
            case_dir,
        )

        assert result.success is False
        assert result.n_cells == 15
        assert result.invalid_star_cells == 5
        assert result.invalid_star_subtets == 25
        assert result.message == (
            "star_validity_refused: mode=centroid, invalid_cells=5, "
            "invalid_subtets=25; garimella point candidate rejected: "
            "star_invalid_cells=5, star_invalid_subtets=25"
        )
        poly_dir = case_dir / "constant" / "polyMesh"
        assert not any(
            (poly_dir / name).exists()
            for name in ("points", "faces", "owner", "neighbour", "boundary")
        )
        observations.append(
            (
                result.n_cells,
                result.n_points,
                result.n_faces,
                result.invalid_star_cells,
                result.invalid_star_subtets,
                result.message,
                json.dumps(result.star_examples, sort_keys=True),
            )
        )

    assert observations[1:] == observations[:1] * 2
    assert _array_digest(_INVALID_CUBE_PRIMAL_POINTS, _INVALID_CUBE_PRIMAL_TETS) == input_digest


def test_valid_classified_bipyramid_preserves_bytes_and_patch_provenance(
    tmp_path: Path,
) -> None:
    input_digest = _array_digest(_VALID_BIPYRAMID_POINTS, _VALID_BIPYRAMID_TETS)
    result = tet_to_poly_dual(
        _VALID_BIPYRAMID_POINTS,
        _VALID_BIPYRAMID_TETS,
        tmp_path,
        boundary_face_entities=_VALID_BIPYRAMID_ENTITIES,
    )

    assert result.success is True
    assert result.invalid_star_cells == 0
    assert result.invalid_star_subtets == 0
    poly_dir = tmp_path / "constant" / "polyMesh"
    assert {
        name: hashlib.sha256((poly_dir / name).read_bytes()).hexdigest()
        for name in _VALID_POLYMESH_HASHES
    } == _VALID_POLYMESH_HASHES
    assert [
        (entry["name"], entry["type"]) for entry in parse_foam_boundary(poly_dir / "boundary")
    ] == [("source_high", "wall"), ("source_low", "patch")]
    assert _array_digest(_VALID_BIPYRAMID_POINTS, _VALID_BIPYRAMID_TETS) == input_digest
