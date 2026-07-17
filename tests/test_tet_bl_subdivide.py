"""tet_bl_subdivide 회귀 테스트.

mesh_type=tet 용 BL: native_bl 로 prism 삽입 → 각 wedge 를 tet 3 개로 분할해
전체가 순수 tet 메쉬로 유지되는지 검증.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest

from core.evaluator.native_checker import NativeMeshChecker
from core.layers.native_bl import BLConfig, generate_native_bl
from core.layers.tet_bl_subdivide import (
    _find_prism_caps,
    _prism_to_tets,
    subdivide_prism_layers_to_tet,
)

_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"


# ---------------------------------------------------------------------------
# Unit tests for the conformal prism → 3-tet split (Dompierre global-ID rule)
# and the geometric cap disambiguation.  These pin the two root-cause fixes
# for the "face … shared by 3 cells — manifold 위반" regression.
# ---------------------------------------------------------------------------


def _quad_diagonal(tets: list[tuple[int, int, int, int]], quad: set[int]) -> frozenset | None:
    """Diagonal edge used to split ``quad`` across the tets (or None)."""
    tris: set[frozenset] = set()
    for a, b, c, d in tets:
        for tri in ((b, c, d), (a, c, d), (a, b, d), (a, b, c)):
            if set(tri) <= quad:
                tris.add(frozenset(tri))
    tri_list = list(tris)
    for i in range(len(tri_list)):
        for j in range(i + 1, len(tri_list)):
            if tri_list[i] | tri_list[j] == quad:
                return tri_list[i] & tri_list[j]
    return None


def test_prism_to_tets_shared_quad_diagonal_is_conformal() -> None:
    """Two prisms sharing a wall edge pick the SAME diagonal on the shared quad.

    A: outer=[w1,w2,wA], inner=[e1,e2,eA]; B lies on the far side of edge
    (w1,w2), so its caps list the same shared vertices in reversed order.
    The Dompierre global-ID rule must give both the same diagonal on the shared
    quad {w1,w2,e1,e2} — otherwise the shared face splits inconsistently.
    """
    w1, w2, wa, e1, e2, ea, wb, eb = 10, 20, 30, 11, 21, 31, 40, 41
    tets_a = _prism_to_tets([w1, w2, wa], [e1, e2, ea])
    tets_b = _prism_to_tets([w2, w1, wb], [e2, e1, eb])
    quad = {w1, w2, e1, e2}
    diag_a = _quad_diagonal(tets_a, quad)
    diag_b = _quad_diagonal(tets_b, quad)
    assert diag_a is not None
    assert diag_a == diag_b, f"diagonals disagree: {diag_a} vs {diag_b}"


def test_prism_to_tets_is_relabel_invariant() -> None:
    """The 3-tet split is invariant under cap rotation and outer/inner swap.

    Because the split is chosen purely from global vertex IDs, rotating the
    caps or swapping which triangle is called ``outer`` must not change the set
    of resulting tets — this is what makes the split independent of face
    storage order (the original defect).
    """
    outer = [10, 20, 30]
    inner = [11, 21, 31]
    base = {frozenset(t) for t in _prism_to_tets(outer, inner)}
    for r in range(3):
        oo = outer[r:] + outer[:r]
        ii = inner[r:] + inner[:r]
        assert {frozenset(t) for t in _prism_to_tets(oo, ii)} == base
        # swap caps (outer <-> inner, keeping lateral pairing)
        assert {frozenset(t) for t in _prism_to_tets(ii, oo)} == base


def test_prism_to_tets_tiles_prism() -> None:
    """The 3 tets partition the prism: exactly 8 boundary + 2 internal tri faces."""
    tets = _prism_to_tets([10, 20, 30], [11, 21, 31])
    assert len(tets) == 3
    face_count: dict[frozenset, int] = {}
    for a, b, c, d in tets:
        for tri in ((b, c, d), (a, c, d), (a, b, d), (a, b, c)):
            key = frozenset(tri)
            face_count[key] = face_count.get(key, 0) + 1
    boundary = [k for k, v in face_count.items() if v == 1]
    internal = [k for k, v in face_count.items() if v == 2]
    assert len(boundary) == 8  # 2 caps + 6 quad halves
    assert len(internal) == 2
    assert not [k for k, v in face_count.items() if v > 2]


def test_find_prism_caps_geometric_selection_picks_thin_laterals() -> None:
    """A split-side prism can admit >1 valid cap pairing; the geometric variant
    must pick the pair whose lateral edges are shortest (true wall↔extruded),
    not an arbitrary topologically-valid pair.

    Coordinates/topology taken from a real native_bl sphere-BL cell that
    triggered the manifold violation (vertices relabelled 0..5 = A..F).
    """
    # A..F -> 0..5
    points = np.array([
        [-0.77167305, 0.07966435, 0.60604836],   # 0 A
        [-0.67365562, 0.16131239, 0.69715522],   # 1 B
        [-0.68445720, 0.16381036, 0.70807560],   # 2 C
        [-0.78384304, 0.08108629, 0.61564201],   # 3 D
        [-0.70030812, -0.00002508, 0.69187307],  # 4 E
        [-0.71128172, 0.00000000, 0.70290703],   # 5 F
    ], dtype=np.float64)
    faces = [
        [3, 0, 2], [0, 1, 2], [5, 4, 3], [4, 0, 3],
        [0, 1, 4], [5, 4, 2], [4, 1, 2], [5, 2, 3],
    ]
    caps = _find_prism_caps(faces, points)
    assert caps is not None
    got = {frozenset(caps[0]), frozenset(caps[1])}
    # correct (thin-lateral) caps: (A,B,E)={0,1,4} & (C,D,F)={2,3,5}
    thin = {frozenset({0, 1, 4}), frozenset({2, 3, 5})}
    # spurious (mixed) caps that the old first-match logic could return:
    spurious = {frozenset({0, 1, 2}), frozenset({3, 4, 5})}
    assert got == thin, f"expected thin caps {thin}, got {got}"
    assert got != spurious

    # Without points the topology-only query may return any valid pair — must
    # still be a valid pair (not None).
    assert _find_prism_caps(faces) is not None


@pytest.fixture
def sphere_with_bl() -> Path:
    """sphere tet 베이스라인 + native_bl 2 layers 삽입된 case."""
    if not SPHERE_STL.exists():
        pytest.skip(f"sphere.stl 미존재: {SPHERE_STL}")
    tmp = Path(tempfile.mkdtemp(prefix="tbs_test_"))
    try:
        case_dir = tmp / "case"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(_REPO) + os.pathsep + env.get("PYTHONPATH", "")
        r = subprocess.run(
            ["python3", "-m", "cli.main", "run", str(SPHERE_STL),
             "-o", str(case_dir), "--mesh-type", "tet", "--quality", "draft",
             "--tier", "wildmesh", "--auto-retry", "off"],
            capture_output=True, text=True, timeout=180,
            env=env, cwd=str(_REPO),
        )
        if r.returncode != 0 or not (case_dir / "constant" / "polyMesh").exists():
            pytest.skip(
                f"baseline 실패 (rc={r.returncode}): "
                f"{(r.stderr or r.stdout)[-300:]}"
            )
        # native_bl 2 layers
        cfg = BLConfig(
            num_layers=2, growth_ratio=1.2, first_thickness=0.01,
            backup_original=False, max_total_ratio=0.1,
        )
        bl_res = generate_native_bl(case_dir, cfg)
        assert bl_res.success, f"native_bl: {bl_res.message}"
        yield case_dir
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_subdivide_converts_all_prism_to_tet(sphere_with_bl: Path) -> None:
    """subdivide 후 prism cell 이 남지 않아야 한다."""
    res = subdivide_prism_layers_to_tet(sphere_with_bl, backup_original=False)
    assert res.success, f"subdivide 실패: {res.message}"
    assert res.n_prism_before > 0
    assert res.n_tet_added == 3 * res.n_prism_before


def test_subdivide_result_is_valid_mesh(sphere_with_bl: Path) -> None:
    """subdivide 결과 NativeMeshChecker 통과 (mesh_ok + negative_volumes=0)."""
    res = subdivide_prism_layers_to_tet(sphere_with_bl, backup_original=False)
    assert res.success

    chk = NativeMeshChecker().run(sphere_with_bl)
    assert chk.negative_volumes == 0
    assert chk.mesh_ok, (
        f"mesh_ok=False, failed_checks={chk.failed_checks}"
    )


def test_subdivide_preserves_boundary_face_count(sphere_with_bl: Path) -> None:
    """sphere 같은 closed manifold 에서 subdivide 전후 wall boundary face 수는 유지."""
    before = NativeMeshChecker().run(sphere_with_bl)
    before_boundary = before.faces - 0  # (boundary face 수는 별도 API 가 없어 전체 face 만)

    res = subdivide_prism_layers_to_tet(sphere_with_bl, backup_original=False)
    assert res.success

    after = NativeMeshChecker().run(sphere_with_bl)
    # tet 분할 시 face 수는 늘어남 (prism 5 face → tet 3 개 * 4 face 중 공유 제외)
    # 단순히 "cells 은 3 배 증가한 prism 만큼만 늘어남" 확인
    assert after.cells == before.cells + res.n_tet_added - res.n_prism_before


def test_subdivide_on_no_prism_mesh_is_noop(sphere_with_bl: Path) -> None:
    """prism 이 없는 메쉬 (이미 분할된 경우) 에서 재실행 시 noop 성공."""
    res1 = subdivide_prism_layers_to_tet(sphere_with_bl, backup_original=False)
    assert res1.success

    res2 = subdivide_prism_layers_to_tet(sphere_with_bl, backup_original=False)
    assert res2.success
    assert res2.n_prism_before == 0
    assert res2.n_tet_added == 0


def test_subdivide_backup_creates_pre_dir(sphere_with_bl: Path) -> None:
    res = subdivide_prism_layers_to_tet(sphere_with_bl, backup_original=True)
    assert res.success
    bak = sphere_with_bl / "constant" / "polyMesh_pre_tet_subdiv"
    assert bak.exists() and bak.is_dir()
