"""Focused contracts for the default-off CAD snapshot provenance reader."""

from __future__ import annotations

import json
import stat
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import numpy as np

from core.analyzer.readers.step import CadEntityProvenance, CadNativeTriangulation
from core.analyzer.readers.step_snapshot_provenance_l0 import (
    canonical_cad_reader_payload_sha256,
    load_cad_native_with_provenance_snapshot_l0,
)

_ENABLE = "AUTO_TESSELL_CAD_PROVENANCE_SNAPSHOT_L0"


def _readonly(value: np.ndarray) -> np.ndarray:
    value.setflags(write=False)
    return value


def _hash(value: np.ndarray, dtype: str) -> str:
    return sha256(np.ascontiguousarray(value, dtype=dtype).tobytes()).hexdigest()


def _fixture() -> CadNativeTriangulation:
    vertices = np.asarray(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)),
        dtype=np.float64,
    )
    faces = np.asarray(((0, 1, 2), (1, 3, 2)), dtype=np.int64)
    ordinals = _readonly(np.asarray((0, 1), dtype=np.int64))
    orientation = _readonly(np.asarray((False, True), dtype=np.bool_))
    seams = _readonly(np.asarray((0, 1, 2, 3), dtype=np.int64))
    sources = _readonly(np.asarray((0, 1, 2, 3), dtype=np.int64))
    oriented = faces.copy()
    oriented[orientation] = oriented[orientation][:, (0, 2, 1)]
    canonical_faces = _readonly(seams[oriented])
    xde = {
        "face_names": (None, None),
        "layer_names": ((), ()),
        "surface_colors": (None, None),
        "assembly_paths": (None, None),
        "layer_authoritative": False,
        "physical_group_authoritative": False,
    }
    provenance = CadEntityProvenance(
        status="partial_authority_physical_groups_unavailable",
        face_count=2,
        topological_edge_count=5,
        triangle_face_ordinals=ordinals,
        triangle_orientation_reversed=orientation,
        seam_vertex_ids=seams,
        canonical_vertex_source_ids=sources,
        oriented_canonical_faces=canonical_faces,
        face_names=(None, None),
        physical_group_names=(None, None),
        xde_layer_names=((), ()),
        xde_surface_colors=(None, None),
        xde_assembly_paths=(None, None),
        xde_layer_authoritative=False,
        xde_layer_coverage_count=0,
        xde_color_display_metadata_authoritative=False,
        xde_assembly_identity_authoritative=False,
        face_ordinals_authoritative=True,
        face_orientation_authoritative=True,
        seam_connectivity_authoritative=True,
        physical_groups_authoritative=False,
        ordered_triangle_coordinate_sha256=_hash(vertices[faces], "<f8"),
        ordered_face_ordinal_sha256=_hash(ordinals, "<i8"),
        ordered_orientation_sha256=_hash(orientation, "u1"),
        seam_connectivity_sha256=_hash(canonical_faces, "<i8"),
        xde_metadata_sha256=sha256(
            json.dumps(xde, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )
    return CadNativeTriangulation(vertices, faces, provenance)


def _assert_never_success(report: object) -> None:
    assert getattr(report, "candidate_constructed") is False
    assert getattr(report, "production_mesh_changed") is False
    assert getattr(report, "artifact_delta") == 0
    assert getattr(report, "accepted") is False
    assert getattr(report, "mesher_success_allowed") is False
    assert getattr(report, "product_claimed") is False


def _call(source: Path, reader, *, source_hash: str | None = None, payload_hash: str | None = None):
    expected_source = (
        source_hash or sha256(source.read_bytes() if source.exists() else b"").hexdigest()
    )
    expected_payload = payload_hash or canonical_cad_reader_payload_sha256(_fixture())
    return load_cad_native_with_provenance_snapshot_l0(
        source,
        ".step",
        expected_source_sha256=expected_source,
        expected_reader_payload_sha256=expected_payload,
        reader=reader,
    )


def test_default_off_does_not_open_source_or_reader(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(_ENABLE, raising=False)
    report = _call(
        tmp_path / "missing.step",
        lambda *_args: (_ for _ in ()).throw(AssertionError("reader must not run")),
    )
    assert report.status == "disabled_cad_provenance_snapshot_l0"
    assert not report.reader_invoked
    _assert_never_success(report)


def test_snapshot_hashes_exact_bytes_private_path_and_cleans_up(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(_ENABLE, "1")
    source = tmp_path / "source.step"
    original = (b"cad-snapshot" * 180_000) + b"end"
    source.write_bytes(original)
    observed: dict[str, object] = {}

    def reader(snapshot: Path, fmt: str) -> CadNativeTriangulation:
        observed["snapshot"] = snapshot
        observed["bytes"] = snapshot.read_bytes()
        observed["mode"] = stat.S_IMODE(snapshot.stat().st_mode)
        observed["parent_mode"] = stat.S_IMODE(snapshot.parent.stat().st_mode)
        observed["fmt"] = fmt
        source.write_bytes(b"mutated-after-snapshot")
        return _fixture()

    report = _call(source, reader)

    assert report.status == "report_snapshot_reader_provenance_unverified"
    assert report.source_snapshot_sha256 == sha256(original).hexdigest()
    assert report.source_snapshot_bytes == len(original)
    assert report.source_digest_matches and report.reader_payload_matches
    assert observed["bytes"] == original and observed["fmt"] == ".step"
    assert observed["snapshot"] != source and not Path(observed["snapshot"]).exists()
    assert observed["mode"] == 0o600 and observed["parent_mode"] == 0o700
    assert report.triangulation is not None and not report.triangulation.vertices.flags.writeable
    _assert_never_success(report)


def test_missing_source_digest_and_payload_mismatch_fail_closed(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(_ENABLE, "1")
    source = tmp_path / "source.step"
    source.write_bytes(b"cad")
    calls = 0

    def reader(*_args) -> CadNativeTriangulation:
        nonlocal calls
        calls += 1
        return _fixture()

    missing = _call(tmp_path / "missing.step", reader)
    bad_source = _call(source, reader, source_hash="0" * 64)
    bad_payload = _call(source, reader, payload_hash="0" * 64)

    assert missing.status == "reject_snapshot_source_not_found"
    assert bad_source.status == "reject_snapshot_source_digest_mismatch"
    assert not missing.reader_invoked and not bad_source.reader_invoked
    assert bad_payload.status == "reject_snapshot_reader_payload_digest_mismatch"
    assert calls == 1
    for report in (missing, bad_source, bad_payload):
        _assert_never_success(report)


def test_malformed_brep_or_physical_injection_rejects(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(_ENABLE, "1")
    source = tmp_path / "source.step"
    source.write_bytes(b"cad")
    base = _fixture()
    malformed = replace(
        base,
        provenance=replace(base.provenance, ordered_orientation_sha256="0" * 64),
    )
    physical = replace(
        base,
        provenance=replace(
            base.provenance,
            physical_groups_authoritative=True,
            physical_group_names=("inlet", "wall"),
        ),
    )
    reports = tuple(
        _call(source, lambda *_args, value=value: value) for value in (malformed, physical)
    )
    assert reports[0].status == "reject_snapshot_provenance_payload"
    assert reports[0].malformed_evidence == ("provenance_hashes",)
    assert reports[1].malformed_evidence == ("physical_groups",)
    assert reports[1].physical_groups_authoritative
    for report in reports:
        _assert_never_success(report)


def test_reader_failure_cleans_private_snapshot(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(_ENABLE, "1")
    source = tmp_path / "source.step"
    source.write_bytes(b"cad")
    observed: dict[str, Path] = {}

    def failing_reader(snapshot: Path, _fmt: str) -> CadNativeTriangulation:
        observed["snapshot"] = snapshot
        raise ValueError("reader failure")

    report = _call(source, failing_reader)

    assert report.status == "reject_snapshot_provenance_reader_failed"
    assert report.snapshot_removed and not observed["snapshot"].exists()
    _assert_never_success(report)
