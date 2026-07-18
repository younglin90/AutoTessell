"""FSL1/FSL3 — flat_allsurf_sliver_candidates + guarded 2-3 flip unit tests."""
from __future__ import annotations

import numpy as np

from core.generator.native_tet.validate import (
    apply_flat_sliver_23_flips,
    count_boundary_faces,
    flat_allsurf_sliver_candidates,
)


def test_flat_allsurf_tet_flagged() -> None:
    """4정점 전부 surface, 거의 공면인 tet -> n_cand>=1."""
    eps = 1e-6
    p0 = np.array([0.0, 0.0, 0.0])
    p1 = np.array([1.0, 0.0, 0.0])
    p2 = np.array([0.0, 1.0, 0.0])
    p3 = np.array([0.3, 0.3, eps])
    pts = np.array([p0, p1, p2, p3])
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    r = flat_allsurf_sliver_candidates(pts, tets, n_surface_vertices=4)
    assert r["n_cand"] >= 1


def test_regular_tet_not_flagged() -> None:
    """정사면체(regular tet) -> n_cand=0."""
    p0 = np.array([0.0, 0.0, 0.0])
    p1 = np.array([1.0, 0.0, 0.0])
    p2 = np.array([0.5, np.sqrt(3) / 2, 0.0])
    p3 = np.array([0.5, np.sqrt(3) / 6, np.sqrt(2.0 / 3.0)])
    pts = np.array([p0, p1, p2, p3])
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    r = flat_allsurf_sliver_candidates(pts, tets, n_surface_vertices=4)
    assert r["n_cand"] == 0


def test_three_internal_face_flat_sliver_is_flip_eligible() -> None:
    """flat central tet 의 3면이 internal(3 이웃과 공유), flip 유효 -> flip_eligible."""
    eps = 1e-6
    b = np.array([0.0, 0.0, 0.0])
    c = np.array([1.0, 0.0, 0.0])
    dv = np.array([0.5, 1.0, 0.0])
    cen = (b + c + dv) / 3.0
    a = np.array([cen[0], cen[1], eps])
    e = np.array([cen[0], cen[1], -1.0])
    f = (a + c + dv) / 3.0 + np.array([0.0, 0.0, -1.0])
    g = (a + b + dv) / 3.0 + np.array([0.0, 0.0, -1.0])
    pts = np.array([a, b, c, dv, e, f, g])
    central = [0, 1, 2, 3]
    n1 = [1, 2, 3, 4]
    n2 = [0, 2, 3, 5]
    n3 = [0, 1, 3, 6]
    tets = np.array([central, n1, n2, n3], dtype=np.int64)
    r = flat_allsurf_sliver_candidates(pts, tets, n_surface_vertices=7)
    assert r["n_cand"] == 1
    assert r["n_flip_eligible"] == 1
    assert r["n_core_unflippable"] == 0


def test_two_boundary_face_wedge_is_core_unflippable() -> None:
    """flat central tet, 2 internal face 모두 flip invalid + 2 boundary face -> core_unflippable."""
    eps = 1e-6
    p0 = np.array([0.0, 0.0, 0.0])
    p1 = np.array([1.0, 0.0, 0.0])
    p2 = np.array([0.0, 1.0, 0.0])
    p3 = np.array([0.3, 0.3, eps])
    p4 = np.array([0.3, 0.3, -1.0])
    p5 = np.array([0.1, 0.4, -1.0])
    pts = np.array([p0, p1, p2, p3, p4, p5])
    central = [0, 1, 2, 3]
    n1 = [1, 2, 3, 4]
    n2 = [0, 2, 3, 5]
    tets = np.array([central, n1, n2], dtype=np.int64)
    r = flat_allsurf_sliver_candidates(pts, tets, n_surface_vertices=6)
    assert r["n_cand"] == 1
    assert r["n_flip_eligible"] == 0
    assert r["n_core_unflippable"] == 1


def test_fsl3_synthetic_bipyramid_flips() -> None:
    """flip-eligible bipyramid(공면 flat sliver + 볼록 apex 2개) -> n_flipped=1,
    tet 수 +1, boundary-face 집합(개수) 불변."""
    b = np.array([0.0, 0.0, 0.0])
    c = np.array([1.0, 0.0, 0.0])
    dv = np.array([0.5, 1.0, 0.0])
    cen = (b + c + dv) / 3.0
    a = np.array([cen[0], cen[1], 1e-6])
    e = np.array([cen[0], cen[1], -1.0])
    pts = np.array([b, c, dv, a, e])
    tets = np.array([[0, 1, 2, 3], [0, 1, 2, 4]], dtype=np.int64)
    nbf_pre = count_boundary_faces(tets)
    tets_new, stats = apply_flat_sliver_23_flips(pts, tets, n_surface_vertices=5)
    assert stats["n_eligible"] == 1
    assert stats["n_flipped"] == 1
    assert stats["n_reverted"] == 0
    assert tets_new.shape[0] == tets.shape[0] + 1
    assert count_boundary_faces(tets_new) == nbf_pre


def test_fsl3_concave_union_not_flipped() -> None:
    """오목 union(FSL1 flip_ok=False, test_two_boundary_face_wedge_is_core_unflippable
    와 동일 fixture) -> n_flipped=0, mesh 불변."""
    eps = 1e-6
    p0 = np.array([0.0, 0.0, 0.0])
    p1 = np.array([1.0, 0.0, 0.0])
    p2 = np.array([0.0, 1.0, 0.0])
    p3 = np.array([0.3, 0.3, eps])
    p4 = np.array([0.3, 0.3, -1.0])
    p5 = np.array([0.1, 0.4, -1.0])
    pts = np.array([p0, p1, p2, p3, p4, p5])
    tets = np.array([[0, 1, 2, 3], [1, 2, 3, 4], [0, 2, 3, 5]], dtype=np.int64)
    tets_new, stats = apply_flat_sliver_23_flips(pts, tets, n_surface_vertices=6)
    assert stats["n_eligible"] == 0
    assert stats["n_flipped"] == 0
    assert np.array_equal(tets_new, tets)


def test_fsl3_guard_violation_reverts() -> None:
    """per-op 가드 위반 합성(flip-target 이웃 boundary-face bskew~0 인데 ti 자신은
    전부 internal) -> n_reverted>=1, tets 불변."""
    b = np.array([0.0, 0.0, 0.0])
    c = np.array([1.0, 0.0, 0.0])
    dv = np.array([0.5, np.sqrt(3) / 2, 0.0])
    cen = (b + c + dv) / 3.0
    a = np.array([cen[0], cen[1], 1e-6])
    h = np.sqrt(2.0 / 3.0)
    e = np.array([cen[0], cen[1], -h])  # regular-tet apex -> bskew ~ 0
    f = (a + c + dv) / 3.0 + np.array([0.0, 0.0, -1.0])
    g = (a + b + dv) / 3.0 + np.array([0.0, 0.0, -1.0])
    hh = (a + b + c) / 3.0 + np.array([0.0, 0.0, -1.0])
    pts = np.array([a, b, c, dv, e, f, g, hh])
    central = [0, 1, 2, 3]
    n1 = [1, 2, 3, 4]
    n2 = [0, 2, 3, 5]
    n3 = [0, 1, 3, 6]
    n4 = [0, 1, 2, 7]
    tets = np.array([central, n1, n2, n3, n4], dtype=np.int64)
    tets_new, stats = apply_flat_sliver_23_flips(pts, tets, n_surface_vertices=8)
    assert stats["n_eligible"] == 1
    assert stats["n_reverted"] >= 1
    assert np.array_equal(tets_new, tets)
