"""Run the report-only POLY-FVERR-RANDPERT1 Laplacian MMS census."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.generator.native_poly.fv_mms import convergence_orders, run_laplacian_mms  # noqa: E402


def _run(perturb_fraction: float, seed: int, corrected: bool) -> None:
    results = run_laplacian_mms(
        (4, 8, 16),
        perturb_fraction=perturb_fraction,
        seed=seed,
        nonorthogonal_correction=corrected,
    )
    print(
        f"perturb_fraction={perturb_fraction:.6g} seed={seed} "
        f"nonorthogonal_correction={corrected}"
    )
    for result in results:
        print(
            f"n={result.n_axis} cells={result.n_cells} "
            f"non_ortho_deg={result.max_non_ortho_deg:.9g} "
            f"skew_proxy={result.max_skew_proxy:.9g} "
            f"l2={result.l2_error:.12g} linf={result.linf_error:.12g}"
        )
    print("l2_orders=" + ",".join(f"{value:.9g}" for value in convergence_orders(results)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--nonorthogonal-correction", action="store_true")
    args = parser.parse_args()
    for fraction in (0.0, 0.25):
        _run(fraction, args.seed, args.nonorthogonal_correction)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
