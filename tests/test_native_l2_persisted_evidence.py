from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from core.evaluator.native_l2_evidence_audit import (
    audit_native_l2_persisted_evidence,
)


def _make_root(tmp_path: Path, layers: int = 1) -> Path:
    root = tmp_path / f"evidence-{layers}"
    (root / "source").mkdir(parents=True)
    (root / "output").mkdir()
    for i in (1, 2, 3):
        (root / f"runs/run-{i}").mkdir(parents=True)

    source = b"authoritative-cad-or-stl-source"
    output = b"persisted-native-output"
    (root / "source/raw-source.bin").write_bytes(source)
    (root / "output/output.bin").write_bytes(output)
    for i in (1, 2, 3):
        (root / f"runs/run-{i}/output.bin").write_bytes(output)

    points = "0 0 0\n1 0 0\n0 1 0\n0 0.1 0\n1 0.1 0\n"
    triangles = "0 1 2\n"
    quads = ""
    cells = ""
    (root / "output/points.tsv").write_text(points)
    (root / "output/triangles.tsv").write_text(triangles)
    (root / "output/quads.tsv").write_text(quads)
    (root / "output/cells.tsv").write_text(cells)

    ledger = "face-0\tedge-0\tflat\twall\tfluid\tmain\tforward\t0,1,2\t0\n"
    (root / "ledger.tsv").write_text(ledger)
    binding = (
        "face-0\t\t\tedge-0\twall-0\tstrip-0\tout-0\tvol-0\tflat\twall"
        "\tfluid\tmain\tdirect\t0\t1\t3\t4\tface-0\tstrip-0\t90\n"
    )
    (root / "binding.tsv").write_text(binding)

    source_digest = sha256(source).hexdigest()
    output_digest = sha256(output).hexdigest()
    geometry_digest = sha256((points + triangles + quads + cells).encode()).hexdigest()
    lines = [
        "schema=native-l2-persisted-evidence/v1",
        "engine=native_tri",
        "source_path=source/raw-source.bin",
        "output_path=output/output.bin",
        "points_path=output/points.tsv",
        "triangles_path=output/triangles.tsv",
        "quads_path=output/quads.tsv",
        "cells_path=output/cells.tsv",
        "ledger_path=ledger.tsv",
        "binding_path=binding.tsv",
        f"source_sha256={source_digest}",
        f"output_sha256={output_digest}",
        f"geometry_sha256={geometry_digest}",
        "build_sha256=" + "b" * 64,
        "config_sha256=" + "c" * 64,
        "baseline_digest=" + ("a" * 64 if layers == 0 else "d" * 64),
        "candidate_digest=" + ("a" * 64 if layers == 0 else "e" * 64),
        f"requested_layers={layers}",
        f"actual_layers={layers}",
        f"bl0_exact_identity={'true' if layers == 0 else 'false'}",
        "total_thickness=0.1",
        "thickness_monotone=true",
        "growth_ratio_error=0.0",
        "run_output_1=runs/run-1/output.bin",
        "run_output_2=runs/run-2/output.bin",
        "run_output_3=runs/run-3/output.bin",
    ]
    (root / "evidence.atne").write_text("\n".join(lines) + "\n")
    return root


def test_persisted_path_only_bridge_recomputes_angle_and_bl_modes(tmp_path, monkeypatch):
    root = _make_root(tmp_path, 1)
    monkeypatch.setenv("AUTOTESSELL_EXT_BUILD_DIR", str(Path("auto_tessell_core/build").resolve()))
    result = audit_native_l2_persisted_evidence(str(root))
    assert result["accepted"] is True
    assert result["geometry_recomputed"] is True
    assert result["status"] == "native_l2_persisted_evidence_sealed"
    assert result["quality"]["wall_front_angle_source"] == "cxx_geometry_recomputed"
    assert result["quality"]["max_wall_front_orthogonality_degrees"] == 0
    assert result["quality"]["max_wall_front_out_of_plane_degrees"] == 0
    assert result["topology"]["duplicate"] == 0

    declared = (root / "binding.tsv").read_text()
    (root / "binding.tsv").write_text(declared.replace("\t90\n", "\t0\n"))
    again = audit_native_l2_persisted_evidence(str(root))
    assert again["accepted"] is True
    assert again["quality"]["max_wall_front_orthogonality_degrees"] == 0

    bl0 = _make_root(tmp_path, 0)
    result = audit_native_l2_persisted_evidence(str(bl0))
    assert result["accepted"] is True
    assert result["quality"]["wall_front_status"] == "not_applicable_bl0"


def test_persisted_path_only_bridge_rejects_raw_tamper_and_wrong_front(tmp_path):
    root = _make_root(tmp_path, 1)
    (root / "output/output.bin").write_bytes(b"tampered")
    result = audit_native_l2_persisted_evidence(str(root))
    assert result["reason"] == "persisted_raw_digest_mismatch"

    root = _make_root(tmp_path / "wrong", 1)
    row = (root / "binding.tsv").read_text()
    (root / "binding.tsv").write_text(row.replace("\t0\t1\t3\t4\t", "\t0\t1\t0\t3\t"))
    result = audit_native_l2_persisted_evidence(str(root))
    assert result["reason"] == "persisted_wall_front_quality_failed"

    missing = audit_native_l2_persisted_evidence(str(tmp_path / "missing"))
    assert missing["accepted"] is False
    assert missing["reason"] == "persisted_root_missing"
