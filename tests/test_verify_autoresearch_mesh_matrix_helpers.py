"""Unit tests for autoresearch mesh verifier selection helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
VERIFIER_PATH = ROOT / "tests" / "stl" / "verify_autoresearch_mesh_matrix.py"
BENCH_PATH = ROOT / "scripts" / "bench_native_tet_matrix.py"
SPEC = importlib.util.spec_from_file_location("verify_autoresearch_mesh_matrix", VERIFIER_PATH)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)
BENCH_SPEC = importlib.util.spec_from_file_location("bench_native_tet_matrix", BENCH_PATH)
assert BENCH_SPEC is not None and BENCH_SPEC.loader is not None
bench = importlib.util.module_from_spec(BENCH_SPEC)
BENCH_SPEC.loader.exec_module(bench)


CUBE_POINTS = np.asarray(
    [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 1.0],
        [1.0, 1.0, 1.0],
        [0.0, 1.0, 1.0],
    ],
    dtype=np.float64,
)
CUBE_FACES = np.asarray(
    [
        [0, 2, 1], [0, 3, 2],
        [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4],
        [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6],
        [3, 0, 4], [3, 4, 7],
    ],
    dtype=np.int64,
)


def _write_ascii_stl(path: Path, points: np.ndarray, faces: np.ndarray) -> None:
    lines = ["solid cube"]
    for face in faces:
        lines.extend(["facet normal 0 0 0", "outer loop"])
        lines.extend(
            f"vertex {point[0]:.17g} {point[1]:.17g} {point[2]:.17g}"
            for point in points[face]
        )
        lines.extend(["endloop", "endfacet"])
    lines.append("endsolid cube")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def _write_boundary_polymesh(
    case_dir: Path,
    points: np.ndarray,
    faces: np.ndarray,
    *,
    corrupt_points: bool = False,
) -> None:
    poly_dir = case_dir / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True)
    point_rows = "bad data" if corrupt_points else "\n".join(
        f"({point[0]:.17g} {point[1]:.17g} {point[2]:.17g})" for point in points
    )
    (poly_dir / "points").write_text(
        f"FoamFile {{}}\n{len(points)}\n(\n{point_rows}\n)\n", encoding="ascii"
    )
    face_rows = "\n".join(
        f"3({int(face[0])} {int(face[1])} {int(face[2])})" for face in faces
    )
    (poly_dir / "faces").write_text(
        f"FoamFile {{}}\n{len(faces)}\n(\n{face_rows}\n)\n", encoding="ascii"
    )
    (poly_dir / "boundary").write_text(
        "FoamFile {}\n1\n(\nobject\n{\ntype wall;\n"
        f"nFaces {len(faces)};\nstartFace 0;\n"
        "}\n)\n",
        encoding="ascii",
    )


def test_native_tet_engine_and_aliases_are_opt_in() -> None:
    assert verifier.ENGINES["native_tet"] == ("tet", "native_tet")
    assert verifier._parse_engine_selection("") == ["tet", "hex", "poly"]
    assert verifier._parse_engine_selection("all") == ["tet", "hex", "poly"]
    assert verifier._parse_engine_selection("native_tet") == ["native_tet"]
    assert verifier._parse_engine_selection("native-tet") == ["native_tet"]
    assert verifier._parse_engine_selection("tier_native_tet") == ["native_tet"]
    assert verifier._parse_engine_selection("tet,native_tet native-tet") == [
        "tet",
        "native_tet",
    ]


def test_native_tet_hard12_has_exact_fixed_membership() -> None:
    expected = {
        "cube.stl",
        "cylinder.stl",
        "sphere.stl",
        "sphere_watertight.stl",
        "naca0012.stl",
        "trimesh_box.stl",
        "external_flow_isolated_box.stl",
        "very_thin_disk_0_01mm.stl",
        "extreme_aspect_ratio_needle.stl",
        "high_genus_dual_torus.stl",
        "multi_scale_sphere_with_micro_spikes.stl",
        "many_small_features_perforated_plate.stl",
    }

    paths = verifier._stl_candidates("native_tet_hard12", root=Path("/repo"))

    assert len(paths) == 12
    assert {path.name for path in paths} == expected
    assert set(verifier.NATIVE_TET_HARD12) == set(bench.INCLUDE) - {
        "sharp_features_micro_ridge.stl"
    }
    assert all(path.parent == Path("/repo/tests/benchmarks") for path in paths)
    assert "sharp_features_micro_ridge.stl" not in {path.name for path in paths}
    assert all(path.exists() for path in verifier._stl_candidates("native_tet_hard12", root=ROOT))


def test_unknown_stl_set_is_rejected() -> None:
    with pytest.raises(SystemExit, match="Unknown AUTO_TESSELL_VERIFY_STL_SET"):
        verifier._stl_candidates("unknown")


@pytest.mark.parametrize(
    ("failed_cases", "fail_count", "strict", "expected"),
    [
        (0, 0, False, 0),
        (1, 0, False, 0),
        (0, 1, False, 0),
        (0, 0, True, 0),
        (1, 0, True, 1),
        (0, 1, True, 1),
    ],
)
def test_verification_exit_code(
    failed_cases: int,
    fail_count: int,
    strict: bool,
    expected: int,
) -> None:
    assert (
        verifier._verification_exit_code(
            failed_cases=failed_cases,
            fail_count=fail_count,
            strict=strict,
        )
        == expected
    )


def test_fidelity_fallback_identical_cube_is_exact(tmp_path: Path) -> None:
    stl_path = tmp_path / "cube.stl"
    case_dir = tmp_path / "case"
    _write_ascii_stl(stl_path, CUBE_POINTS, CUBE_FACES)
    _write_boundary_polymesh(case_dir, CUBE_POINTS, CUBE_FACES)

    measured = verifier._measure_fidelity_fallback(stl_path, case_dir)

    assert measured["available"] is True
    assert measured["input_connected_components"] == 1
    assert measured["hausdorff_distance"] == pytest.approx(0.0, abs=1e-12)
    assert measured["hausdorff_relative"] == pytest.approx(0.0, abs=1e-12)
    assert measured["distance_rms"] == pytest.approx(0.0, abs=1e-12)
    assert measured["distance_p95"] == pytest.approx(0.0, abs=1e-12)
    assert measured["distance_p99"] == pytest.approx(0.0, abs=1e-12)
    assert measured["surface_area_deviation_percent"] == pytest.approx(0.0, abs=1e-12)
    assert measured["normal_deviation_max_deg"] == pytest.approx(0.0, abs=1e-7)
    assert measured["feature_preservation_score"] == pytest.approx(1.0)


def test_fidelity_fallback_ignores_unreferenced_interior_points(tmp_path: Path) -> None:
    stl_path = tmp_path / "cube.stl"
    case_dir = tmp_path / "case"
    points = np.vstack([CUBE_POINTS, np.asarray([[0.5, 0.5, 0.5]])])
    _write_ascii_stl(stl_path, CUBE_POINTS, CUBE_FACES)
    _write_boundary_polymesh(case_dir, points, CUBE_FACES)

    measured = verifier._measure_fidelity_fallback(stl_path, case_dir)

    assert measured["available"] is True
    assert measured["hausdorff_relative"] == pytest.approx(0.0, abs=1e-12)
    assert measured["distance_rms"] == pytest.approx(0.0, abs=1e-12)


def test_fidelity_fallback_uses_marked_semantic_reference(tmp_path: Path) -> None:
    stl_path = tmp_path / "overlapping_input.stl"
    case_dir = tmp_path / "case"
    shifted = CUBE_POINTS + np.asarray([5.0, 0.0, 0.0])
    _write_ascii_stl(stl_path, shifted, CUBE_FACES)
    _write_boundary_polymesh(case_dir, CUBE_POINTS, CUBE_FACES)
    semantic_path = case_dir / "_work" / "preprocessed.stl"
    semantic_path.parent.mkdir(parents=True, exist_ok=True)
    _write_ascii_stl(semantic_path, CUBE_POINTS, CUBE_FACES)
    (case_dir / "native_tet_perforated_extrusion.marker").write_text(
        "1\n", encoding="ascii"
    )

    measured = verifier._measure_fidelity_fallback(stl_path, case_dir)

    assert measured["available"] is True
    assert measured["hausdorff_relative"] == pytest.approx(0.0, abs=1e-12)


def test_fidelity_fallback_detects_perturbed_cube(tmp_path: Path) -> None:
    stl_path = tmp_path / "cube.stl"
    case_dir = tmp_path / "case"
    perturbed = CUBE_POINTS.copy()
    perturbed[6] += np.asarray([0.2, 0.1, 0.15])
    _write_ascii_stl(stl_path, CUBE_POINTS, CUBE_FACES)
    _write_boundary_polymesh(case_dir, perturbed, CUBE_FACES)

    measured = verifier._measure_fidelity_fallback(stl_path, case_dir)

    assert measured["available"] is True
    assert measured["hausdorff_relative"] > 0.02
    assert measured["distance_rms"] > 0.0
    assert measured["distance_p95"] > 0.0
    assert measured["distance_p99"] > 0.0
    assert measured["surface_area_deviation_percent"] > 0.0
    assert measured["normal_deviation_max_deg"] > 0.0
    assert measured["feature_preservation_score"] < 1.0


def test_fidelity_fallback_missing_or_corrupt_data_fails_closed(tmp_path: Path) -> None:
    stl_path = tmp_path / "cube.stl"
    _write_ascii_stl(stl_path, CUBE_POINTS, CUBE_FACES)

    missing = verifier._measure_fidelity_fallback(stl_path, tmp_path / "missing")
    assert missing["available"] is False
    assert "missing" in missing["error"]

    corrupt_case = tmp_path / "corrupt"
    _write_boundary_polymesh(
        corrupt_case,
        CUBE_POINTS,
        CUBE_FACES,
        corrupt_points=True,
    )
    corrupt = verifier._measure_fidelity_fallback(stl_path, corrupt_case)
    assert corrupt["available"] is False
    assert corrupt["error"] == "polyMesh boundary parse failed"


def test_classify_fills_missing_report_fidelity_from_fallback() -> None:
    fallback = verifier._measure_surface_fidelity(
        CUBE_POINTS,
        CUBE_FACES,
        CUBE_POINTS,
        CUBE_FACES,
    )
    row = verifier._classify(
        {"returncode": 0, "tier": "native_tet"},
        {"evaluation_summary": {"geometry_fidelity": None}},
        {},
        {},
        {},
        {},
        {"available": True, "n_boundary_components": 1, "patch_count": 1},
        fallback,
    )

    assert row["fidelity_source"] == "verifier_fallback"
    assert row["input_components"] == 1
    assert row["hausdorff_relative"] == pytest.approx(0.0, abs=1e-12)
    assert row["surface_area_deviation_percent"] == pytest.approx(0.0, abs=1e-12)
    assert not any(
        failure in {
            "missing_metric:fidelity_rms",
            "missing_metric:fidelity_p95",
            "missing_metric:fidelity_p99",
            "missing_metric:normal_deviation",
            "missing_metric:feature_preservation",
            "missing_metric:input_connected_components",
        }
        for failure in row["failures"]
    )


def test_surface_components_require_shared_edges_not_touching_vertex() -> None:
    vertices = np.array(
        [
            [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0], [-1.0, 0.0, 0.0], [0.0, -1.0, 0.0],
        ]
    )
    faces = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)

    assert verifier._surface_components(vertices, faces) == 2
