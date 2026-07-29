"""L2 test-only THR S2/Z1 + FOU SSSS shared-face compatibility tests."""

from __future__ import annotations

from core.generator.native_tet.chen_thr_fou_seam_l2 import certify_thr_fou_shared_face_l2

_POINTS = (
    (-1, 0, -1 / 2),  # source-side A
    (1, 0, 1 / 2),  # source-side E
    (0, -1, -1),  # B
    (0, 1, -1),  # C
    (0, 0, 1),  # D
)
_SOURCE = ((-2, -2, 0), (2, -2, 0), (0, 2, 0))


def test_thr_s2z1_and_fou_ssss_share_one_exact_three_triangle_parent_face_partition() -> None:
    # THR uses local (A,B,C,D)=(0,2,3,4); FOU uses local
    # (A,B,C,D)=(1,4,2,3).  They share the physical face (2,3,4).
    result = certify_thr_fou_shared_face_l2(_POINTS, (0, 2, 3, 4), (1, 4, 2, 3), _SOURCE)

    assert result.accepted, result.reason
    assert result.shared_parent_face == (2, 3, 4)
    assert result.shared_face_subfaces == 3
    assert result.shared_face_l1_preserved
    assert result.child_face_incidence_valid
    assert result.cavity_boundary_l1_preserved
    assert result.combined_volume_preserved
    assert result.source_points_unchanged
    assert not result.production_mesh_changed


def test_thr_fou_seam_rejects_an_undocumented_fou_local_order() -> None:
    result = certify_thr_fou_shared_face_l2(_POINTS, (0, 2, 3, 4), (1, 2, 4, 3), _SOURCE)

    assert not result.accepted
    assert result.reason == "parents_do_not_match_documented_thr_s2z1_fou_ssss"
    assert not result.production_mesh_changed


def test_thr_fou_seam_is_value_identical_on_repeat() -> None:
    first = certify_thr_fou_shared_face_l2(_POINTS, (0, 2, 3, 4), (1, 4, 2, 3), _SOURCE)
    second = certify_thr_fou_shared_face_l2(_POINTS, (0, 2, 3, 4), (1, 4, 2, 3), _SOURCE)

    assert first == second
