"""native_poly dual 변환 + harness 회귀 테스트."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.evaluator.native_checker import NativeMeshChecker
from core.generator.native_poly import dual as dual_module
from core.generator.native_poly import (
    run_native_poly_harness,
    tet_to_poly_dual,
)
from core.generator.native_tet import generate_native_tet
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

_REPO = Path(__file__).resolve().parents[1]
SPHERE_STL = _REPO / "tests" / "benchmarks" / "sphere.stl"


@pytest.fixture
def tmp_case_dir():
    tmp = Path(tempfile.mkdtemp(prefix="poly_dual_"))
    try:
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_tet_to_poly_dual_preserves_classified_multi_patch_caps(
    tmp_case_dir: Path,
) -> None:
    """POLY-DUAL-CLASSIFY1 — source face entities survive the dual write.

    The two-tet bipyramid fixture is intentionally minimal: before
    classification all dual boundary caps are emitted as one ``defaultWall``
    patch. The
    classified path creates the same dual points, refines caps by primal
    boundary triangle, and keeps both source entities as separate patches.
    """
    V = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.3, 0.3, 1.0],
            [0.3, 0.3, -1.0],
        ],
        dtype=np.float64,
    )
    T = np.array([[0, 1, 2, 3], [0, 2, 1, 4]], dtype=np.int64)
    source_entities = {
        (0, 1, 3): {"patch": "source_high", "type": "wall", "entity": "face"},
        (1, 2, 3): {"patch": "source_high", "type": "wall", "entity": "face"},
        (0, 2, 3): {"patch": "source_high", "type": "wall", "entity": "face"},
        (0, 1, 4): {"patch": "source_low", "type": "patch", "entity": "face"},
        (1, 2, 4): {"patch": "source_low", "type": "patch", "entity": "face"},
        (0, 2, 4): {"patch": "source_low", "type": "patch", "entity": "face"},
    }

    unclassified = tet_to_poly_dual(V, T, tmp_case_dir / "unclassified")
    assert unclassified.success, unclassified.message
    unclassified_boundary = parse_foam_boundary(
        tmp_case_dir / "unclassified" / "constant" / "polyMesh" / "boundary"
    )
    assert [entry["name"] for entry in unclassified_boundary] == ["defaultWall"]

    classified_case = tmp_case_dir / "classified"
    classified = tet_to_poly_dual(
        V,
        T,
        classified_case,
        boundary_face_entities=source_entities,
    )
    assert classified.success, classified.message

    poly_dir = classified_case / "constant" / "polyMesh"
    boundary = parse_foam_boundary(poly_dir / "boundary")
    faces = parse_foam_faces(poly_dir / "faces")
    neighbours = parse_foam_labels(poly_dir / "neighbour")
    points = np.asarray(parse_foam_points(poly_dir / "points"), dtype=np.float64)
    baseline_points = np.asarray(
        parse_foam_points(tmp_case_dir / "unclassified" / "constant" / "polyMesh" / "points"),
        dtype=np.float64,
    )

    assert np.array_equal(points, baseline_points)
    assert {entry["name"] for entry in boundary} == {"source_low", "source_high"}
    boundary_text = (poly_dir / "boundary").read_text()
    assert "type            patch;" in boundary_text
    assert "type            wall;" in boundary_text
    checker = NativeMeshChecker().run(classified_case)
    assert checker.mesh_ok
    assert checker.negative_volumes == 0
    assert sum(int(entry["nFaces"]) for entry in boundary) == len(faces) - len(neighbours)
    assert all(
        boundary[idx]["startFace"] + boundary[idx]["nFaces"] == boundary[idx + 1]["startFace"]
        for idx in range(len(boundary) - 1)
    )


def test_tet_to_poly_dual_rejects_partial_boundary_entity_mapping(
    tmp_case_dir: Path,
) -> None:
    """A classified write must not silently relabel an unlabeled source cap."""
    V = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.3, 0.3, 1.0],
            [0.3, 0.3, -1.0],
        ],
        dtype=np.float64,
    )
    T = np.array([[0, 1, 2, 3], [0, 2, 1, 4]], dtype=np.int64)
    partial_entities = {
        (0, 1, 3): ("source_high", "wall"),
        (1, 2, 3): ("source_high", "wall"),
        (0, 2, 3): ("source_high", "wall"),
        (0, 1, 4): ("source_low", "patch"),
        (1, 2, 4): ("source_low", "patch"),
    }

    result = tet_to_poly_dual(
        V,
        T,
        tmp_case_dir / "partial_entities",
        boundary_face_entities=partial_entities,
    )

    assert not result.success
    assert "must cover every extracted boundary triangle" in result.message
    assert not (tmp_case_dir / "partial_entities" / "constant" / "polyMesh").exists()


def test_tet_to_poly_dual_star_validity_convex_and_nonmanifold(
    tmp_case_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POLY-DUAL-POINT1/POLY-STAR-VALID1 — measure convex and non-manifold cases."""
    convex_v = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.3, 0.3, 1.0],
            [0.3, 0.3, -1.0],
        ],
        dtype=np.float64,
    )
    convex_t = np.array([[0, 1, 2, 3], [0, 2, 1, 4]], dtype=np.int64)

    def wall_classifier(_triangle: tuple[int, int, int], _vertices: np.ndarray) -> str:
        return "wall"

    convex = tet_to_poly_dual(
        convex_v,
        convex_t,
        tmp_case_dir / "convex",
        boundary_face_classifier=wall_classifier,
    )
    assert convex.success, convex.message
    assert convex.invalid_star_cells == 0
    assert convex.invalid_star_subtets == 0

    nonmanifold_v = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, 1.0, 0.0],
            [0.5, 0.0, 1.0],
            [0.5, -1.0, 0.0],
            [0.5, 2.0, 2.0],
            [0.5, 3.0, 2.0],
        ],
        dtype=np.float64,
    )
    nonmanifold_t = np.array(
        [[0, 1, 2, 3], [0, 1, 3, 4], [0, 1, 5, 6]],
        dtype=np.int64,
    )

    monkeypatch.setattr(
        dual_module,
        "_compute_tet_dual_points",
        lambda vertices, tets: vertices[tets].mean(axis=1),
    )
    before = tet_to_poly_dual(
        nonmanifold_v,
        nonmanifold_t,
        tmp_case_dir / "nonmanifold_before",
        boundary_face_classifier=wall_classifier,
    )
    monkeypatch.undo()
    after = tet_to_poly_dual(
        nonmanifold_v,
        nonmanifold_t,
        tmp_case_dir / "nonmanifold_after",
        boundary_face_classifier=wall_classifier,
    )
    assert before.success, before.message
    assert after.success, after.message
    # GAP fix (non-manifold-fan dual cell): the primal vertices shared by the
    # disconnected edge-(0,1) fans (tet [0,1,2,3]/[0,1,3,4] vs. the separate
    # tet [0,1,5,6]) now split into one dual cell per fan component instead
    # of being forced into a single, topologically incoherent cell -- both
    # dual-point placements resolve to zero invalid star cells.
    assert (before.invalid_star_cells, before.invalid_star_subtets) == (0, 0)
    assert (after.invalid_star_cells, after.invalid_star_subtets) == (0, 0)
    assert not before.star_examples
    assert not after.star_examples
    # The Garimella circumcenter-biased dual point placement still produces
    # its own (unrelated) invalid candidate for this fixture; the existing
    # centroid fallback absorbs it and the final result is fully valid.
    assert "candidate rejected" in after.message
    assert "star_invalid_cells=6" in after.message
    assert "star_invalid_subtets=30" in after.message


def test_tet_to_poly_dual_from_sphere(tmp_case_dir: Path) -> None:
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    base = tmp_case_dir / "base_tet"
    tet_res = generate_native_tet(
        m.vertices,
        m.faces,
        base,
        seed_density=8,
    )
    assert tet_res.success
    assert tet_res.tets is not None
    assert tet_res.tet_points is not None

    out = tmp_case_dir / "dual"
    res = tet_to_poly_dual(
        tet_res.tet_points,
        tet_res.tets,
        out,
    )
    assert res.success, res.message
    assert res.n_cells > 0
    assert res.n_points > 0
    # polyMesh 파일 생성 확인
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        assert (out / "constant" / "polyMesh" / name).exists()


def test_tet_to_poly_dual_polymesh_valid(tmp_case_dir: Path) -> None:
    """dual 결과가 NativeMeshChecker 로 검증되고 negative_volumes=0."""
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    base = tmp_case_dir / "base_tet"
    tet_res = generate_native_tet(
        m.vertices,
        m.faces,
        base,
        seed_density=10,
    )
    assert tet_res.success and tet_res.tets is not None

    out = tmp_case_dir / "dual"
    res = tet_to_poly_dual(tet_res.tet_points, tet_res.tets, out)
    assert res.success

    chk = NativeMeshChecker().run(out)
    assert chk.negative_volumes == 0, f"negative_volumes = {chk.negative_volumes}"


def test_native_poly_harness_passes_on_sphere(tmp_case_dir: Path) -> None:
    """harness 가 sphere 에서 negative_volumes=0 + cells>0 으로 PASS 한다."""
    if not SPHERE_STL.exists():
        pytest.skip()
    m = read_stl(SPHERE_STL)
    res = run_native_poly_harness(
        m.vertices,
        m.faces,
        tmp_case_dir,
        seed_density=10,
        max_iter=3,
    )
    assert res.success, res.message
    assert res.iterations >= 1
    assert res.n_cells > 0
    assert res.negative_volumes == 0


def test_native_poly_harness_empty_input_fails(tmp_case_dir: Path) -> None:
    V = np.zeros((0, 3))
    F = np.zeros((0, 3), dtype=np.int64)
    res = run_native_poly_harness(V, F, tmp_case_dir, max_iter=1)
    assert res.success is False


def test_tet_to_poly_dual_writes_polymesh_structure(tmp_case_dir: Path) -> None:
    """dual 결과 polyMesh 가 읽을 수 있는 format 인지 확인."""
    if not SPHERE_STL.exists():
        pytest.skip()
    from core.utils.polymesh_reader import (
        parse_foam_boundary,
        parse_foam_faces,
        parse_foam_labels,
        parse_foam_points,
    )

    m = read_stl(SPHERE_STL)
    base = tmp_case_dir / "base_tet"
    tet_res = generate_native_tet(
        m.vertices,
        m.faces,
        base,
        seed_density=8,
    )
    assert tet_res.success and tet_res.tets is not None
    out = tmp_case_dir / "dual"
    tet_to_poly_dual(tet_res.tet_points, tet_res.tets, out)
    poly_dir = out / "constant" / "polyMesh"
    pts = parse_foam_points(poly_dir / "points")
    faces = parse_foam_faces(poly_dir / "faces")
    owner = parse_foam_labels(poly_dir / "owner")
    nbr = parse_foam_labels(poly_dir / "neighbour")
    bnd = parse_foam_boundary(poly_dir / "boundary")
    assert len(pts) > 0
    assert len(faces) > 0
    assert len(owner) == len(faces)
    assert len(nbr) < len(faces)  # boundary faces 는 neighbour 에 없음
    assert len(bnd) >= 1
