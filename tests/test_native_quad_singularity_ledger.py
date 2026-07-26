"""QUAD-SINGULARITY1 explicit ambiguous-face ledger tests.

The ledger is a report-only view over the unchanged extrinsic and intrinsic
4-RoSy censuses.  Synthetic faces pin its data contract; the three benchmark
shapes pin the measured connection behavior that QUAD-POSY1 must consume.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pytest

from core.preprocessor.native_remesh.rosy_diagnostic import (
    OrientationSingularity,
    RosyDiagnosticReport,
    SingularityCensus,
    build_singularity_ledger,
    run_rosy_diagnostic,
)

STL_DIR = Path(__file__).parent / "stl"


def _synthetic_faces(n_faces: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """Disjoint triangles whose IDs, vertices, and centroids are obvious."""
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for face in range(n_faces):
        x = float(face * 10)
        base = len(vertices)
        vertices.extend(((x, 0.0, 0.0), (x + 3.0, 0.0, 0.0), (x, 3.0, 0.0)))
        faces.append((base, base + 1, base + 2))
    return np.asarray(vertices, dtype=np.float64), np.asarray(faces, dtype=np.int64)


def _singularity(face: int, index: int) -> OrientationSingularity:
    return OrientationSingularity(face=face, index=index, centroid=(0.0, 0.0, 0.0))


def _census(connection: str, values: tuple[tuple[int, int], ...]) -> SingularityCensus:
    return SingularityCensus(
        connection=connection,
        euler_characteristic=0,
        closed=True,
        singularities=tuple(_singularity(face, index) for face, index in values),
    )


def _load_stl(name: str) -> tuple[np.ndarray, np.ndarray]:
    trimesh = pytest.importorskip("trimesh")
    mesh = trimesh.load(str(STL_DIR / name), process=True)
    mesh.merge_vertices()
    return (
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int64),
    )


@pytest.fixture(scope="module")
def measured_reports() -> dict[str, RosyDiagnosticReport]:
    reports: dict[str, RosyDiagnosticReport] = {}
    for filename in (
        "01_easy_cube.stl",
        "02_medium_cylinder.stl",
        "03_hard_bracket.stl",
    ):
        vertices, faces = _load_stl(filename)
        reports[filename] = run_rosy_diagnostic(
            vertices,
            faces,
            filename,
            n_sweeps=20,
            seed=0,
            multires=True,
            with_curvature=False,
        )
    return reports


def test_synthetic_union_categories_and_admissible_indices() -> None:
    vertices, faces = _synthetic_faces()
    vertices_before, faces_before = vertices.copy(), faces.copy()
    extrinsic = _census("extrinsic", ((4, 2), (3, -1), (2, 2), (1, 1)))
    intrinsic = _census("intrinsic", ((0, 1), (1, 1), (2, -1), (4, 2)))

    ledger = build_singularity_ledger(vertices, faces, extrinsic, intrinsic)

    assert [entry.face for entry in ledger.entries] == [0, 1, 2, 3, 4]
    assert ledger.union_count == 5
    assert ledger.shared_count == 3
    assert ledger.extrinsic_only_count == 1
    assert ledger.intrinsic_only_count == 1
    assert ledger.disagreement_count == 1
    assert ledger.ambiguous_count == 2
    assert ledger.unresolved_count == 4
    assert ledger.poincare_hopf_consistent
    assert np.array_equal(vertices, vertices_before)
    assert np.array_equal(faces, faces_before)

    intrinsic_only, agreed, disagreed, extrinsic_only, ambiguous = ledger.entries
    assert intrinsic_only.category == "intrinsic-only"
    assert intrinsic_only.extrinsic_index == 0
    assert intrinsic_only.extrinsic_admissible_indices == (0,)
    assert intrinsic_only.intrinsic_admissible_indices == (1,)
    assert intrinsic_only.unresolved

    assert agreed.category == "shared"
    assert agreed.connection_agreement
    assert not agreed.connection_disagreement
    assert not agreed.unresolved

    assert disagreed.connection_disagreement
    assert disagreed.extrinsic_admissible_indices == (-2, 2)
    assert disagreed.intrinsic_admissible_indices == (-1,)
    assert disagreed.unresolved

    assert extrinsic_only.category == "extrinsic-only"
    assert extrinsic_only.intrinsic_index == 0
    assert extrinsic_only.unresolved

    assert ambiguous.connection_agreement
    assert ambiguous.extrinsic_admissible_indices == (-2, 2)
    assert ambiguous.intrinsic_admissible_indices == (-2, 2)
    assert ambiguous.unresolved, "agreement must not hide the +-1/2 sign choice"


def test_synthetic_entries_carry_exact_face_vertices_and_centroids() -> None:
    vertices, faces = _synthetic_faces()
    ledger = build_singularity_ledger(
        vertices,
        faces,
        _census("extrinsic", ((3, 1),)),
        _census("intrinsic", ()),
    )
    entry = ledger.entries[0]
    assert entry.face == 3
    assert entry.face_vertex_ids == tuple(int(v) for v in faces[3])
    assert entry.centroid == (31.0, 1.0, 0.0)


def test_cube_keeps_eight_positive_quarter_indices_without_shared_disagreement(
    measured_reports: dict[str, RosyDiagnosticReport],
) -> None:
    report = measured_reports["01_easy_cube.stl"]
    assert report.extrinsic is not None and report.intrinsic is not None
    assert report.ledger is not None
    assert report.extrinsic.n_singularities == 8
    assert report.intrinsic.n_singularities == 8
    assert report.extrinsic.index_histogram == {1: 8}
    assert report.intrinsic.index_histogram == {1: 8}
    assert report.ledger.disagreement_count == 0
    assert report.ledger.ambiguous_count == 0
    assert (
        report.ledger.union_count,
        report.ledger.shared_count,
        report.ledger.extrinsic_only_count,
        report.ledger.intrinsic_only_count,
        report.ledger.unresolved_count,
    ) == (10, 6, 2, 2, 4)
    assert report.ledger.poincare_hopf_consistent


def test_cylinder_multires_ledger_matches_existing_census(
    measured_reports: dict[str, RosyDiagnosticReport],
) -> None:
    report = measured_reports["02_medium_cylinder.stl"]
    assert report.extrinsic is not None and report.intrinsic is not None
    assert report.ledger is not None
    assert report.extrinsic.n_singularities == 18
    assert report.intrinsic.n_singularities == 18
    assert report.extrinsic.index_sum == report.intrinsic.index_sum == 0
    assert report.extrinsic.n_half_index == report.intrinsic.n_half_index == 0
    assert report.extrinsic.poincare_hopf_ok
    assert report.intrinsic.poincare_hopf_ok
    assert (
        report.ledger.union_count,
        report.ledger.shared_count,
        report.ledger.extrinsic_only_count,
        report.ledger.intrinsic_only_count,
        report.ledger.disagreement_count,
        report.ledger.ambiguous_count,
        report.ledger.unresolved_count,
    ) == (26, 10, 8, 8, 0, 0, 16)
    assert report.ledger.poincare_hopf_consistent


def test_hard_bracket_preserves_multires_18_vs_4_ambiguity(
    measured_reports: dict[str, RosyDiagnosticReport],
) -> None:
    report = measured_reports["03_hard_bracket.stl"]
    assert report.extrinsic is not None and report.intrinsic is not None
    assert report.ledger is not None
    assert report.extrinsic.n_singularities == 38
    assert report.intrinsic.n_singularities == 56
    assert report.extrinsic.n_half_index == 18
    assert report.intrinsic.n_half_index == 4
    assert report.extrinsic.poincare_hopf_reconcilable
    assert report.intrinsic.poincare_hopf_reconcilable
    assert (
        report.ledger.union_count,
        report.ledger.shared_count,
        report.ledger.extrinsic_only_count,
        report.ledger.intrinsic_only_count,
        report.ledger.disagreement_count,
        report.ledger.ambiguous_count,
        report.ledger.unresolved_count,
    ) == (69, 25, 13, 31, 6, 18, 54)
    assert report.ledger.poincare_hopf_consistent


def test_ledger_is_dataclass_and_byte_deterministic(
    measured_reports: dict[str, RosyDiagnosticReport],
) -> None:
    first = measured_reports["03_hard_bracket.stl"]
    vertices, faces = _load_stl("03_hard_bracket.stl")
    second = run_rosy_diagnostic(
        vertices,
        faces,
        "03_hard_bracket.stl",
        n_sweeps=20,
        seed=0,
        multires=True,
        with_curvature=False,
    )
    assert first.ledger is not None and second.ledger is not None
    assert first.extrinsic == second.extrinsic
    assert first.intrinsic == second.intrinsic
    assert first.ledger == second.ledger
    assert pickle.dumps(first.ledger, protocol=5) == pickle.dumps(second.ledger, protocol=5)
    assert first.energy_before == second.energy_before
    assert first.energy_after == second.energy_after
    assert first.ledger.extrinsic is first.extrinsic
    assert first.ledger.intrinsic is first.intrinsic
