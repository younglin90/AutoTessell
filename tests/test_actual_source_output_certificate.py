"""Measured source/output authority certificate L0 contracts."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.evaluator.actual_source_output_certificate import (
    certify_exact_surface_output,
)

_POINTS = np.asarray(
    ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    dtype=np.float64,
)
_FACES = np.asarray(((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)), dtype=np.int64)
_LABELS = ("wall", "inlet", "outlet", "wall")


def _certificate(source_path: Path, **overrides: object):
    values: dict[str, object] = {
        "source_path": source_path,
        "source_points": _POINTS,
        "source_faces": _FACES,
        "output_points": _POINTS.copy(),
        "output_faces": _FACES.copy(),
        "source_feature_ids": ("corner", "edge", "edge", "corner"),
        "source_patch_ids": ("patch-a", "patch-a", "patch-b", "patch-b"),
        "source_physical_groups": _LABELS,
        "output_feature_ids": ("corner", "edge", "edge", "corner"),
        "output_patch_ids": ("patch-a", "patch-a", "patch-b", "patch-b"),
        "output_physical_groups": _LABELS,
        "output_to_source_faces": (0, 1, 2, 3),
    }
    values.update(overrides)
    return certify_exact_surface_output(**values)


def test_exact_output_is_bound_to_source_bytes_and_explicit_authority(tmp_path: Path) -> None:
    source = tmp_path / "source.step"
    source.write_bytes(b"immutable-source-snapshot")

    first = _certificate(source)
    second = _certificate(source)

    assert first == second
    assert first.status == "measured_authoritative_source_output"
    assert first.authoritative is True
    assert first.source_authoritative is True
    assert first.source_vertices_preserved is True
    assert first.source_faces_preserved is True
    assert first.feature_preserved is True
    assert first.patch_preserved is True
    assert first.physical_groups_preserved is True
    assert first.component_bijection is True
    assert first.provenance_complete is True
    assert all(
        getattr(first, field) is not None
        for field in (
            "source_sha256",
            "source_shape_sha256",
            "output_shape_sha256",
            "feature_sha256",
            "patch_sha256",
            "physical_group_sha256",
            "provenance_sha256",
        )
    )


def test_geometry_or_explicit_group_mismatch_rejects_closed_certificate(tmp_path: Path) -> None:
    source = tmp_path / "source.stl"
    source.write_bytes(b"source")
    moved = _POINTS.copy()
    moved[0, 0] = 1.0e-6
    forged_geometry = _certificate(source, output_points=moved)
    forged_groups = _certificate(source, output_physical_groups=("wall", "wall", "outlet", "wall"))

    for certificate in (forged_geometry, forged_groups):
        assert certificate.authoritative is False
        assert certificate.status == "reject_source_output_binding_mismatch"
        assert certificate.rejection_reason == "source_output_binding_mismatch"


def test_missing_mapping_or_authoritative_labels_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source.stl"
    source.write_bytes(b"source")
    missing_mapping = _certificate(source, output_to_source_faces=None)
    missing_groups = _certificate(source, source_physical_groups=None)

    assert missing_mapping.rejection_reason == "explicit_output_to_source_face_mapping_required"
    assert missing_mapping.authoritative is False
    assert missing_groups.rejection_reason == "explicit_feature_patch_physical_group_declarations_required"  # noqa: E501
    assert missing_groups.authoritative is False

