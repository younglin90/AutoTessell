import numpy as np

from core.generator.native_tet.core_certificate import snapshot_tet_core_certificate


def test_core_certificate_reports_exact_single_tetra_boundary() -> None:
    points = np.asarray(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))
    faces = np.asarray(((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)))
    report = snapshot_tet_core_certificate(faces, points, np.asarray([(0, 1, 2, 3)]), "unit")
    assert report.n_tets == 1
    assert report.n_boundary_faces == 4
    assert report.strict_source_face_ratio == 1.0
    assert report.boundary_source_face_ratio == 1.0
    assert report.n_zero_volume == 0
    assert report.n_negative_orientation == 0


def test_core_certificate_reports_zero_volume_tetra() -> None:
    points = np.asarray(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)))
    faces = np.asarray(((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)))
    report = snapshot_tet_core_certificate(faces, points, np.asarray([(0, 1, 2, 3)]), "flat")
    assert report.n_zero_volume == 1
