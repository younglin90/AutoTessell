"""Report-only provenance census for the native_hex octree path.

The octree builder currently emits generic cell-face connectivity, not an
authoritative transition-template or source-patch record.  This module keeps
that distinction explicit: it summarizes the metadata observed inside the
builder and never infers missing provenance from the final mesh.
"""

from __future__ import annotations

import os
from collections import Counter
from typing import Mapping, Sequence


PROVENANCE_ENV = "AUTO_TESSELL_HEX_TRANSITION_PROVENANCE_DIAG"

MISSING_AUTHORITATIVE_FIELDS: tuple[str, ...] = (
    "octree leaf lineage and stable source-cell identity",
    "authoritative transition-chain ID and hanging-node valence per face",
    "published/emitted transition template identity per cell",
    "feature-edge/curve/corner provenance per affected cell",
    "authoritative boundary patch/source provenance per face",
)


def enabled() -> bool:
    """Return whether the opt-in, report-only census is enabled."""

    return os.environ.get(PROVENANCE_ENV, "").strip().lower() in {"1", "true", "yes"}


def summarize_transition_provenance(
    cell_metadata: Sequence[Mapping[str, object]],
    *,
    n_levels: int,
    n_feature_segments: int,
    n_feature_refined_cells: int,
) -> dict[str, object]:
    """Summarize builder-side labels without promoting them to provenance.

    ``grid_origin`` and ``target_level`` are deterministic observations of the
    current implementation.  They are not equivalent to a persistent octree
    leaf lineage, because the generic writer receives only final connectivity.
    """

    level_hist = Counter(int(item["target_level"]) for item in cell_metadata)
    template_hist = Counter(str(item["template_class"]) for item in cell_metadata)
    transition_hist = Counter(int(item["transition_face_count"]) for item in cell_metadata)
    unique_origins = {
        tuple(int(value) for value in item["grid_origin"])  # type: ignore[arg-type]
        for item in cell_metadata
    }
    n_transition_cells = sum(
        1 for item in cell_metadata if int(item["transition_face_count"]) > 0
    )
    return {
        "mode": "report-only",
        "n_levels": int(n_levels),
        "n_output_cells_at_builder": int(len(cell_metadata)),
        "n_cell_metadata": int(len(cell_metadata)),
        "n_unique_grid_origins": int(len(unique_origins)),
        "n_transition_cells": int(n_transition_cells),
        "n_transition_faces": int(
            sum(int(item["transition_face_count"]) for item in cell_metadata)
        ),
        "level_histogram": {str(key): int(value) for key, value in sorted(level_hist.items())},
        "template_class_histogram": {
            key: int(value) for key, value in sorted(template_hist.items())
        },
        "transition_face_histogram": {
            str(key): int(value) for key, value in sorted(transition_hist.items())
        },
        "n_feature_segments": int(n_feature_segments),
        "n_feature_refined_cells": int(n_feature_refined_cells),
        "metadata_scope": "grid-origin+target-level+derived-generic-transition-pattern",
        "authoritative_provenance": False,
        "missing_authoritative_fields": list(MISSING_AUTHORITATIVE_FIELDS),
    }
