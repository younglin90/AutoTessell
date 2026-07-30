"""POLY-PRIMAL-CONFORMAL-AUDIT1 focused contracts."""

from __future__ import annotations

import hashlib
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from core.generator.native_poly import dual, tet_to_poly_dual


def _invalid_primal(kind: str) -> tuple[np.ndarray, np.ndarray, str]:
    if kind == "three_owner_face":
        points = np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.2, 0.2, 1.0],
                [0.2, 0.2, -1.0],
                [0.6, 0.2, 1.2],
            ],
            dtype=np.float64,
        )
        tets = np.array(
            [[0, 1, 2, 3], [0, 2, 1, 4], [0, 1, 2, 5]],
            dtype=np.int64,
        )
        reason = (
            "tet connectivity has faces with more than two incident tetrahedra: "
            "(((0, 1, 2), (0, 1, 2)),)"
        )
        return points, tets, reason
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3], [3, 2, 1, 0]], dtype=np.int64)
    reason = (
        "tet connectivity contains duplicate canonical tetrahedra: " "(((0, 1, 2, 3), (0, 1)),)"
    )
    return points, tets, reason


def _valid_classified_bipyramid() -> tuple[
    np.ndarray,
    np.ndarray,
    dict[tuple[int, int, int], tuple[str, str]],
]:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.3, 0.3, 1.0],
            [0.3, 0.3, -1.0],
        ],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3], [0, 2, 1, 4]], dtype=np.int64)
    entities = {
        (0, 1, 3): ("source_high", "wall"),
        (1, 2, 3): ("source_high", "wall"),
        (0, 2, 3): ("source_high", "wall"),
        (0, 1, 4): ("source_low", "patch"),
        (1, 2, 4): ("source_low", "patch"),
        (0, 2, 4): ("source_low", "patch"),
    }
    return points, tets, entities


def _polymesh_hashes(case_dir: Path) -> tuple[str, ...]:
    poly_dir = case_dir / "constant" / "polyMesh"
    return tuple(
        hashlib.sha256((poly_dir / name).read_bytes()).hexdigest()
        for name in ("points", "faces", "owner", "neighbour", "boundary")
    )


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    "kind", ("three_owner_face", "duplicate_tet")
)
def test_nonconformal_primal_is_rejected_before_writing(
    tmp_path: Path,
    kind: str,
) -> None:
    points, tets, reason = _invalid_primal(kind)
    points_before = points.copy()
    tets_before = tets.copy()

    results = []
    for run in range(3):
        case_dir = tmp_path / f"{kind}-{run}"
        results.append(tet_to_poly_dual(points, tets, case_dir))
        assert not case_dir.exists()

    assert all(not result.success for result in results)
    assert {result.message for result in results} == {f"invalid tet dual input: {reason}"}
    assert np.array_equal(points, points_before)
    assert np.array_equal(tets, tets_before)


def test_valid_classified_bipyramid_preserves_exact_output_and_provenance(
    tmp_path: Path,
) -> None:
    points, tets, entities = _valid_classified_bipyramid()
    expected_hashes = (
        "fdab8bddd008ad6fc003427a6a153c4ae4898ddb540dee684cc2be2134a25957",
        "e34a8b7e92d198a658ef33227d71ecbba55dba2c9c8ebd66c9db16fa297c854c",
        "2f3f3f3e97e28db3e2c4ad74ec0b55690bb399ab97098b15d97172ae488873ca",
        "8d80df3c7b13898717eb271b3913d3e577179c3f85e9441418159002f9374873",
        "d29e59ca7dede8b5d1b3ecd5e7858923ab3e5ca459dafcf1d8b2ebd0281d88c0",
    )

    hashes = []
    for run in range(3):
        case_dir = tmp_path / f"valid-{run}"
        result = tet_to_poly_dual(
            points,
            tets,
            case_dir,
            boundary_face_entities=entities,
        )
        assert result.success, result.message
        hashes.append(_polymesh_hashes(case_dir))

    assert hashes == [expected_hashes] * 3


def test_negative_orientation_is_diagnostic_not_a_hard_reject(tmp_path: Path) -> None:
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    tets = np.array([[0, 2, 1, 3]], dtype=np.int64)

    audit = dual._audit_tet_primal_conformity(points, tets)
    result = tet_to_poly_dual(points, tets, tmp_path / "negative_orientation")

    assert audit.conformal
    assert audit.negative_orientation_rows == (0,)
    assert result.success, result.message


def _native_or_skip() -> Any:
    from core.utils.native_extensions import load_native_polymesh

    native = load_native_polymesh()
    if native is None or not hasattr(native, "audit_tet_primal_conformity"):
        pytest.skip("native primal-conformity kernel is not built")
    return native


def test_native_primal_conformity_matches_python_oracle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.utils import native_extensions

    native = _native_or_skip()
    points, tets, _reason = _invalid_primal("three_owner_face")
    duplicate = np.array([[0, 1, 2, 3], [3, 2, 1, 0]], dtype=np.int64)
    tets = np.concatenate((tets, duplicate), axis=0)

    expected = dual._audit_tet_primal_conformity_python(points, tets)
    actual = dual._normalise_tet_primal_conformity_audit(
        native.audit_tet_primal_conformity(points, tets),
        n_points=int(points.shape[0]),
        n_tets=int(tets.shape[0]),
    )
    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: native)

    assert actual == expected
    assert dual._audit_tet_primal_conformity(points, tets) == expected


def test_native_orphan_rows_match_python_oracle() -> None:
    native = _native_or_skip()
    points, tets, _entities = _valid_classified_bipyramid()
    points = np.vstack((points, np.array([[9.0, 9.0, 9.0], [10.0, 10.0, 10.0]], dtype=np.float64)))

    expected = dual._audit_tet_primal_conformity_python(points, tets)
    raw = native.audit_tet_primal_conformity(points, tets)
    raw_orphans = raw[3]
    actual = dual._normalise_tet_primal_conformity_audit(
        raw,
        n_points=int(points.shape[0]),
        n_tets=int(tets.shape[0]),
    )

    assert isinstance(raw_orphans, np.ndarray)
    assert raw_orphans.dtype == np.dtype(np.int64)
    assert raw_orphans.ndim == 1
    assert raw_orphans.flags.c_contiguous
    assert np.array_equal(raw_orphans, np.array([5, 6], dtype=np.int64))
    assert expected.orphan_vertex_rows == (5, 6)
    assert actual == expected
    assert not actual.conformal


def test_native_primal_conformity_strict_abi() -> None:
    native = _native_or_skip()
    points: np.ndarray = np.eye(4, 3, dtype=np.float64)
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)

    with pytest.raises(TypeError):
        native.audit_tet_primal_conformity(points.astype(np.float32), tets)
    with pytest.raises(TypeError):
        native.audit_tet_primal_conformity(points, tets.astype(np.int32))
    with pytest.raises(TypeError):
        native.audit_tet_primal_conformity(points[::-1], tets)


def test_malformed_present_native_audit_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.utils import native_extensions

    points, tets, _entities = _valid_classified_bipyramid()
    malformed = types.SimpleNamespace(
        audit_tet_primal_conformity=lambda *_args: ((), ((((0, 1, 2), (0,))),), (), ())
    )
    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: malformed)

    with pytest.raises(RuntimeError, match="kernel returned an invalid result"):
        dual._audit_tet_primal_conformity(points, tets)

    malformed.audit_tet_primal_conformity = lambda *_args: ((), (), (0.5,), ())
    with pytest.raises(RuntimeError, match="kernel returned an invalid result"):
        dual._audit_tet_primal_conformity(points, tets)


def test_malformed_native_orphan_result_writes_zero_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from core.utils import native_extensions

    points, tets, _entities = _valid_classified_bipyramid()
    malformed = types.SimpleNamespace(
        audit_tet_primal_conformity=lambda *_args: ((), (), (), (1, 0))
    )
    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: malformed)
    case_dir = tmp_path / "malformed-native"

    with pytest.raises(RuntimeError, match="kernel returned an invalid result"):
        tet_to_poly_dual(points, tets, case_dir)
    assert not case_dir.exists()


def test_orphan_primal_vertex_is_rejected_before_writing(tmp_path: Path) -> None:
    points, tets, _entities = _valid_classified_bipyramid()
    points = np.vstack((points, np.array([[9.0, 9.0, 9.0]], dtype=np.float64)))
    points_before = points.copy()
    tets_before = tets.copy()

    results = []
    for run in range(3):
        case_dir = tmp_path / f"orphan-{run}"
        results.append(tet_to_poly_dual(points, tets, case_dir))
        assert not case_dir.exists()

    assert all(not result.success for result in results)
    assert {result.message for result in results} == {
        "invalid tet dual input: tet point array contains vertices with zero "
        "tetrahedron incidence: (5,)"
    }
    assert np.array_equal(points, points_before)
    assert np.array_equal(tets, tets_before)


def test_python_oracle_orphan_rejection_writes_zero_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from core.utils import native_extensions

    points, tets, _entities = _valid_classified_bipyramid()
    points = np.vstack((points, np.array([[9.0, 9.0, 9.0]], dtype=np.float64)))
    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: None)
    case_dir = tmp_path / "python-oracle-orphan"

    result = tet_to_poly_dual(points, tets, case_dir)

    assert not result.success
    assert result.message.endswith("zero tetrahedron incidence: (5,)")
    assert not case_dir.exists()


@pytest.mark.parametrize(
    "orphan_rows",
    ((5, 4), (5, 5), (-1,), (6,), (True,), (5.0,)),
)
def test_malformed_native_orphan_rows_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    orphan_rows: tuple[object, ...],
) -> None:
    from core.utils import native_extensions

    points, tets, _entities = _valid_classified_bipyramid()
    malformed = types.SimpleNamespace(
        audit_tet_primal_conformity=lambda *_args: ((), (), (), orphan_rows)
    )
    monkeypatch.setattr(native_extensions, "load_native_polymesh", lambda: malformed)

    with pytest.raises(RuntimeError, match="kernel returned an invalid result"):
        dual._audit_tet_primal_conformity(points, tets)
