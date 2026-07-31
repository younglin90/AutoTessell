from __future__ import annotations

from pathlib import Path

from core.evaluator.gate4_fidelity_substrate import (
    capture_immutable_source,
    evaluate_gate4_fidelity_evidence,
)
from core.schemas import GeometryFidelity


class _MissingMetricChecker:
    def __init__(self) -> None:
        self.source_paths: list[Path] = []

    def compute(
        self,
        original_stl: Path,
        case_dir: Path,
        diagonal: float,
    ) -> None:
        self.source_paths.append(original_stl)
        assert case_dir.is_dir()
        assert diagonal > 0.0
        return None


class _LegacyMetricChecker(_MissingMetricChecker):
    def compute(
        self,
        original_stl: Path,
        case_dir: Path,
        diagonal: float,
    ) -> GeometryFidelity:
        self.source_paths.append(original_stl)
        assert case_dir.is_dir()
        assert diagonal > 0.0
        return GeometryFidelity(
            hausdorff_distance=0.0,
            hausdorff_relative=0.0,
            surface_area_deviation_percent=0.0,
        )


class _MutatingMetricChecker(_MissingMetricChecker):
    def compute(
        self,
        original_stl: Path,
        case_dir: Path,
        diagonal: float,
    ) -> None:
        self.source_paths.append(original_stl)
        assert diagonal > 0.0
        (case_dir / "constant" / "polyMesh" / "points").write_text("changed", encoding="utf-8")
        return None


def _write_required_polymesh(case_dir: Path) -> None:
    poly_mesh = case_dir / "constant" / "polyMesh"
    poly_mesh.mkdir(parents=True)
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        (poly_mesh / name).write_text(name, encoding="utf-8")


def test_snapshot_preserves_original_bytes_after_source_path_changes(tmp_path: Path) -> None:
    source_path = tmp_path / "source.stl"
    source_path.write_bytes(b"original-source")
    source = capture_immutable_source(source_path, tmp_path / "snapshots")
    source_path.write_bytes(b"changed-source")
    _write_required_polymesh(tmp_path / "case")
    checker = _MissingMetricChecker()

    evidence = evaluate_gate4_fidelity_evidence(
        source=source,
        source_status="unverified_source_snapshot_missing",
        case_dir=tmp_path / "case",
        diagonal=1.0,
        checker=checker,  # type: ignore[arg-type]
    )

    assert Path(source.snapshot_path).read_bytes() == b"original-source"
    assert checker.source_paths == [Path(source.snapshot_path)]
    assert evidence.status == "unverified_metric_missing"
    assert evidence.gate4_pass is False


def test_missing_required_output_artifact_is_unverified(tmp_path: Path) -> None:
    source_path = tmp_path / "source.stl"
    source_path.write_bytes(b"source")
    source = capture_immutable_source(source_path, tmp_path / "snapshots")
    partial_poly_mesh = tmp_path / "case" / "constant" / "polyMesh"
    partial_poly_mesh.mkdir(parents=True)
    (partial_poly_mesh / "points").write_text("points", encoding="utf-8")

    evidence = evaluate_gate4_fidelity_evidence(
        source=source,
        source_status="unverified_source_snapshot_missing",
        case_dir=tmp_path / "case",
        diagonal=1.0,
        checker=_MissingMetricChecker(),  # type: ignore[arg-type]
    )

    assert evidence.status == "unverified_output_artifact_missing"
    assert evidence.output is None
    assert evidence.gate4_pass is False


def test_changed_output_artifact_is_unverified(tmp_path: Path) -> None:
    source_path = tmp_path / "source.stl"
    source_path.write_bytes(b"source")
    source = capture_immutable_source(source_path, tmp_path / "snapshots")
    _write_required_polymesh(tmp_path / "case")

    evidence = evaluate_gate4_fidelity_evidence(
        source=source,
        source_status="unverified_source_snapshot_missing",
        case_dir=tmp_path / "case",
        diagonal=1.0,
        checker=_MutatingMetricChecker(),  # type: ignore[arg-type]
    )

    assert evidence.status == "unverified_output_artifact_changed"
    assert evidence.gate4_pass is False


def test_legacy_metric_remains_nonpromoting(tmp_path: Path) -> None:
    source_path = tmp_path / "source.stl"
    source_path.write_bytes(b"source")
    source = capture_immutable_source(source_path, tmp_path / "snapshots")
    _write_required_polymesh(tmp_path / "case")

    evidence = evaluate_gate4_fidelity_evidence(
        source=source,
        source_status="unverified_source_snapshot_missing",
        case_dir=tmp_path / "case",
        diagonal=1.0,
        checker=_LegacyMetricChecker(),  # type: ignore[arg-type]
    )

    assert evidence.status == "unverified_metric_incomplete"
    assert evidence.metric_status == "legacy_partial"
    assert evidence.geometry_fidelity is not None
    assert evidence.gate4_pass is False


def test_multi_source_defer_does_not_attempt_metric(tmp_path: Path) -> None:
    checker = _MissingMetricChecker()

    evidence = evaluate_gate4_fidelity_evidence(
        source=None,
        source_status="unverified_multi_source_contract_required",
        case_dir=tmp_path / "case",
        diagonal=1.0,
        checker=checker,  # type: ignore[arg-type]
    )

    assert evidence.status == "unverified_multi_source_contract_required"
    assert evidence.metric_status == "not_attempted"
    assert checker.source_paths == []
    assert evidence.gate4_pass is False
