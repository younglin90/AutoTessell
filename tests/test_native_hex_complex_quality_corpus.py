from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from core.analyzer.readers import read_stl
from core.evaluator.strict_volume_topology import audit_strict_volume_topology
from core.generator.native_hex.mesher import generate_native_hex

_FIXTURES = (
    ("sphere", Path("tests/benchmarks/sphere.stl"), None),
    ("naca", Path("tests/benchmarks/naca0012.stl"), None),
    ("gear", Path("tests/stl/04_extreme_gear.stl"), None),
)


def _artifact_hash(case_dir: Path) -> str:
    digest = hashlib.sha256()
    poly = case_dir / "constant" / "polyMesh"
    for path in sorted(poly.iterdir()):
        if path.is_file():
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


@pytest.mark.parametrize(("name", "source", "target"), _FIXTURES)
def test_native_hex_complex_quality_is_strict_and_repeatable(
    tmp_path: Path,
    name: str,
    source: Path,
    target: float | None,
) -> None:
    mesh = read_stl(source)
    hashes = []
    cell_counts = []
    for index in range(3):
        case_dir = tmp_path / f"{name}-{index}"
        result = generate_native_hex(
            mesh.vertices,
            mesh.faces,
            case_dir,
            target_edge_length=target,
            seed_density=10,
            snap_boundary=True,
            preserve_features=True,
            max_cells_per_axis=40,
        )
        assert result.success, result.message
        assert result.quality_grade in {"A", "B"}
        strict = audit_strict_volume_topology(case_dir)
        assert strict.valid, strict.as_dict()
        assert strict.n_duplicate_faces == 0
        assert strict.n_nonmanifold_faces == 0
        assert strict.n_nonmanifold_cell_edges == 0
        assert strict.n_open_cell_edges == 0
        assert strict.n_inverted_cells == 0
        hashes.append(_artifact_hash(case_dir))
        cell_counts.append(result.n_cells)
    assert hashes == [hashes[0]] * 3
    assert cell_counts == [cell_counts[0]] * 3
