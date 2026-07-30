"""Exact source-facet provenance contract for native tetrahedral output."""

from __future__ import annotations

import numpy as np
import pytest

from core.generator.native_tet.rescue_gate import audit_source_topology
from core.generator.native_tet.source_facet_provenance import (
    audit_source_facet_provenance_python,
)
from core.generator.native_tet.surface_transaction_gate import (
    apply_metric_topology_transaction,
)


def _pyramid(*, warped_height: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return source/candidate tets separated only by a base diagonal flip."""
    points = np.asarray(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 1.0, warped_height),
            (0.0, 1.0, 0.0),
            (0.5, 0.5, 1.0),
        ),
        dtype=np.float64,
    )
    source_faces = np.asarray(
        (
            (0, 2, 1),
            (0, 3, 2),
            (0, 1, 4),
            (1, 2, 4),
            (2, 3, 4),
            (3, 0, 4),
        ),
        dtype=np.int64,
    )
    source_tets = np.asarray(((0, 1, 2, 4), (0, 2, 3, 4)), dtype=np.int64)
    candidate_tets = np.asarray(((0, 1, 3, 4), (1, 2, 3, 4)), dtype=np.int64)
    return points, source_faces, source_tets, candidate_tets


def test_exact_source_facets_are_certified() -> None:
    points, source_faces, source_tets, _ = _pyramid(warped_height=0.3)

    audit = audit_source_topology(points, source_faces, points.copy(), source_tets)

    assert audit.valid
    assert audit.boundary.valid
    assert audit.components.bijective
    assert audit.components.source_faces_preserved
    assert audit.components.n_source_faces == 6
    assert audit.components.n_source_faces_on_boundary == 6
    assert audit.components.n_missing_source_faces == 0


def test_warped_source_diagonal_replacement_fails_closed() -> None:
    points, source_faces, _, candidate_tets = _pyramid(warped_height=0.3)

    audit = audit_source_topology(points, source_faces, points.copy(), candidate_tets)

    assert audit.boundary.valid
    assert audit.boundary.n_inverted_tets == 0
    assert audit.components.bijective
    assert not audit.components.source_faces_preserved
    assert audit.components.n_source_faces == 6
    assert audit.components.n_source_faces_on_boundary == 4
    assert audit.components.n_missing_source_faces == 2
    assert not audit.valid


def test_metric_transaction_rolls_back_source_diagonal_replacement() -> None:
    points, source_faces, source_tets, candidate_tets = _pyramid(warped_height=0.3)
    pre_points = points.copy()
    pre_tets = source_tets.copy()

    output_points, output_tets, report = apply_metric_topology_transaction(
        points,
        source_faces,
        pre_points,
        pre_tets,
        points.copy(),
        candidate_tets,
    )

    assert not report.accepted
    assert report.reason == "source_facet_provenance_invalid"
    assert report.audit is not None
    assert report.audit.components.n_missing_source_faces == 2
    assert output_points is pre_points
    assert output_tets is pre_tets


def test_planar_retriangulation_is_certified_by_complete_patch_ownership() -> None:
    points, source_faces, _, candidate_tets = _pyramid(warped_height=0.0)

    audit = audit_source_topology(points, source_faces, points.copy(), candidate_tets)

    assert audit.boundary.valid
    assert audit.components.bijective
    assert audit.components.n_missing_source_faces == 2
    assert audit.components.n_owned_candidate_faces == 6
    assert audit.components.n_unowned_candidate_faces == 0
    assert audit.components.n_uncovered_source_patches == 0
    assert audit.components.n_area_mismatch_patches == 0
    assert audit.components.n_feature_boundary_mismatches == 0
    assert audit.components.n_overlap_pairs == 0
    assert audit.valid


def test_nonconvex_patch_shortcut_fails_closed() -> None:
    points = np.asarray(
        (
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (2.0, 1.0, 0.0),
            (1.0, 1.0, 0.0),
            (1.0, 2.0, 0.0),
            (0.0, 2.0, 0.0),
            (0.0, 1.0, 0.0),
        ),
        dtype=np.float64,
    )
    source_faces = np.asarray(((0, 1, 2), (0, 2, 6), (6, 3, 4), (6, 4, 5)), dtype=np.int64)
    shortcut = np.asarray(((0, 2, 4),), dtype=np.int64)

    report = audit_source_facet_provenance_python(points, source_faces, points.copy(), shortcut)

    assert not report["source_faces_preserved"]
    assert report["n_unowned_candidate_faces"] == 1


def test_patch_hole_cover_fails_closed() -> None:
    points = np.asarray(
        (
            (0.0, 0.0, 0.0),
            (3.0, 0.0, 0.0),
            (3.0, 3.0, 0.0),
            (0.0, 3.0, 0.0),
            (1.0, 1.0, 0.0),
            (2.0, 1.0, 0.0),
            (2.0, 2.0, 0.0),
            (1.0, 2.0, 0.0),
        ),
        dtype=np.float64,
    )
    source_faces = np.asarray(
        (
            (0, 1, 5),
            (0, 5, 4),
            (1, 2, 6),
            (1, 6, 5),
            (2, 3, 7),
            (2, 7, 6),
            (3, 0, 4),
            (3, 4, 7),
        ),
        dtype=np.int64,
    )
    hole_cover = np.asarray(((0, 1, 2), (0, 2, 3)), dtype=np.int64)

    report = audit_source_facet_provenance_python(points, source_faces, points.copy(), hole_cover)

    assert not report["source_faces_preserved"]
    assert report["n_unowned_candidate_faces"] == 2


def test_patch_gap_and_overlap_fail_closed() -> None:
    points = np.asarray(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)),
        dtype=np.float64,
    )
    source_faces = np.asarray(((0, 1, 2), (0, 2, 3)), dtype=np.int64)

    gap = audit_source_facet_provenance_python(
        points,
        source_faces,
        points.copy(),
        np.asarray(((0, 1, 2),), dtype=np.int64),
    )
    overlap = audit_source_facet_provenance_python(
        points,
        source_faces,
        points.copy(),
        np.asarray(((0, 1, 2), (0, 2, 3), (0, 1, 3), (1, 2, 3)), dtype=np.int64),
    )

    assert not gap["source_faces_preserved"]
    assert gap["n_area_mismatch_patches"] == 1
    assert not overlap["source_faces_preserved"]
    assert overlap["n_overlap_pairs"] > 0


def test_point_face_and_tet_permutations_preserve_certificate() -> None:
    points, source_faces, _, candidate_tets = _pyramid(warped_height=0.0)
    baseline = audit_source_topology(points, source_faces, points.copy(), candidate_tets)
    point_order = np.asarray((3, 0, 4, 1, 2), dtype=np.int64)
    old_to_new = np.empty(len(point_order), dtype=np.int64)
    old_to_new[point_order] = np.arange(len(point_order), dtype=np.int64)
    permuted_points = points[point_order]
    permuted_faces = old_to_new[source_faces[::-1, ::-1]]
    permuted_tets = old_to_new[candidate_tets[::-1, ::-1]]

    permuted = audit_source_topology(
        permuted_points,
        permuted_faces,
        permuted_points.copy(),
        permuted_tets,
    )

    assert permuted == baseline


@pytest.mark.parametrize("scale", [1.0e-9, 1.0e9])
@pytest.mark.parametrize("warped_height", [0.0, 0.3])
def test_scale_and_translation_preserve_certificate(
    scale: float,
    warped_height: float,
) -> None:
    points, source_faces, _, candidate_tets = _pyramid(warped_height=warped_height)
    baseline = audit_source_topology(points, source_faces, points.copy(), candidate_tets)
    transformed = scale * points + scale * np.asarray((2.0, -3.0, 5.0))

    actual = audit_source_topology(
        transformed,
        source_faces,
        transformed.copy(),
        candidate_tets,
    )

    assert actual == baseline


def test_native_and_python_facet_censuses_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.generator.native_tet import rescue_gate
    from core.utils import native_extensions

    native = native_extensions.load_native_tet_predicates()
    if native is None or not hasattr(native, "audit_source_component_bijection"):
        pytest.skip("native source-component audit is unavailable")

    for warped_height in (0.0, 0.3):
        points, source_faces, source_tets, candidate_tets = _pyramid(warped_height=warped_height)
        for tets in (source_tets, candidate_tets):
            native_result = rescue_gate.audit_source_component_bijection(
                points, source_faces, points.copy(), tets
            )
            monkeypatch.setattr(native_extensions, "load_native_tet_predicates", lambda: None)
            python_result = rescue_gate.audit_source_component_bijection(
                points, source_faces, points.copy(), tets
            )
            assert native_result == python_result
            monkeypatch.undo()
