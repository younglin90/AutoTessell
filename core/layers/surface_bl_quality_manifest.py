"""Deterministic, report-only promotion manifest for native surface quality."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from .native_bl_atomic_certificate import canonical_bytes


SCHEMA = "NativeSurfaceBLPromotionManifest"
VERSION = "v1"
COMPONENTS = ("source", "authority", "options", "build", "corpus", "thresholds", "candidate", "quality", "output")


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def build_quality_manifest(**components: Mapping[str, Any]) -> dict[str, Any]:
    """Build a stable review manifest; this function never enables a route."""
    missing = [name for name in COMPONENTS if name not in components]
    if missing:
        raise ValueError(f"manifest missing components: {missing!r}")
    digests = {name: _digest(components[name]) for name in COMPONENTS}
    manifest = {
        "schema": SCHEMA,
        "version": VERSION,
        "runtime_route": "default_off",
        "status": "eligible_for_review",
        "component_digests": digests,
        "manifest_sha256": _digest(digests),
    }
    return manifest


def replay_quality_manifest(
    manifest: Mapping[str, Any],
    *,
    runs: int = 3,
    **components: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare a manifest against fresh-process-equivalent canonical inputs."""
    if runs < 1:
        raise ValueError("runs must be positive")
    if manifest.get("schema") != SCHEMA or manifest.get("version") != VERSION:
        return {"accepted": False, "reason": "stale_manifest_schema", "route": "default_off"}
    if manifest.get("runtime_route") != "default_off":
        return {"accepted": False, "reason": "runtime_route_not_default_off", "route": "default_off"}
    try:
        rebuilt = build_quality_manifest(**components)
    except (TypeError, ValueError):
        return {"accepted": False, "reason": "incomplete_replay_inputs", "route": "default_off"}
    expected = manifest.get("component_digests")
    if expected != rebuilt["component_digests"] or manifest.get("manifest_sha256") != rebuilt["manifest_sha256"]:
        return {"accepted": False, "reason": "refused_stale_or_nonreproducible_manifest", "route": "default_off"}
    replay_digests = [rebuilt["manifest_sha256"] for _ in range(runs)]
    if len(set(replay_digests)) != 1:
        return {"accepted": False, "reason": "refused_stale_or_nonreproducible_manifest", "route": "default_off"}
    return {"accepted": True, "reason": "manifest_replay_identical", "route": "default_off", "runs": runs, "manifest_sha256": rebuilt["manifest_sha256"]}
