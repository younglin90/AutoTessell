"""Parity checks for the optional native_metrics C++ kernels."""

from __future__ import annotations

import numpy as np
import pytest

from core.evaluator import native_checker as nc
from core.evaluator.native_checker import NativeMeshChecker


def _native_metrics_or_skip():
    module = nc._load_native_metrics()
    if module is None:
        pytest.skip("native_metrics extension is not built")
    return module


class _NoIndexPoints(np.ndarray):
    def __getitem__(self, key):
        raise AssertionError(f"points indexed on no-work face path: {key!r}")


@pytest.mark.parametrize(
    ("faces", "expected"),
    [
        ([[0, 1, 2], [1, 3, 2]], (0.0, 0.0)),
        ([[0, 1]], (0.0, 1.0)),
    ],
    ids=["triangle-only", "short-invalid-face"],
)
def test_face_concavity_warpage_no_work_faces_do_not_index_points(
    faces: list[list[int]], expected: tuple[float, float]
) -> None:
    points = np.zeros((4, 3), dtype=np.float64).view(_NoIndexPoints)
    n_faces = len(faces)

    result = NativeMeshChecker._compute_face_concavity_warpage(
        points,
        faces,
        np.zeros((n_faces, 3), dtype=np.float64),
        np.zeros(n_faces, dtype=np.float64),
        np.zeros((n_faces, 3), dtype=np.float64),
    )

    assert result == expected


@pytest.mark.parametrize(
    ("points", "expected"),
    [
        (
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
            (0.0, 0.0),
        ),
        (
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.35], [0.0, 1.0, 0.0]],
            (0.0, 0.013735455038311195),
        ),
        (
            [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [1.0, 0.5, 0.0], [2.0, 2.0, 0.0], [0.0, 2.0, 0.0]],
            (180.0, 0.11764705882352955),
        ),
    ],
    ids=["planar-quad", "warped-quad", "concave-polygon"],
)
def test_face_concavity_warpage_polygon_behavior(
    points: list[list[float]], expected: tuple[float, float]
) -> None:
    point_array = np.asarray(points, dtype=np.float64)
    faces = [list(range(len(points)))]
    face_centres = NativeMeshChecker._compute_face_centres(point_array, faces)
    face_normals, face_areas = NativeMeshChecker._compute_face_normals_areas(point_array, faces)
    actual = NativeMeshChecker._compute_face_concavity_warpage(
        point_array, faces, face_normals, face_areas, face_centres
    )

    assert actual == pytest.approx(expected, abs=1e-15)


def _python_aspect_ratios(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    n_cells: int,
) -> tuple[np.ndarray, np.ndarray]:
    old_module = nc._NATIVE_METRICS
    old_attempted = nc._NATIVE_METRICS_IMPORT_ATTEMPTED
    try:
        nc._NATIVE_METRICS = None
        nc._NATIVE_METRICS_IMPORT_ATTEMPTED = True
        return NativeMeshChecker._per_cell_aspect_ratios(points, faces, owner, n_cells, 0)
    finally:
        nc._NATIVE_METRICS = old_module
        nc._NATIVE_METRICS_IMPORT_ATTEMPTED = old_attempted


def _native_aspect_ratios(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    n_cells: int,
) -> tuple[np.ndarray, np.ndarray]:
    module = _native_metrics_or_skip()
    cell_ids, aspect_ratios = module.compute_per_cell_aspect_ratios(
        points, faces, owner, n_cells
    )
    return (
        np.asarray(cell_ids, dtype=np.int64),
        np.asarray(aspect_ratios, dtype=np.float64),
    )


def _native_combined_cell_metrics(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_cells: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    module = _native_metrics_or_skip()
    centres, cell_ids, aspect_ratios = module.compute_cell_centres_and_aspect_ratios(
        points, faces, owner, neighbour, n_cells
    )
    return (
        np.asarray(centres, dtype=np.float64),
        np.asarray(cell_ids, dtype=np.int64),
        np.asarray(aspect_ratios, dtype=np.float64),
    )


def test_native_metrics_face_geometry_matches_python() -> None:
    _native_metrics_or_skip()
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],
        [0, 3, 1],
        [0, 2, 3],
        [1, 4, 2],
        [1, 3, 4, 2],
    ]

    cpp = NativeMeshChecker._compute_face_geometry(points, faces)
    assert cpp is not None
    centres_cpp, normals_cpp, areas_cpp = cpp

    centres_py = NativeMeshChecker._compute_face_centres(points, faces)
    normals_py, areas_py = NativeMeshChecker._compute_face_normals_areas(points, faces)

    np.testing.assert_allclose(centres_cpp, centres_py, rtol=0.0, atol=1e-15)
    np.testing.assert_allclose(normals_cpp, normals_py, rtol=0.0, atol=1e-15)
    np.testing.assert_allclose(areas_cpp, areas_py, rtol=0.0, atol=1e-15)


def test_native_metrics_cell_centres_match_python_fallback() -> None:
    _native_metrics_or_skip()
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],
        [0, 3, 1],
        [0, 2, 3],
        [1, 3, 4, 2],
    ]
    owner = np.array([0, 0, 0, 1], dtype=np.int64)
    neighbour = np.array([1], dtype=np.int64)
    n_cells = 2

    centres_cpp = NativeMeshChecker._compute_cell_centres_from_vertices(
        points, faces, owner, n_cells, neighbour
    )

    old_module = nc._NATIVE_METRICS
    old_attempted = nc._NATIVE_METRICS_IMPORT_ATTEMPTED
    try:
        nc._NATIVE_METRICS = None
        nc._NATIVE_METRICS_IMPORT_ATTEMPTED = True
        centres_py = NativeMeshChecker._compute_cell_centres_from_vertices(
            points, faces, owner, n_cells, neighbour
        )
    finally:
        nc._NATIVE_METRICS = old_module
        nc._NATIVE_METRICS_IMPORT_ATTEMPTED = old_attempted

    np.testing.assert_allclose(centres_cpp, centres_py, rtol=0.0, atol=1e-15)


def test_native_metrics_combined_cell_metrics_match_standalone_kernels() -> None:
    module = _native_metrics_or_skip()
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [0.0, 2.0, 0.0],
            [0.0, 0.0, 2.0],
            [0.0, 0.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 1],
        [2, 3, 2],
        [0, 4, 4],
    ]
    owner = np.array([0, 1, 2], dtype=np.int64)
    neighbour = np.array([1], dtype=np.int64)
    n_cells = 3

    centres, cell_ids, aspect_ratios = _native_combined_cell_metrics(
        points, faces, owner, neighbour, n_cells
    )
    standalone_centres = np.asarray(
        module.compute_cell_centres_from_vertices(points, faces, owner, neighbour, n_cells),
        dtype=np.float64,
    )
    standalone_ids, standalone_ratios = module.compute_per_cell_aspect_ratios(
        points, faces, owner, n_cells
    )

    np.testing.assert_allclose(centres, standalone_centres, rtol=0.0, atol=1e-15)
    np.testing.assert_array_equal(cell_ids, np.asarray(standalone_ids, dtype=np.int64))
    np.testing.assert_allclose(
        aspect_ratios,
        np.asarray(standalone_ratios, dtype=np.float64),
        rtol=0.0,
        atol=1e-15,
    )
    np.testing.assert_allclose(centres[1], points[[0, 1, 2, 3]].mean(axis=0), rtol=0.0, atol=1e-15)
    np.testing.assert_allclose(aspect_ratios, np.array([1.0, 1.0]))


def test_native_metrics_quality_metrics_match_python_fallback() -> None:
    _native_metrics_or_skip()
    checker = NativeMeshChecker()
    face_centres = np.array(
        [
            [0.5, 0.0, 0.0],
            [0.5, 1.0, 0.0],
            [0.5, 0.5, 0.2],
            [0.0, 0.5, 0.0],
        ],
        dtype=np.float64,
    )
    face_normals = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.8, 0.2, 0.0],
            [0.0, 0.0, 1.0],
            [-1.0, 0.0, 0.0],
        ],
        dtype=np.float64,
    )
    cell_centres = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.1, 0.0],
            [0.9, 1.0, 0.1],
        ],
        dtype=np.float64,
    )
    owner = np.array([0, 1, 0, 0], dtype=np.int64)
    neighbour = np.array([1, 2, 2], dtype=np.int64)
    n_internal = 3

    non_ortho_cpp = checker._compute_non_orthogonality(
        face_centres, face_normals, cell_centres, owner, neighbour, n_internal
    )
    skew_cpp = checker._compute_skewness(
        face_centres, cell_centres, owner, neighbour, n_internal
    )
    boundary_skew_cpp = checker._compute_boundary_skewness(
        face_centres, face_normals, cell_centres, owner, n_internal
    )

    old_module = nc._NATIVE_METRICS
    old_attempted = nc._NATIVE_METRICS_IMPORT_ATTEMPTED
    try:
        nc._NATIVE_METRICS = None
        nc._NATIVE_METRICS_IMPORT_ATTEMPTED = True
        non_ortho_py = checker._compute_non_orthogonality(
            face_centres, face_normals, cell_centres, owner, neighbour, n_internal
        )
        skew_py = checker._compute_skewness(
            face_centres, cell_centres, owner, neighbour, n_internal
        )
        boundary_skew_py = checker._compute_boundary_skewness(
            face_centres, face_normals, cell_centres, owner, n_internal
        )
    finally:
        nc._NATIVE_METRICS = old_module
        nc._NATIVE_METRICS_IMPORT_ATTEMPTED = old_attempted

    np.testing.assert_allclose(non_ortho_cpp, non_ortho_py, rtol=0.0, atol=1e-12)
    assert skew_cpp == pytest.approx(skew_py, abs=1e-15)
    assert boundary_skew_cpp == pytest.approx(boundary_skew_py, abs=1e-15)


def test_native_metrics_cell_volumes_match_python_fallback() -> None:
    _native_metrics_or_skip()
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 1.0],
        ],
        dtype=np.float64,
    )
    faces = [
        [0, 1, 2],
        [0, 3, 1],
        [0, 2, 3],
        [1, 3, 4, 2],
    ]
    owner = np.array([0, 0, 0, 1], dtype=np.int64)
    neighbour = np.array([1], dtype=np.int64)
    n_cells = 2
    n_internal = 1

    face_geometry = NativeMeshChecker._compute_face_geometry(points, faces)
    assert face_geometry is not None
    face_centres, face_normals, face_areas = face_geometry
    cell_centres = NativeMeshChecker._compute_cell_centres_from_vertices(
        points, faces, owner, n_cells, neighbour
    )

    volumes_cpp, negative_cpp = NativeMeshChecker._compute_cell_volumes(
        points,
        faces,
        face_normals,
        face_areas,
        owner,
        neighbour,
        n_cells,
        n_internal,
        cell_centres,
        face_centres,
    )

    old_module = nc._NATIVE_METRICS
    old_attempted = nc._NATIVE_METRICS_IMPORT_ATTEMPTED
    try:
        nc._NATIVE_METRICS = None
        nc._NATIVE_METRICS_IMPORT_ATTEMPTED = True
        volumes_py, negative_py = NativeMeshChecker._compute_cell_volumes(
            points,
            faces,
            face_normals,
            face_areas,
            owner,
            neighbour,
            n_cells,
            n_internal,
            cell_centres,
            face_centres,
        )
    finally:
        nc._NATIVE_METRICS = old_module
        nc._NATIVE_METRICS_IMPORT_ATTEMPTED = old_attempted

    np.testing.assert_allclose(volumes_cpp, volumes_py, rtol=0.0, atol=1e-15)
    assert negative_cpp == negative_py


def test_native_metrics_aspect_ratios_match_duplicate_and_degenerate_vertices() -> None:
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [3.0, 0.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = [[0, 1, 2, 2, 3, 0], [0, 1, 1]]
    owner = np.array([0, 1], dtype=np.int64)

    cells_cpp, ratios_cpp = _native_aspect_ratios(points, faces, owner, 2)
    cells_py, ratios_py = _python_aspect_ratios(points, faces, owner, 2)

    np.testing.assert_array_equal(cells_cpp, cells_py)
    np.testing.assert_allclose(ratios_cpp, ratios_py, rtol=0.0, atol=1e-15)
    np.testing.assert_array_equal(cells_cpp, np.array([0], dtype=np.int64))
    np.testing.assert_allclose(ratios_cpp, np.array([3.0]), rtol=0.0, atol=1e-15)


def test_native_metrics_aspect_ratios_zero_cells() -> None:
    points = np.empty((0, 3), dtype=np.float64)
    owner = np.empty(0, dtype=np.int64)
    cells, ratios = _native_aspect_ratios(points, [], owner, 0)
    cells_py, ratios_py = _python_aspect_ratios(
        points, [], owner, 0
    )

    np.testing.assert_array_equal(cells, cells_py)
    np.testing.assert_array_equal(ratios, ratios_py)
    assert cells.dtype == np.int64
    assert ratios.dtype == np.float64
    assert cells.size == 0
    assert ratios.size == 0


def test_native_metrics_aspect_ratios_preserve_sampling_rule() -> None:
    points = np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]], dtype=np.float64)
    faces = [[0, 1], [0, 1], [0, 1], [0, 1]]
    owner = np.array([0, 1, 49_998, 49_999], dtype=np.int64)
    n_cells = 50_001

    cells_cpp, ratios_cpp = _native_aspect_ratios(points, faces, owner, n_cells)
    cells_py, ratios_py = _python_aspect_ratios(points, faces, owner, n_cells)

    np.testing.assert_array_equal(cells_cpp, cells_py)
    np.testing.assert_allclose(ratios_cpp, ratios_py, rtol=0.0, atol=1e-15)
    np.testing.assert_array_equal(cells_cpp, np.array([0, 49_998], dtype=np.int64))

    _, combined_cells, combined_ratios = _native_combined_cell_metrics(
        points, faces, owner, np.empty(0, dtype=np.int64), n_cells
    )
    np.testing.assert_array_equal(combined_cells, cells_cpp)
    np.testing.assert_allclose(combined_ratios, ratios_cpp, rtol=0.0, atol=1e-15)


def test_native_metrics_aspect_ratios_fall_back_on_binding_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [4.0, 0.0, 0.0]],
        dtype=np.float64,
    )
    faces = [[0, 1, 2]]
    owner = np.array([0], dtype=np.int64)
    expected_cells, expected_ratios = _python_aspect_ratios(points, faces, owner, 1)

    class FailingNativeMetrics:
        @staticmethod
        def compute_per_cell_aspect_ratios(*_args) -> None:
            raise RuntimeError("forced binding failure")

    monkeypatch.setattr(nc, "_NATIVE_METRICS", FailingNativeMetrics())
    monkeypatch.setattr(nc, "_NATIVE_METRICS_IMPORT_ATTEMPTED", True)
    cells, ratios = NativeMeshChecker._per_cell_aspect_ratios(
        points, faces, owner, 1, 0
    )

    np.testing.assert_array_equal(cells, expected_cells)
    np.testing.assert_allclose(ratios, expected_ratios, rtol=0.0, atol=1e-15)


def test_native_metrics_run_falls_back_when_combined_kernel_fails(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    poly_dir = tmp_path / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True)
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        (poly_dir / name).touch()

    points = [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]
    faces = [
        [0, 2, 1],
        [0, 1, 3],
        [0, 3, 2],
        [1, 2, 3],
    ]
    monkeypatch.setattr(
        nc, "parse_foam_points_array", lambda _path: np.asarray(points, dtype=np.float64)
    )
    monkeypatch.setattr(nc, "parse_foam_faces", lambda _path: faces)
    monkeypatch.setattr(
        nc,
        "parse_foam_labels_array",
        lambda path: np.asarray(
            [0, 0, 0, 0] if path.name == "owner" else [], dtype=np.int64
        ),
    )
    monkeypatch.setattr(nc, "parse_foam_boundary", lambda _path: [{"startFace": 0}])

    calls = {"combined": 0, "centres": 0, "aspect": 0}

    class FailingCombinedMetrics:
        @staticmethod
        def compute_cell_centres_and_aspect_ratios(*_args) -> None:
            calls["combined"] += 1
            raise RuntimeError("forced combined binding failure")

    original_centres = NativeMeshChecker._compute_cell_centres_from_vertices
    original_aspect = NativeMeshChecker._compute_max_aspect_ratio

    def counted_centres(*args, **kwargs):
        calls["centres"] += 1
        return original_centres(*args, **kwargs)

    def counted_aspect(*args, **kwargs):
        calls["aspect"] += 1
        return original_aspect(*args, **kwargs)

    monkeypatch.setattr(nc, "_NATIVE_METRICS", FailingCombinedMetrics())
    monkeypatch.setattr(nc, "_NATIVE_METRICS_IMPORT_ATTEMPTED", True)
    monkeypatch.setattr(
        NativeMeshChecker,
        "_compute_cell_centres_from_vertices",
        staticmethod(counted_centres),
    )
    monkeypatch.setattr(
        NativeMeshChecker,
        "_compute_max_aspect_ratio",
        staticmethod(counted_aspect),
    )

    result = NativeMeshChecker().run(tmp_path)

    assert result.cells == 1
    assert result.max_aspect_ratio == pytest.approx(np.sqrt(2.0))
    assert calls == {"combined": 1, "centres": 1, "aspect": 1}
