from __future__ import annotations

import trimesh

from scripts.bench_native_tet_matrix import INCLUDE, REPO


def test_native_tet_matrix_only_contains_watertight_solids() -> None:
    for filename in INCLUDE:
        mesh = trimesh.load(REPO / "tests" / "benchmarks" / filename, force="mesh")
        assert mesh.is_watertight, filename
