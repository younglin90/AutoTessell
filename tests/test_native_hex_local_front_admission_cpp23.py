"""L0/L1 contracts for default-OFF local-front admission evidence."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.generator.native_hex.local_front_admission_l0 import audit_local_front_admission_l0
from core.generator.native_hex.source_feature_sidecar_l1 import (
    AuthoritativeSourceFeatureManifest,
    ordered_triangle_coordinate_sha256,
)

_ROOT = Path(__file__).resolve().parents[1]
_ENV = "AUTO_TESSELL_HEX_LOCAL_FRONT_ADMISSION_CPP23"


def _cube_manifest(path: Path) -> tuple[np.ndarray, np.ndarray, AuthoritativeSourceFeatureManifest]:
    mesh = read_stl(path)
    points = np.ascontiguousarray(mesh.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(mesh.faces, dtype=np.int64)
    manifest = AuthoritativeSourceFeatureManifest(
        hashlib.sha256(path.read_bytes()).hexdigest(),
        ordered_triangle_coordinate_sha256(points, faces),
        (("fixture", "wall"),) * len(faces),
    )
    return points, faces, manifest


def test_l0_authoritative_cube_admits_exact_three_quad_rows_without_mutation() -> None:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    points, faces, manifest = _cube_manifest(path)
    point_hash, face_hash = (
        hashlib.sha256(points.tobytes()).hexdigest(),
        hashlib.sha256(faces.tobytes()).hexdigest(),
    )
    report = audit_local_front_admission_l0(
        points,
        faces,
        source_path=path,
        manifest=manifest,
        requested_step=0.1,
    )
    assert report.status == "pass_local_front_admission"
    assert report.admitted and report.source_rows_complete and report.clearance_sufficient
    assert report.quad_count == 3 * report.source_face_count
    assert report.source_geometry_unchanged and not report.native_checked
    assert hashlib.sha256(points.tobytes()).hexdigest() == point_hash
    assert hashlib.sha256(faces.tobytes()).hexdigest() == face_hash


@pytest.mark.parametrize("step", (1.1, float("nan"), -0.1))
def test_l0_sampled_clearance_or_invalid_step_rejects_without_candidate(step: float) -> None:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    points, faces, manifest = _cube_manifest(path)
    report = audit_local_front_admission_l0(
        points,
        faces,
        source_path=path,
        manifest=manifest,
        requested_step=step,
    )
    assert report.status == "reject_sampled_inward_clearance"
    assert not report.admitted and not report.source_rows_complete
    assert report.source_geometry_unchanged


def test_l0_manifest_mismatch_fails_closed() -> None:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    points, faces, manifest = _cube_manifest(path)
    bad = AuthoritativeSourceFeatureManifest(
        "0" * 64, manifest.ordered_triangle_coordinate_sha256, manifest.face_entities
    )
    report = audit_local_front_admission_l0(
        points, faces, source_path=path, manifest=bad, requested_step=0.1
    )
    assert report.status == "reject_authoritative_source_provenance"
    assert not report.admitted and report.quad_count == 0


def test_l1_default_off_and_opt_in_missing_native_are_same_three_times() -> None:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    points, faces, manifest = _cube_manifest(path)
    with patch.dict(os.environ, {}, clear=True):
        expected = audit_local_front_admission_l0(
            points,
            faces,
            source_path=path,
            manifest=manifest,
            requested_step=0.1,
        )
    with (
        patch.dict(os.environ, {_ENV: "1"}),
        patch("core.generator.native_hex.quality._load_native_hex_quality", return_value=None),
    ):
        actual = [
            audit_local_front_admission_l0(
                points,
                faces,
                source_path=path,
                manifest=manifest,
                requested_step=0.1,
            )
            for _ in range(3)
        ]
    assert actual == [expected, expected, expected]


def test_l1_opt_in_native_numeric_parity_is_deterministic() -> None:
    from core.generator.native_hex import quality

    native = quality._load_native_hex_quality()
    if native is None or not hasattr(native, "local_front_numeric_admission"):
        pytest.skip("native_hex_quality local-front admission extension is not built")
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    points, faces, manifest = _cube_manifest(path)
    with patch.dict(os.environ, {_ENV: "1"}):
        reports = [
            audit_local_front_admission_l0(
                points,
                faces,
                source_path=path,
                manifest=manifest,
                requested_step=0.1,
            )
            for _ in range(3)
        ]
    assert reports == [reports[0]] * 3
    assert reports[0].admitted and reports[0].native_checked


def test_l0_native_numeric_predicate_has_strict_abi_and_row_gate() -> None:
    from core.generator.native_hex import quality

    native = quality._load_native_hex_quality()
    if native is None or not hasattr(native, "local_front_numeric_admission"):
        pytest.skip("native_hex_quality local-front admission extension is not built")
    ids = np.array((0, 0, 0, 1, 1, 1), dtype=np.int64)
    accepted = native.local_front_numeric_admission(ids, 2, 0.1, 0.2)
    assert accepted == {
        "source_rows_complete": True,
        "clearance_sufficient": True,
        "source_face_count": 2,
        "quad_count": 6,
    }
    duplicate = native.local_front_numeric_admission(
        np.array((0, 0, 0, 0, 1, 1), dtype=np.int64), 2, 0.1, 0.2
    )
    assert duplicate["source_rows_complete"] is False
    with pytest.raises(TypeError):
        native.local_front_numeric_admission(ids.astype(np.int32), 2, 0.1, 0.2)
    with pytest.raises(TypeError):
        native.local_front_numeric_admission(ids[::-1], 2, 0.1, 0.2)


def test_l1_malformed_native_result_fails_closed() -> None:
    path = _ROOT / "tests" / "benchmarks" / "cube.stl"
    points, faces, manifest = _cube_manifest(path)
    native = SimpleNamespace(
        local_front_numeric_admission=lambda *_: {"source_rows_complete": True}
    )
    with (
        patch.dict(os.environ, {_ENV: "1"}),
        patch("core.generator.native_hex.quality._load_native_hex_quality", return_value=native),
        pytest.raises(RuntimeError, match="disagrees"),
    ):
        audit_local_front_admission_l0(
            points,
            faces,
            source_path=path,
            manifest=manifest,
            requested_step=0.1,
        )
