"""Native Poly quality/repeatability corpus on non-cube surfaces.

This is quality evidence only until source authority and feature/group binding are
measured by an independent certificate.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.evaluator.strict_volume_topology import audit_strict_volume_topology
from core.generator.native_poly.harness import run_native_poly_harness

_CASES = (
    ("sphere", Path("tests/benchmarks/sphere_watertight.stl")),
    ("cylinder", Path("tests/benchmarks/cylinder.stl")),
    ("duct", Path("tests/benchmarks/trimesh_duct.stl")),
)


def _manifest(case_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((case_dir / "constant" / "polyMesh").iterdir()):
        if path.is_file():
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


@pytest.mark.parametrize("name,source", _CASES, ids=[row[0] for row in _CASES])
def test_native_poly_complex_quality_corpus_is_strict_and_repeatable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    source: Path,
) -> None:
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    mesh = read_stl(source)
    hashes: list[str] = []
    cell_counts: list[int] = []
    for repeat in range(3):
        case_dir = tmp_path / f"{name}-{repeat}"
        result = run_native_poly_harness(
            np.asarray(mesh.vertices),
            np.asarray(mesh.faces),
            case_dir,
            seed_density=8,
            max_iter=1,
            max_tet_cells=15_000,
        )
        assert result.success, result.message
        strict = audit_strict_volume_topology(case_dir)
        assert strict.valid
        assert strict.n_duplicate_faces == 0
        assert strict.n_nonmanifold_faces == 0
        assert strict.n_nonmanifold_cell_edges == 0
        assert strict.n_open_cell_edges == 0
        assert strict.n_inverted_cells == 0
        hashes.append(_manifest(case_dir))
        cell_counts.append(result.final_poly_cells)
    assert hashes == [hashes[0]] * 3
    assert cell_counts == [cell_counts[0]] * 3
