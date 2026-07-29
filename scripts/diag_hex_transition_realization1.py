"""HEX-OCT-ADAPTIVE-TRANSITION-REALIZATION-DIAG1.

Feed a deliberately mixed target-level grid directly to the existing octree
cell builder.  This is a report-only diagnostic: it does not change the
builder and treats an absent mixed-level output as a measured finding.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.generator.native_hex.octree import _build_nlevel_cells  # noqa: E402
from core.generator.native_hex.sheet_diagnostic import _face_records  # noqa: E402
from core.generator.native_hex.transition_provenance import (  # noqa: E402
    summarize_transition_provenance,
)
from core.generator.native_hex.transition_quality import (  # noqa: E402
    audit_transition_quality,
)


def run_diagnostic() -> dict[str, object]:
    """Return the deterministic mixed-level input/output census."""

    nfx = nfy = nfz = 4
    n_levels = 2
    inside = np.ones((nfx, nfy, nfz), dtype=bool)
    requested_levels = np.full((nfx, nfy, nfz), 2, dtype=np.int8)
    requested_levels[:2, :2, :2] = 1
    metadata: list[dict[str, object]] = []
    points = np.asarray(
        [
            [float(i), float(j), float(k)]
            for i in range(nfx + 1)
            for j in range(nfy + 1)
            for k in range(nfz + 1)
        ],
        dtype=np.float64,
    )
    previous_flag = os.environ.get("AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION")
    os.environ["AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION"] = "1"
    try:
        cells = _build_nlevel_cells(
            points,
            inside,
            requested_levels,
            n_levels,
            nfx,
            nfy,
            nfz,
            nfy + 1,
            nfz + 1,
            cell_metadata=metadata,
        )
    finally:
        if previous_flag is None:
            os.environ.pop("AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION", None)
        else:
            os.environ["AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION"] = previous_flag
    summary = summarize_transition_provenance(
        metadata,
        n_levels=n_levels,
        n_feature_segments=0,
        n_feature_refined_cells=0,
    )
    quality = audit_transition_quality(
        points,
        cells,
        cell_metadata=metadata,
    )
    requested_histogram = {
        str(level): int(np.count_nonzero(requested_levels == level))
        for level in sorted(set(int(value) for value in requested_levels.flat))
    }
    records = _face_records(cells)
    incidence_histogram = dict(
        sorted(Counter(len(owners) for _face, (_cyclic, owners) in records.items()).items())
    )
    coarse_cell_indices = [
        index for index, item in enumerate(metadata) if int(item["target_level"]) == 1
    ]
    coarse_cell_index = coarse_cell_indices[0] if len(coarse_cell_indices) == 1 else -1
    interface_face_count = sum(
        1
        for _face, (_cyclic, owners) in records.items()
        if coarse_cell_index in owners and len(owners) == 2
    )
    return {
        "card": "HEX-OCT-ADAPTIVE-TRANSITION-REALIZATION-DIAG1",
        "mode": "report-only",
        "requested_level_histogram": requested_histogram,
        "requested_mixed_levels": bool(len(requested_histogram) > 1),
        "observed_builder_cells": len(cells),
        "face_incidence_histogram": {
            str(key): int(value) for key, value in incidence_histogram.items()
        },
        "boundary_face_count": int(
            incidence_histogram.get(1, 0)
        ),
        "coarse_to_fine_interface_faces": int(interface_face_count),
        "observed": summary,
        "quality": quality.to_dict(),
        "realization": (
            "observed"
            if int(summary["n_transition_cells"]) > 0
            else "not_observed"
        ),
        "interpretation": (
            "The existing builder did not realize the mixed-level request: "
            "all output cells were fine-level and no transition faces were emitted."
            if int(summary["n_transition_cells"]) == 0
            else "A mixed-level transition pattern was emitted; proceed to quality census."
        ),
    }


def main() -> int:
    print(json.dumps(run_diagnostic(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
