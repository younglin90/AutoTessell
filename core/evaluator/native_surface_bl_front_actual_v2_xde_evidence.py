"""Actual STEPCAF/XDE folded-plate authority and readback evidence bridge."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np

from core.analyzer.readers.step import load_cad_native_with_provenance
from core.generator.native_surface_xde_folded_ledger import build_explicit_xde_folded_profile
from core.evaluator.native_surface_bl_front_readback import verify_actual_xde_folded_evidence
from core.utils.native_extensions import import_native_extension


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=list).encode()
    ).hexdigest()


def _refused(reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "accepted": False,
        "reason": reason,
        "candidate_discarded": True,
        "atomic_rollback": True,
        **extra,
    }


def write_actual_xde_folded_evidence(
    target_root: str | Path,
    source_path: str | Path,
    *,
    requested_layers: int,
    first_height: float = 0.2,
    growth_ratio: float = 1.2,
    strict_quality: bool = True,
) -> dict[str, Any]:
    target = Path(target_root)
    source = Path(source_path)
    if target.exists():
        return _refused("target_exists")
    if requested_layers < 0:
        return _refused("negative_layer_count")
    temp = target.parent / f".{target.name}.actual-xde-folded-tmp"
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True, exist_ok=True)
    try:
        raw = source.read_bytes()
        source_sha256 = hashlib.sha256(raw).hexdigest()
        cad = load_cad_native_with_provenance(source, source.suffix.lower())
        profile = build_explicit_xde_folded_profile(cad)
        if profile.get("accepted") is not True:
            return _refused("authority_refused", profile=profile)
        positions = np.ascontiguousarray(np.asarray(profile["canonical_positions"], dtype=np.float64))
        triangles = np.ascontiguousarray(np.asarray(profile["canonical_triangles"], dtype=np.int64))
        ridge = np.ascontiguousarray(np.asarray(profile["ridge_endpoints"], dtype=np.int64))
        normals = np.ascontiguousarray(np.asarray(profile["normals"], dtype=np.float64))
        semantic_rows = [dict(row) for row in profile["semantic_rows"]]
        kernel = import_native_extension("native_surface_bl_folded_plate")

        def run(layers: int) -> dict[str, Any]:
            return dict(
                kernel.produce_actual_v2_folded_plate_ridge_v1(
                    positions, triangles, ridge, normals, semantic_rows,
                    int(layers), float(first_height), float(growth_ratio),
                    bool(strict_quality),
                )
            )

        baseline = run(0)
        if baseline.get("accepted") is not True:
            return _refused("baseline_refused", baseline=baseline)
        runs = [run(requested_layers) for _ in range(3)]
        if any(item.get("accepted") is not True for item in runs):
            return _refused("producer_refused", runs=runs)
        run_digests = [_digest(item) for item in runs]
        if len(set(run_digests)) != 1:
            return _refused("producer_repeatability_mismatch", run_digests=run_digests)
        if requested_layers == 0:
            output_points = [list(row) for row in runs[0]["points"]]
            output_triangles = [list(row) for row in runs[0]["triangles"]]
            if output_points != profile["canonical_positions"] or output_triangles != profile["canonical_triangles"]:
                return _refused("bl0_source_identity_mismatch", runs=runs)
        (temp / "source").mkdir()
        (temp / "source" / source.name).write_bytes(raw)
        (temp / "source_ledger.json").write_text(json.dumps(profile, indent=2, sort_keys=True))
        (temp / "lineage.json").write_text(json.dumps(runs[0]["provenance"], indent=2, sort_keys=True))
        manifest = {
            "schema": "native-surface-actual-xde-folded-evidence/v1",
            "engine": "native_surface",
            "authority_level": "L1_actual_stepcaf_xde_two_face_folded",
            "source_sha256": source_sha256,
            "source_profile": profile,
            "requested_layers": int(requested_layers),
            "actual_layers": int(runs[0]["actual_layers"]),
            "baseline_digest": _digest(baseline),
            "run_digests": run_digests,
            "producer": runs[0],
            "publication_eligible": False,
        }
        (temp / "evidence.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
        readback = json.loads((temp / "evidence.json").read_text())
        readback_digest = _digest(readback["producer"])
        if readback_digest != run_digests[0]:
            shutil.rmtree(temp)
            return _refused("readback_digest_mismatch", readback_digest=readback_digest, run_digests=run_digests)
        native_receipt = verify_actual_xde_folded_evidence(temp)
        if native_receipt.get("accepted") is not True:
            shutil.rmtree(temp)
            return _refused("native_readback_refused", native_receipt=native_receipt)
        readback["native_geometry_fingerprint"] = native_receipt["geometry_fingerprint"]
        readback["orchestration_geometry_fingerprint"] = native_receipt["orchestration_geometry_fingerprint"]
        readback["fingerprint_matches"] = native_receipt["fingerprint_matches"]
        (temp / "evidence.json").write_text(json.dumps(readback, indent=2, sort_keys=True))
        native_receipt = verify_actual_xde_folded_evidence(temp)
        if native_receipt.get("accepted") is not True:
            shutil.rmtree(temp)
            return _refused("native_readback_persisted_fingerprint_refused", native_receipt=native_receipt)
        readback_receipt = {
            "schema": "native-surface-actual-xde-folded-readback/v2",
            "evidence_digest": _digest(readback),
            "producer_digest": readback_digest,
            "run_digest": run_digests[0],
            "native_geometry_fingerprint": native_receipt["geometry_fingerprint"],
            "orchestration_geometry_fingerprint": native_receipt["orchestration_geometry_fingerprint"],
            "fingerprint_matches": native_receipt["fingerprint_matches"],
            "native_topology": native_receipt["recomputed_topology"],
            "matches": True,
        }
        (temp / "readback.json").write_text(json.dumps(readback_receipt, indent=2, sort_keys=True))
        temp.replace(target)
        return {
            "accepted": True,
            "status": "actual_xde_folded_evidence_written",
            "evidence_root": str(target),
            "authority_level": "L1_actual_stepcaf_xde_two_face_folded",
            "producer": runs[0],
            "baseline": baseline,
            "run_digests": run_digests,
            "readback": readback_receipt,
            "publication_eligible": False,
            "atomic_rollback": False,
        }
    except Exception as exc:
        if temp.exists():
            shutil.rmtree(temp)
        return _refused(f"actual_xde_folded_exception:{type(exc).__name__}:{exc}")


__all__ = ["write_actual_xde_folded_evidence"]
