"""Native Tet actual strict release corpus and same-side transaction evidence."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from core.analyzer.readers import read_stl
from core.evaluator.strict_volume_topology import audit_strict_volume_topology
from core.evaluator.native_tet_release_evidence import certify_native_tet_release_output
from core.generator.native_tet.mesher import generate_native_tet

_CASES = (
    ("cube", Path("tests/benchmarks/cube.stl"), 4),
    ("sphere", Path("tests/benchmarks/sphere_watertight.stl"), 6),
    ("naca", Path("tests/benchmarks/naca0012.stl"), 6),
    ("complex-duct", Path("tests/benchmarks/trimesh_duct.stl"), 6),
)


def _manifest(case_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((case_dir / "constant" / "polyMesh").iterdir()):
        if path.is_file():
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


@pytest.mark.parametrize("name,source,seed_density", _CASES, ids=[row[0] for row in _CASES])
def test_native_tet_release_corpus_strict_and_repeatable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    source: Path,
    seed_density: int,
) -> None:
    monkeypatch.setenv("AUTO_TESSELL_P4C_PYTETWILD", "0")
    mesh = read_stl(source)
    hashes: list[str] = []
    for repeat in range(3):
        case_dir = tmp_path / f"{name}-{repeat}"
        result = generate_native_tet(
            np.asarray(mesh.vertices),
            np.asarray(mesh.faces),
            case_dir,
            seed_density=seed_density,
            sliver_quality_threshold=0.0,
            enable_same_side_retriangulation=True,
            enable_phase_a=False,
            recovery_iterations=0,
            smooth_iterations=0,
        )
        assert result.success, result.message
        transaction = (result.debug_info or {}).get("same_side_retriangulation_transaction")
        assert isinstance(transaction, dict)
        assert transaction.get("exact_rollback") is True or transaction.get("accepted") is True
        strict = audit_strict_volume_topology(case_dir)
        assert strict.valid
        face_count = len(mesh.faces)
        certificate = certify_native_tet_release_output(
            case_dir,
            source,
            mesh.vertices,
            mesh.faces,
            result.tet_points,
            result.tets,
            source_feature_ids=("none",) * face_count,
            source_patch_ids=("wall",) * face_count,
            source_physical_groups=("wall",) * face_count,
            debug_info=result.debug_info,
        )
        assert certificate.authoritative, certificate.as_dict()
        assert strict.n_duplicate_faces == 0
        assert strict.n_nonmanifold_faces == 0
        assert strict.n_nonmanifold_cell_edges == 0
        assert strict.n_open_cell_edges == 0
        assert strict.n_inverted_cells == 0
        assert strict.min_cell_volume is not None and strict.min_cell_volume > 0.0
        hashes.append(_manifest(case_dir))
    assert hashes == [hashes[0]] * 3
