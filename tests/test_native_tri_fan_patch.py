"""Native Tri C++ worst-fan retriangulation and release-lane tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)
from core.preprocessor.native_tri.release_route import (
    NativeTriSourceAuthority,
    run_native_tri_release,
)
from core.utils.native_extensions import load_native_tri_quality_repair


_SOURCE = Path("tests/benchmarks/naca0012.stl")


def _mesh() -> tuple[np.ndarray, np.ndarray]:
    mesh = read_stl(_SOURCE)
    return (
        np.ascontiguousarray(mesh.vertices, dtype=np.float64),
        np.ascontiguousarray(mesh.faces, dtype=np.int64),
    )


def _authority(faces: np.ndarray) -> NativeTriSourceAuthority:
    groups = tuple("naca-wall" for _ in faces)
    return NativeTriSourceAuthority(
        patch_ids=groups,
        physical_groups=AuthoritativePhysicalGroupMapping(groups, True),
        feature_edges=(),
        feature_authoritative=True,
    )


def _proposal() -> tuple[object, np.ndarray, np.ndarray, dict[str, object]]:
    vertices, faces = _mesh()
    module = load_native_tri_quality_repair()
    assert module is not None
    assert hasattr(module, "propose_worst_fan_patch")
    raw = dict(module.propose_worst_fan_patch(vertices, faces, 2, 16))
    candidate = np.ascontiguousarray(
        np.asarray(raw["candidate_faces"], dtype=np.int64),
    )
    return module, vertices, faces, {
        "raw": raw,
        "candidate": candidate,
    }


def test_cpp_worst_fan_patch_is_deterministic_and_bounded() -> None:
    module, vertices, faces, first = _proposal()
    raw = first["raw"]
    assert raw["schema"] == "autotessell/native-tri-worst-fan-patch/v1"
    assert raw["accepted"] is True
    assert raw["selected_centers"] == [158, 159]
    assert raw["removed_faces"] == 318
    assert raw["replacement_faces"] == 314
    candidate = first["candidate"]
    assert candidate.shape == (632, 3)
    assert len(raw["face_correspondence"]) == 314

    repeat = dict(
        module.propose_worst_fan_patch(vertices, faces, 2, 16),
    )
    repeat_faces = np.asarray(repeat["candidate_faces"], dtype=np.int64)
    np.testing.assert_array_equal(candidate, repeat_faces)
    assert repeat["selected_centers"] == raw["selected_centers"]


def test_cpp_worst_fan_patch_passes_strict_quality_admission() -> None:
    module, vertices, faces, first = _proposal()
    candidate = first["candidate"]
    receipt = dict(
        module.admit_surface_edit(
            vertices,
            faces,
            vertices,
            candidate,
            vertices,
            faces,
        ),
    )
    assert receipt["accepted"] is True
    assert receipt["hard_valid"] is True
    assert receipt["after"]["invalid"] == 0
    assert receipt["after"]["self_intersecting"] == 0
    assert receipt["after"]["min_angle"] > receipt["before"]["min_angle"]
    assert receipt["after"]["min_mean_ratio"] > receipt["before"]["min_mean_ratio"]
    assert receipt["after"]["max_edge_aspect"] < receipt["before"]["max_edge_aspect"]


def test_naca_fan_patch_release_is_authoritative_and_transactional(monkeypatch) -> None:
    monkeypatch.setenv("AUTO_TESSELL_NATIVE_TRI_RELEASE", "1")
    monkeypatch.setenv("AUTO_TESSELL_NATIVE_TRI_QUALITY_ADMISSION", "1")
    monkeypatch.setenv("AUTO_TESSELL_NATIVE_TRI_NACA_FAN_PATCH", "1")
    vertices, faces = _mesh()
    result = run_native_tri_release(
        vertices,
        faces,
        target_edge_length=0.15,
        source_authority=_authority(faces),
        max_rounds=1,
        source_path=_SOURCE,
    )
    assert result.accepted is True
    assert result.transaction_applied is True
    assert result.independent_route is True
    assert result.source_topology_valid is True
    assert result.output_topology_valid is True
    assert result.source_envelope_preserved is True
    assert result.source_provenance_authoritative is True
    assert result.feature_recall == 1.0
    assert result.faces.shape == (632, 3)
    assert result.fan_patch is not None
    assert result.fan_patch["transaction_applied"] is True
    assert result.fan_patch["selected_centers"] == [158, 159]
    assert result.quality_admission is not None
    assert result.quality_admission["accepted"] == 1


def test_naca_fan_patch_cannot_bypass_quality_admission(monkeypatch) -> None:
    monkeypatch.setenv("AUTO_TESSELL_NATIVE_TRI_RELEASE", "1")
    monkeypatch.delenv("AUTO_TESSELL_NATIVE_TRI_QUALITY_ADMISSION", raising=False)
    monkeypatch.setenv("AUTO_TESSELL_NATIVE_TRI_NACA_FAN_PATCH", "1")
    vertices, faces = _mesh()
    result = run_native_tri_release(
        vertices,
        faces,
        target_edge_length=0.15,
        source_authority=_authority(faces),
        max_rounds=1,
        source_path=_SOURCE,
    )
    assert result.accepted is False
    assert result.transaction_applied is False
    assert result.independent_route is False
    assert np.array_equal(result.faces, faces)
    assert result.fan_patch is not None
    assert result.fan_patch["reason"] == "quality_admission_required"
