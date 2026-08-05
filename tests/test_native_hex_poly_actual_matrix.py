from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.evaluator.native_hex_poly_actual_matrix import (
    audit_actual_native_hex_poly_case,
    validate_actual_native_hex_poly_matrix,
)

_POINTS = """8
(
(0 0 0)
(1 0 0)
(1 1 0)
(0 1 0)
(0 0 1)
(1 0 1)
(1 1 1)
(0 1 1)
)
"""
_FACES = """6
(
4(0 3 2 1)
4(4 5 6 7)
4(0 1 5 4)
4(1 2 6 5)
4(2 3 7 6)
4(3 0 4 7)
)
"""
_OWNER = """6
(
0
0
0
0
0
0
)
"""
_NEIGHBOUR = """0
(
)
"""


def _write_cube(case_dir: Path) -> None:
    mesh = case_dir / "constant" / "polyMesh"
    mesh.mkdir(parents=True)
    for name, text in {
        "points": _POINTS,
        "faces": _FACES,
        "owner": _OWNER,
        "neighbour": _NEIGHBOUR,
        "boundary": "1\n(\nwall\n{\n type wall;\n nFaces 6;\n startFace 0;\n}\n)\n",
    }.items():
        (mesh / name).write_text(text, encoding="utf-8")


def _source(path: Path) -> tuple[Path, str]:
    path.write_bytes(b"authoritative source")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _authority(source_sha: str) -> dict[str, object]:
    return {
        "authority_ready": True,
        "source_sha256": source_sha,
        "mapping_sha256": "a" * 64,
        "canonical_geometry_sha256": "b" * 64,
        "mapping_complete": True,
    }


def _add_witness(case_dir: Path, source_sha: str, artifact_sha: str) -> None:
    (case_dir / "native_quality_witness.json").write_text(
        json.dumps(
            {
                "schema": "autotessell/native-quality-witness/v1",
                "implementation": "cpp",
                "digest": "c" * 64,
                "source_sha256": source_sha,
                "output_artifact_sha256": artifact_sha,
                "metrics": {
                    "p95_non_ortho_deg": 10.0,
                    "p99_non_ortho_deg": 12.0,
                    "max_non_ortho_deg": 15.0,
                    "p95_skewness": 0.1,
                    "p99_skewness": 0.2,
                    "max_skewness": 0.3,
                    "p95_aspect_ratio": 2.0,
                    "p99_aspect_ratio": 2.5,
                    "max_aspect_ratio": 3.0,
                    "worst_uid": 7,
                    "mapping_coverage": True,
                },
            }
        ),
        encoding="utf-8",
    )


def test_bl0_authoritative_case_is_accepted_only_with_real_witness_and_baseline(
    tmp_path: Path,
) -> None:
    case = tmp_path / "run"
    baseline = tmp_path / "baseline"
    _write_cube(case)
    _write_cube(baseline)
    source_path, source_sha = _source(tmp_path / "cube.stl")
    (case / "native_bl_state.json").write_text(
        json.dumps({"requested_layers": 0, "actual_layers": 0, "state": "disabled_identity"}),
        encoding="utf-8",
    )
    audit0 = audit_actual_native_hex_poly_case(
        case,
        engine="hex",
        source_path=source_path,
        requested_layers=0,
        baseline_case_dir=baseline,
        cad_authority=_authority(source_sha),
    )
    _add_witness(case, source_sha, audit0.artifact_sha256)
    result = audit_actual_native_hex_poly_case(
        case,
        engine="hex",
        source_path=source_path,
        requested_layers=0,
        baseline_case_dir=baseline,
        cad_authority=_authority(source_sha),
    )
    assert result.accepted is True
    assert result.status == "ACCEPTED"


def test_synthetic_or_missing_authority_is_unverified(tmp_path: Path) -> None:
    case = tmp_path / "run"
    _write_cube(case)
    source_path, _ = _source(tmp_path / "cube.stl")
    (case / "native_bl_state.json").write_text(
        json.dumps({"requested_layers": 0, "actual_layers": 0, "state": "disabled_identity"}),
        encoding="utf-8",
    )
    result = audit_actual_native_hex_poly_case(
        case,
        engine="poly",
        source_path=source_path,
        requested_layers=0,
        baseline_case_dir=case,
        cad_authority=None,
    )
    assert result.accepted is False
    assert result.status == "UNVERIFIED"
    assert "source_authority_mapping_missing" in result.reasons
    assert "quality_cpp_witness_missing" not in result.reasons
    assert result.quality["cpp"] is True
    assert result.quality["witness_source"] == "on_readback_cpp"


def test_positive_bl_quality_failure_is_refused(tmp_path: Path) -> None:
    case = tmp_path / "run"
    _write_cube(case)
    source_path, source_sha = _source(tmp_path / "cube.stl")
    (case / "native_bl_state.json").write_text(
        json.dumps({"requested_layers": 1, "actual_layers": 1, "state": "completed"}),
        encoding="utf-8",
    )
    (case / "native_bl_quality.json").write_text(
        json.dumps(
            {
                "total_thickness": 0.1,
                "n_prism_cells": 1,
                "wall_preserve": {"within_envelope": True},
                "bad_internal_faces": {"n_bad_faces": 4},
            }
        ),
        encoding="utf-8",
    )
    result = audit_actual_native_hex_poly_case(
        case,
        engine="poly",
        source_path=source_path,
        requested_layers=1,
        cad_authority=_authority(source_sha),
    )
    assert result.accepted is False
    assert result.status == "REFUSED"
    assert "bl_quality_failure" in result.reasons


def test_matrix_requires_three_identical_accepted_runs(tmp_path: Path) -> None:
    rows = [
        {
            "case_id": "cube",
            "accepted": True,
            "artifact_sha256": "d" * 64,
            "authority": {"authority_ready": True},
        }
        for _ in range(3)
    ]
    result = validate_actual_native_hex_poly_matrix(rows)
    assert result["accepted"] is True
    result = validate_actual_native_hex_poly_matrix(rows[:2])
    assert result["accepted"] is False
    assert "cube:nondeterministic_or_less_than_three_runs" in result["reasons"]
