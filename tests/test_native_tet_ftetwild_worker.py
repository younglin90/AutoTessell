"""Vendored C++ fTetWild P4C worker regression."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest


def test_vendored_ftetwild_worker_returns_tets_without_host_teardown() -> None:
    build = Path(__file__).resolve().parents[1] / "auto_tessell_core" / "build"
    if not any(build.glob("ftetwild*.so")):
        pytest.skip("vendored ftetwild extension unavailable")
    assert importlib.util.find_spec("core.generator.native_tet.ftetwild_worker")
    from core.generator.native_tet.ftetwild_worker import tetrahedralize

    vertices = np.array([
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [1.0, 1.0, 1.0], [0.0, 1.0, 1.0],
    ])
    faces = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
        [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7],
    ], dtype=np.int64)

    points, tets = tetrahedralize(
        vertices, faces, edge_length_r=0.2, epsilon=1e-3,
        skip_simplify=False, stop_quality=10.0, max_threads=1, max_its=8,
    )
    assert points.ndim == 2 and points.shape[1] == 3
    assert tets.ndim == 2 and tets.shape[1] == 4
    assert len(tets) > 0


@pytest.mark.skipif(
    os.environ.get("AUTO_TESSELL_RUN_SLOW_E2E") != "1",
    reason="native P4C airfoil E2E is an explicit slow gate",
)
def test_native_tet_p4c_prefers_vendored_ftetwild_on_airfoil(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[1]
    script = """
import json
from pathlib import Path
import numpy as np
from core.analyzer.file_reader import load_mesh
from core.evaluator.native_checker import NativeMeshChecker
from core.generator.native_tet.hausdorff import hausdorff_vs_input
from core.generator.native_tet.mesher import generate_native_tet
from core.generator.native_tet.quality import snapshot
root = Path(__import__('sys').argv[1])
case = Path(__import__('sys').argv[2])
mesh = load_mesh(root / 'tests' / 'benchmarks' / 'naca0012.stl')
result = generate_native_tet(
    np.asarray(mesh.vertices, dtype=np.float64),
    np.asarray(mesh.faces, dtype=np.int64), case, target_cells=2000,
)
quality = snapshot(result.tet_points, result.tets)
checker = NativeMeshChecker().run(case)
fidelity = hausdorff_vs_input(
    np.asarray(mesh.vertices, dtype=np.float64),
    np.asarray(mesh.faces, dtype=np.int64),
    result.tet_points,
    result.tets,
    n_samples_per_tri=1,
)
diagonal = float(np.linalg.norm(np.ptp(mesh.vertices, axis=0)))
print('P4C_PAYLOAD ' + json.dumps({
    'success': result.success,
    'cells': result.n_cells,
    'mean_q': quality.mean_q,
    'max_aspect': quality.max_aspect,
    'negative_volumes': checker.negative_volumes,
    'max_skewness': checker.max_skewness,
    'max_non_orthogonality': checker.max_non_orthogonality,
    'hausdorff_relative': fidelity.h_symmetric / max(diagonal, 1e-30),
}))
"""
    env = os.environ.copy()
    env.update({
        "AUTO_TESSELL_CONVEX_EXTRUSION_RESCUE": "0",
        "AUTO_TESSELL_P4C_PYTETWILD": "1",
        "AUTO_TESSELL_P4C_VENDORED_FTETWILD": "1",
        "AUTO_TESSELL_P4C_WORKER_TIMEOUT_S": "60",
        "PYTHONPATH": str(root) + os.pathsep + env.get("PYTHONPATH", ""),
    })
    completed = subprocess.run(
        [sys.executable, "-c", script, str(root), str(tmp_path / "naca")],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-500:]
    lines = [line for line in completed.stdout.splitlines() if line.startswith("P4C_PAYLOAD ")]
    assert lines, completed.stdout[-500:]
    payload = json.loads(lines[-1].removeprefix("P4C_PAYLOAD "))
    assert payload["success"]
    # The surface-preserve selector rejects candidates below 50% of the
    # requested count; fTetWild ordering remains non-bit-stable above that.
    assert 1_000 <= payload["cells"] <= 4_000
    assert payload["mean_q"] >= 0.20
    assert payload["max_aspect"] < 50.0
    assert payload["negative_volumes"] == 0
    assert payload["max_skewness"] <= 3.0
    assert payload["max_non_orthogonality"] <= 65.0
    # The only finer epsilon schedules measured on this high-genus surface
    # produce non-manifold output and are rejected by the topology gate.
    # The valid fTetWild envelope is below 1.5% of the bounding diagonal.
    assert payload["hausdorff_relative"] <= 0.015


@pytest.mark.skipif(
    os.environ.get("AUTO_TESSELL_RUN_SLOW_E2E") != "1",
    reason="native P4C high-genus E2E is an explicit slow gate",
)
def test_native_tet_p4c_high_genus_surface_stays_closed_and_faithful(
    tmp_path: Path,
) -> None:
    """C++ P4C must keep the dual-torus boundary valid and CFD-usable."""
    root = Path(__file__).resolve().parents[1]
    script = """
import json
from pathlib import Path
import numpy as np
from core.analyzer.file_reader import load_mesh
from core.evaluator.native_checker import NativeMeshChecker
from core.generator.native_tet.hausdorff import hausdorff_vs_input
from core.generator.native_tet.mesher import generate_native_tet
from core.generator.native_tet.quality import snapshot
from core.generator.native_tet.rescue_gate import audit_tet_boundary
root = Path(__import__('sys').argv[1])
case = Path(__import__('sys').argv[2])
mesh = load_mesh(root / 'tests' / 'benchmarks' / 'high_genus_dual_torus.stl')
vertices = np.asarray(mesh.vertices, dtype=np.float64)
faces = np.asarray(mesh.faces, dtype=np.int64)
result = generate_native_tet(vertices, faces, case, target_cells=2000)
quality = snapshot(result.tet_points, result.tets)
checker = NativeMeshChecker().run(case)
fidelity = hausdorff_vs_input(vertices, faces, result.tet_points, result.tets, n_samples_per_tri=1)
audit = audit_tet_boundary(result.tet_points, result.tets)
diagonal = float(np.linalg.norm(np.ptp(vertices, axis=0)))
print('P4C_TORUS_PAYLOAD ' + json.dumps({
    'success': result.success,
    'cells': result.n_cells,
    'mean_q': quality.mean_q,
    'negative_volumes': checker.negative_volumes,
    'max_skewness': checker.max_skewness,
    'max_non_orthogonality': checker.max_non_orthogonality,
    'hausdorff_relative': fidelity.h_symmetric / max(diagonal, 1e-30),
    'topology_valid': audit.valid,
}))
"""
    env = os.environ.copy()
    env.update({
        "AUTO_TESSELL_CONVEX_EXTRUSION_RESCUE": "0",
        "AUTO_TESSELL_P4C_PYTETWILD": "1",
        "AUTO_TESSELL_P4C_VENDORED_FTETWILD": "1",
        "AUTO_TESSELL_P4C_WORKER_TIMEOUT_S": "60",
        "PYTHONPATH": str(root) + os.pathsep + env.get("PYTHONPATH", ""),
    })
    completed = subprocess.run(
        [sys.executable, "-c", script, str(root), str(tmp_path / "torus")],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=150,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-500:]
    lines = [
        line for line in completed.stdout.splitlines()
        if line.startswith("P4C_TORUS_PAYLOAD ")
    ]
    assert lines, completed.stdout[-500:]
    payload = json.loads(lines[-1].removeprefix("P4C_TORUS_PAYLOAD "))
    assert payload["success"]
    assert 600 <= payload["cells"] <= 4_000
    assert payload["mean_q"] >= 0.20
    assert payload["negative_volumes"] == 0
    assert payload["max_skewness"] <= 5.0
    assert payload["max_non_orthogonality"] <= 80.0
    assert payload["hausdorff_relative"] <= 0.01
    assert payload["topology_valid"]
