from pathlib import Path

import numpy as np

from core.evaluator.volume_source_output_certificate import (
    certify_volume_source_output,
)


def _input(tmp_path: Path):
    source = tmp_path / "source.stl"
    source.write_bytes(b"source")
    points = np.asarray(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        dtype=np.float64,
    )
    faces = np.asarray(
        ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)),
        dtype=np.int64,
    )
    return source, points, faces


def test_volume_certificate_requires_explicit_measurements(tmp_path: Path) -> None:
    source, points, faces = _input(tmp_path)
    cert = certify_volume_source_output(
        source,
        points,
        faces,
        points,
        np.asarray(((0, 1, 2, 3),), dtype=np.int64),
        source_feature_ids=("f0", "f1", "f2", "f3"),
        source_patch_ids=("wall", "wall", "wall", "wall"),
        source_physical_groups=("wall", "wall", "wall", "wall"),
        provenance={"source_face_map": [0, 1, 2, 3]},
        source_vertices_preserved=True,
        source_faces_preserved=True,
        feature_preserved=True,
        patch_preserved=True,
        physical_groups_preserved=True,
        component_bijection=True,
        provenance_complete=True,
    )
    assert cert.authoritative is True
    assert cert.status == "measured_authoritative_volume_source_output"
    assert len(cert.source_sha256 or "") == 64


def test_volume_certificate_rejects_missing_labels(tmp_path: Path) -> None:
    source, points, faces = _input(tmp_path)
    cert = certify_volume_source_output(
        source,
        points,
        faces,
        points,
        np.asarray(((0, 1, 2, 3),), dtype=np.int64),
        source_feature_ids=None,
        source_patch_ids=("wall",) * 4,
        source_physical_groups=("wall",) * 4,
        provenance={},
        source_vertices_preserved=True,
        source_faces_preserved=True,
        feature_preserved=True,
        patch_preserved=True,
        physical_groups_preserved=True,
        component_bijection=True,
        provenance_complete=True,
    )
    assert cert.authoritative is False
    assert cert.rejection_reason == "explicit_feature_patch_physical_group_declarations_required"
