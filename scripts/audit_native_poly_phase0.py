"""Print the current aspect-ratio gate outcome for synthetic BL stretching.

This is an accept/reject audit only.  It does not generate a mesh and does not
change the evaluator's pass/fail logic.  Katz's aligned BL evidence is shown
alongside the current gate so the calibration mismatch is explicit.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.evaluator.report import get_thresholds


def current_aspect_gate_accepts(aspect_ratio: float, quality_level: str) -> bool:
    """Mirror the existing report-only aspect criterion exactly."""
    threshold = float(get_thresholds(quality_level)["soft_aspect_ratio"])
    return float(aspect_ratio) <= threshold


def main() -> int:
    print("synthetic aligned BL-like stretched cells (accept/reject only)")
    print("Katz reference: aligned stretching up to AR=1e6 is solver-acceptable")
    for quality_level in ("draft", "standard", "fine"):
        threshold = float(get_thresholds(quality_level)["soft_aspect_ratio"])
        for aspect_ratio in (1.0, 1.0e2, 1.0e3, 1.0e6):
            outcome = (
                "ACCEPT" if current_aspect_gate_accepts(aspect_ratio, quality_level) else "REJECT"
            )
            print(
                f"quality={quality_level} aspect_ratio={aspect_ratio:.0e} "
                f"current_threshold={threshold:.0f} outcome={outcome}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
