"""The evidence collector must keep an empty campaign unverified."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from scripts.collect_native_release_evidence import surface_audit
from core.evaluator.native_release_matrix import REQUIRED_RELEASE_CASES


def test_empty_spec_is_not_promoted(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    manifest = tmp_path / "manifest.json"
    report = tmp_path / "report.json"
    spec.write_text(
        json.dumps({"schema": "autotessell/native-release-evidence-spec/v1", "cases": []})
    )
    result = subprocess.run(
        [
            sys.executable,
            "scripts/collect_native_release_evidence.py",
            str(spec),
            "--output",
            str(manifest),
            "--authority-evidence",
            str(report),
        ],
        check=False,
    )
    value = json.loads(report.read_text())
    assert result.returncode == 1
    assert value["status"] == "matrix_unverified"
    assert len(value["matrix"]["missing_cases"]) == len(REQUIRED_RELEASE_CASES)


def test_surface_artifact_is_audited_as_surface_not_openfoam_volume(tmp_path: Path) -> None:
    vertices = np.asarray(
        ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)),
        dtype=np.float64,
    )
    quads = np.asarray(
        ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (3, 7, 6, 2), (0, 4, 7, 3), (1, 2, 6, 5)),
        dtype=np.int64,
    )
    np.save(tmp_path / "vertices.npy", vertices, allow_pickle=False)
    np.save(tmp_path / "quads.npy", quads, allow_pickle=False)
    audit = surface_audit(tmp_path)
    assert audit["kind"] == "surface"
    assert audit["valid"] is True
    assert audit["n_open_edges"] == 0
