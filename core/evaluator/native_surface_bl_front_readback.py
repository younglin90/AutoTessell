"""C++ readback verification for persisted actual XDE folded evidence."""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

from core.utils.native_extensions import import_native_extension


def _orchestration_fingerprint(producer: dict[str, Any]) -> str:
    value = 1469598103934665603
    for row in producer["points"]:
        for number in row:
            for byte in struct.pack("<d", float(number)):
                value ^= byte
                value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    for row in producer["triangles"]:
        for index in row:
            for byte in struct.pack("<q", int(index)):
                value ^= byte
                value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return f"{value:016x}"


def verify_actual_xde_folded_evidence(evidence_root: str | Path) -> dict[str, Any]:
    root = Path(evidence_root)
    evidence = root / "evidence.json"
    if not evidence.is_file():
        return {"accepted": False, "reason": "evidence_missing"}
    try:
        manifest = json.loads(evidence.read_text())
        kernel = import_native_extension("native_surface_bl_readback_verifier")
        result = dict(kernel.verify_persisted_folded_manifest(manifest))
        if result.get("accepted") is True:
            orchestration = _orchestration_fingerprint(manifest["producer"])
            result["orchestration_geometry_fingerprint"] = orchestration
            result["fingerprint_matches"] = orchestration == result.get("geometry_fingerprint")
            if not result["fingerprint_matches"]:
                result["accepted"] = False
                result["reason"] = "native_orchestration_fingerprint_mismatch"
        return result
    except Exception as exc:
        return {
            "accepted": False,
            "reason": f"readback_verifier_exception:{type(exc).__name__}:{exc}",
        }


__all__ = ["verify_actual_xde_folded_evidence"]
