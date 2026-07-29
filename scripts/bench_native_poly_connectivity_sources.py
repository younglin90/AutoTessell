"""Locate when incomplete interior tet edge links appear.

Diagnostic only.  Runs the same fixed STL/seed protocol with native-tet Phase A
disabled and enabled, then reuses the topology map and audit-only counters.
No production connectivity is changed.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("AUTO_TESSELL_P4C_PYTETWILD", "0")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.analyzer.readers import read_stl  # noqa: E402
from core.generator.native_tet.mesher import generate_native_tet  # noqa: E402
from bench_native_poly_topology_map import _map  # noqa: E402


def main() -> None:
    rows: dict[str, object] = {}
    for shape in ("cube", "cylinder", "sphere"):
        mesh = read_stl(ROOT / "tests" / "benchmarks" / f"{shape}.stl")
        shape_rows: dict[str, object] = {}
        modes = (
            ("recovery_off_phase_a_off", False, 0),
            ("recovery_on_phase_a_off", False, 2),
            ("recovery_on_phase_a_on", True, 2),
        )
        for mode, phase_a, recovery_iterations in modes:
            with tempfile.TemporaryDirectory(prefix="native_poly_connectivity_") as temp:
                result = generate_native_tet(
                    mesh.vertices,
                    mesh.faces,
                    Path(temp) / shape,
                    seed_density=6,
                    enable_phase_a=phase_a,
                    recovery_iterations=recovery_iterations,
                    enable_phase_b=False,
                    enable_bsp_insertion=False,
                    enable_edge_recovery=False,
                )
            if not result.success or result.tet_points is None or result.tets is None:
                shape_rows[mode] = {"success": False, "message": result.message}
                continue
            mapped = _map(result.tet_points, result.tets)
            audit = mapped["native_tet_audit"]
            shape_rows[mode] = {
                "success": True,
                "points": mapped["points"],
                "tets": mapped["tets"],
                "internal_rings_lt3": mapped["internal_rings_lt3"],
                "orphan_vertices": len(mapped["orphan_vertices"]),
                "native_tet_audit": audit,
            }
        rows[shape] = shape_rows
    print(json.dumps(rows, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
