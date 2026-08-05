"""Python orchestration for the bounded C++ actual-v2 folded-plate route."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np

from core.utils.native_extensions import import_native_extension


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=list).encode()).hexdigest()


def produce_folded_plate_evidence(
    target_root: str | Path,
    positions: Any,
    source_triangles: Any,
    ridge_endpoints: Any,
    normals: Any,
    semantic_rows: list[dict[str, Any]],
    *,
    requested_layers: int,
    first_height: float,
    growth_ratio: float,
    strict_quality: bool = True,
) -> dict[str, Any]:
    target = Path(target_root)
    if target.exists():
        return {"accepted": False, "reason": "target_exists", "candidate_discarded": True, "atomic_rollback": True}
    temp = target.parent / f".{target.name}.folded-plate-tmp"
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True, exist_ok=True)
    try:
        kernel = import_native_extension("native_surface_bl_folded_plate")
        args = (
            np.ascontiguousarray(np.asarray(positions, dtype=np.float64)),
            np.ascontiguousarray(np.asarray(source_triangles, dtype=np.int64)),
            np.ascontiguousarray(np.asarray(ridge_endpoints, dtype=np.int64)),
            np.ascontiguousarray(np.asarray(normals, dtype=np.float64)),
            [dict(row) for row in semantic_rows], int(requested_layers),
            float(first_height), float(growth_ratio), bool(strict_quality),
        )
        runs = [dict(kernel.produce_actual_v2_folded_plate_ridge_v1(*args)) for _ in range(3)]
        if any(not row.get("accepted") for row in runs):
            return {"accepted": False, "reason": "producer_refused", "runs": runs, "candidate_discarded": True, "atomic_rollback": True}
        digests = [_digest(row) for row in runs]
        if len(set(digests)) != 1:
            raise ValueError("producer_repeatability_mismatch")
        manifest = {
            "schema": "native-surface-actual-v2-folded-plate/v1",
            "source_geometry_sha256": _digest(np.asarray(positions, dtype=np.float64).tolist()),
            "source_triangles_sha256": _digest(np.asarray(source_triangles, dtype=np.int64).tolist()),
            "semantic_map_sha256": _digest(semantic_rows),
            "requested_layers": int(requested_layers),
            "actual_layers": int(runs[0]["actual_layers"]),
            "producer_digest": digests[0],
            "producer": runs[0],
            "runs": digests,
            "authority_level": "L0_bounded_folded_plate",
            "publication_eligible": False,
        }
        (temp / "evidence.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
        (temp / "lineage.json").write_text(json.dumps(runs[0]["provenance"], indent=2, sort_keys=True))
        temp.replace(target)
        return {"accepted": True, "status": "folded_plate_evidence_written", "evidence_root": str(target), "producer": runs[0], "run_digests": digests, "publication_eligible": False, "atomic_rollback": False}
    except Exception as exc:
        if temp.exists():
            shutil.rmtree(temp)
        return {"accepted": False, "reason": f"folded_plate_exception:{type(exc).__name__}:{exc}", "candidate_discarded": True, "atomic_rollback": True}


__all__ = ["produce_folded_plate_evidence"]
