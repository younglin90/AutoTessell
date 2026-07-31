"""Fail-closed regression for residual star-invalid native-poly duals."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

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
    "faces": "0846799c7a230d88394a434ff49bf169ceed0a761f3ed253b097301fc6f6e09d",
    "owner": "6c8335250af566f1affbc17c21e1f8846f7aafdff99f5e5fcc010421d7a8bdf5",
    "neighbour": "408c0ac900fc804194882df5d6432d76745df82ecdc44a499f13e31a20e78bac",
    "boundary": "f637c72d06683b18f208c23b7517968ebc7a31eff2b6a841e8bf4d1d9755c5f8",
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
        # Four arithmetic-center false negatives have feasible kernel witnesses.
        # Cell 6 remains genuinely non-star-shaped and must keep the whole write
        # transaction fail-closed.
        assert result.invalid_star_cells == 1
        # Provenance-defined separator triangulation removes three duplicate
        # invalid wedges while preserving the same rejected non-star cell.
        assert result.invalid_star_subtets == 6
        assert result.message == (
            "star_validity_refused: mode=centroid, invalid_cells=1, "
            "invalid_subtets=6; garimella point candidate rejected: "
            "star_invalid_cells=1, star_invalid_subtets=6"
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


def test_kernel_witness_projection_matches_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from core.utils import native_extensions

    native_result = tet_to_poly_dual(
        _INVALID_CUBE_PRIMAL_POINTS,
        _INVALID_CUBE_PRIMAL_TETS,
        tmp_path / "native",
    )
    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: None)
    python_result = tet_to_poly_dual(
        _INVALID_CUBE_PRIMAL_POINTS,
        _INVALID_CUBE_PRIMAL_TETS,
        tmp_path / "python",
    )

    assert (
        native_result.success,
        native_result.invalid_star_cells,
        native_result.invalid_star_subtets,
        native_result.message,
    ) == (
        python_result.success,
        python_result.invalid_star_cells,
        python_result.invalid_star_subtets,
        python_result.message,
    )
    assert len(native_result.star_examples) == len(python_result.star_examples)
    for native_example, python_example in zip(
        native_result.star_examples,
        python_result.star_examples,
        strict=True,
    ):
        assert native_example.keys() == python_example.keys()
        for key, python_value in python_example.items():
            native_value = native_example[key]
            if isinstance(python_value, float):
                assert native_value == pytest.approx(python_value, abs=1e-15)
            else:
                assert native_value == python_value
    for case_dir in (tmp_path / "native", tmp_path / "python"):
        poly_dir = case_dir / "constant" / "polyMesh"
        assert not any(
            (poly_dir / name).exists()
            for name in ("points", "faces", "owner", "neighbour", "boundary")
        )


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
