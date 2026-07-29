"""Apply the report-only FV MMS solver to one native-poly dual output."""

from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path
import sys

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.analyzer.readers import read_stl  # noqa: E402
from core.generator.native_poly.dual import tet_to_poly_dual  # noqa: E402
from core.generator.native_poly.fv_mms import solve_laplacian_mms  # noqa: E402
from core.generator.native_hex.metrics import read_written_polymesh_cells  # noqa: E402
from core.generator.native_tet.mesher import generate_native_tet  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--shape",
        choices=("cube", "sphere", "cylinder"),
        default="sphere",
    )
    parser.add_argument("--seed-density", type=int, default=8)
    parser.add_argument("--nonorthogonal-correction", action="store_true")
    args = parser.parse_args()

    stl = REPO / "tests" / "benchmarks" / f"{args.shape}.stl"
    mesh = read_stl(stl)
    with tempfile.TemporaryDirectory(prefix="native_poly_fv_mms_") as temp:
        root = Path(temp)
        started = time.perf_counter()
        primal = generate_native_tet(
            mesh.vertices,
            mesh.faces,
            root / "primal",
            seed_density=args.seed_density,
        )
        primal_seconds = time.perf_counter() - started
        if not primal.success or primal.tets is None or primal.tet_points is None:
            raise RuntimeError(f"native-tet primal failed: {primal}")

        started = time.perf_counter()
        dual = tet_to_poly_dual(
            np.asarray(primal.tet_points, dtype=np.float64),
            np.asarray(primal.tets, dtype=np.int64),
            root / "dual",
        )
        dual_seconds = time.perf_counter() - started
        if not dual.success:
            raise RuntimeError(f"native-poly dual failed: {dual.message}")

        reconstructed = read_written_polymesh_cells(root / "dual")
        if reconstructed is None:
            raise RuntimeError("could not reconstruct written polyMesh cells")
        points, cells = reconstructed
        started = time.perf_counter()
        try:
            mms = solve_laplacian_mms(
                points,
                cells,
                nonorthogonal_correction=args.nonorthogonal_correction,
            )
        except ValueError as exc:
            solve_seconds = time.perf_counter() - started
            print(f"shape={args.shape} seed_density={args.seed_density}")
            print(f"primal_seconds={primal_seconds:.9g} dual_seconds={dual_seconds:.9g}")
            print(f"cells={len(cells)} points={len(points)}")
            print(
                f"mms_seconds={solve_seconds:.9g} "
                f"nonorthogonal_correction={args.nonorthogonal_correction} "
                f"status=REJECT reason={exc}"
            )
            return 0
        solve_seconds = time.perf_counter() - started

    print(f"shape={args.shape} seed_density={args.seed_density}")
    print(f"primal_seconds={primal_seconds:.9g} dual_seconds={dual_seconds:.9g}")
    print(f"cells={len(cells)} points={len(points)}")
    print(
        f"mms_seconds={solve_seconds:.9g} "
        f"nonorthogonal_correction={args.nonorthogonal_correction} "
        f"non_ortho_deg={mms.max_non_ortho_deg:.9g} "
        f"skew_proxy={mms.max_skew_proxy:.9g} "
        f"l2={mms.l2_error:.12g} linf={mms.linf_error:.12g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
