"""Default-off admission and profiling for fresh Native Poly BL candidates.

This module deliberately does not run or mutate the Poly generator.  It is a
read-only gate around a private stage: missing producer evidence is rejected
before an expensive BL run can be treated as a candidate.  Python is used only
for orchestration/evidence; measured geometry or topology hotspots remain C++
work for a later card.
"""

from __future__ import annotations

import hashlib
import json
import resource
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from core.evaluator.native_artifact_tree import fingerprint_staged_artifact_tree

REQUIRED_LINEAGE_DIGESTS = (
    "source_sha256",
    "candidate_source_sha256",
    "wall_edge_layer_sha256",
    "source_face_preservation_sha256",
    "outer_front_sha256",
)
REQUIRED_PARTITIONS = ("core", "boundary_layer", "transition")
_HEX = frozenset("0123456789abcdef")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_profile_sha256(value: Mapping[str, Any]) -> str:
    """Hash a profile without allowing its own digest field to be recursive."""
    payload = dict(value)
    payload.pop("profile_sha256", None)
    return _sha256(_canonical_json(payload))


def _rss_kb() -> int:
    """Return a platform-neutral best-effort peak RSS observation."""
    try:
        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (AttributeError, OSError, ValueError):
        return 0
    # Linux reports KiB; macOS reports bytes.  WSL/Linux is the release host,
    # but retaining the fallback makes the sidecar schema portable.
    return value if value < 10**9 else value // 1024


def _read_json(path: Path) -> Mapping[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _load_provenance(
    stage: Path, supplied: Mapping[str, Any] | None
) -> Mapping[str, Any] | None:
    if supplied is not None:
        return supplied
    return _read_json(stage / "native_bl_provenance.v2.json") or _read_json(
        stage / "native_bl_provenance.json"
    )


def _load_partitions(
    stage: Path, supplied: Mapping[str, Any] | Sequence[str] | None
) -> Mapping[str, Any] | None:
    if supplied is None:
        supplied = _read_json(stage / "native_cell_partitions.v2.json") or _read_json(
            stage / "native_cell_partitions.json"
        )
        if supplied is None:
            return None
    if isinstance(supplied, Mapping):
        if isinstance(supplied.get("cell_ids"), Mapping):
            cell_ids = supplied["cell_ids"]
            if set(cell_ids) != set(REQUIRED_PARTITIONS):
                return None
            return {
                "counts": {name: len(cell_ids[name]) for name in REQUIRED_PARTITIONS},
                "cell_ids": {name: list(cell_ids[name]) for name in REQUIRED_PARTITIONS},
                "final_cell_ids": list(supplied.get("final_cell_ids", [])),
                "transition_not_applicable": supplied.get("transition_not_applicable") is True,
            }
        return supplied
    if isinstance(supplied, (str, bytes)):
        return None
    counts = {name: 0 for name in REQUIRED_PARTITIONS}
    for name in supplied:
        if name not in counts:
            return None
        counts[name] += 1
    return {"counts": counts, "transition_not_applicable": counts["transition"] == 0}


def _validate_lineage(value: Mapping[str, Any] | None) -> str | None:
    if value is None:
        return "bl_lineage_missing"
    if value.get("lineage_complete") is not True:
        return "bl_lineage_incomplete"
    for name in REQUIRED_LINEAGE_DIGESTS:
        if not _is_digest(value.get(name)):
            return f"lineage_digest_missing:{name}"
    mapping = value.get("producer_mapping_sha256")
    if not _is_digest(mapping):
        return "lineage_digest_missing:producer_mapping_sha256"
    return None


def _validate_partitions(value: Mapping[str, Any] | None) -> str | None:
    if value is None:
        return "partition_missing"
    counts = value.get("counts")
    if not isinstance(counts, Mapping) or set(counts) != set(REQUIRED_PARTITIONS):
        return "partition_incomplete"
    for name in REQUIRED_PARTITIONS:
        number = counts.get(name)
        if isinstance(number, bool) or not isinstance(number, int) or number < 0:
            return f"partition_count_invalid:{name}"
    explicit = value.get("cell_ids")
    final_ids = value.get("final_cell_ids")
    if explicit is not None:
        if not isinstance(explicit, Mapping) or set(explicit) != set(REQUIRED_PARTITIONS):
            return "partition_explicit_ids_invalid"
        seen: set[int] = set()
        for name in REQUIRED_PARTITIONS:
            ids = explicit[name]
            if (
                not isinstance(ids, list)
                or any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in ids)
                or len(ids) != len(set(ids))
                or seen.intersection(ids)
            ):
                return "partition_explicit_ids_overlap_or_invalid"
            if len(ids) != counts[name]:
                return f"partition_count_id_mismatch:{name}"
            seen.update(ids)
        if not isinstance(final_ids, list) or set(final_ids) != seen:
            return "partition_explicit_coverage_mismatch"
    if counts["boundary_layer"] <= 0:
        return "partition_boundary_layer_empty"
    if counts["transition"] == 0 and value.get("transition_not_applicable") is not True:
        return "partition_transition_empty_without_certificate"
    return None


def _validate_fixed_digest(name: str, value: Any) -> str | None:
    return None if _is_digest(value) else f"fixed_digest_missing:{name}"


def _accepted(value: Any) -> bool:
    if isinstance(value, Mapping):
        return value.get("accepted") is True or value.get("valid") is True
    return bool(getattr(value, "accepted", False) or getattr(value, "valid", False))


@dataclass
class _ProfileState:
    stage_timings: dict[str, float] = field(default_factory=dict)
    stage_results: dict[str, Any] = field(default_factory=dict)
    collision_counters: dict[str, int] = field(default_factory=dict)
    peak_rss_kb: int = 0

    def run(self, name: str, callback: Callable[[], Any]) -> Any:
        started = time.perf_counter()
        try:
            result = callback()
        except TimeoutError as error:
            self.stage_timings[name] = time.perf_counter() - started
            self.stage_results[name] = {"status": "TIMEOUT", "error": str(error)}
            self.peak_rss_kb = max(self.peak_rss_kb, _rss_kb())
            raise
        except Exception as error:  # noqa: BLE001
            self.stage_timings[name] = time.perf_counter() - started
            self.stage_results[name] = {
                "status": "ERROR",
                "error": f"{type(error).__name__}: {error}",
            }
            self.peak_rss_kb = max(self.peak_rss_kb, _rss_kb())
            raise
        self.stage_timings[name] = time.perf_counter() - started
        self.stage_results[name] = result
        self.peak_rss_kb = max(self.peak_rss_kb, _rss_kb())
        if isinstance(result, Mapping):
            counters = result.get("collision_counters")
            if isinstance(counters, Mapping):
                for key in ("rays", "triangles", "candidates", "max_candidates"):
                    number = counters.get(key)
                    if isinstance(number, int) and not isinstance(number, bool) and number >= 0:
                        self.collision_counters[key] = number
        return result


def profile_poly_bl_stage(
    stage_dir: str | Path,
    *,
    requested_layers: int,
    actual_layers: int | None = None,
    baseline_dir: str | Path | None = None,
    input_sha256: str | None = None,
    build_sha256: str | None = None,
    provenance: Mapping[str, Any] | None = None,
    partitions: Mapping[str, Any] | Sequence[str] | None = None,
    stage_callbacks: Mapping[str, Callable[[], Any]] | None = None,
    readback_callbacks: Mapping[str, Callable[[], Any]] | None = None,
    fingerprint_fn: Callable[[str | Path], Mapping[str, Any]] = fingerprint_staged_artifact_tree,
    allow_test_fixtures: bool = False,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Profile an already-created private stage without publishing or mutating it.

    The BL1 lineage and partition preflight intentionally occurs before any
    callback.  A caller may use callbacks for generation-stage instrumentation
    only after its producer has supplied admissible evidence.  The default
    fingerprint is the first-party C++ artifact-tree kernel; tests may inject a
    deterministic equivalent.
    """
    stage = Path(stage_dir)
    state = _ProfileState()
    started = time.perf_counter()
    base: Mapping[str, Any] | None = None
    try:
        if not stage.is_dir():
            result = {"status": "REFUSED", "reason": "stage_missing"}
        else:
            before = fingerprint_fn(stage)
            if baseline_dir is not None:
                base = fingerprint_fn(Path(baseline_dir))
            actual = requested_layers if actual_layers is None else actual_layers
            result = _profile_admission(
                stage=stage,
                requested_layers=requested_layers,
                actual_layers=actual,
                baseline=base,
                before=before,
                input_sha256=input_sha256,
                build_sha256=build_sha256,
                provenance=provenance,
                partitions=partitions,
                allow_test_fixtures=allow_test_fixtures,
                state=state,
                stage_callbacks=stage_callbacks,
                readback_callbacks=readback_callbacks,
                fingerprint_fn=fingerprint_fn,
            )
    except TimeoutError as error:
        result = {"status": "TIMEOUT", "reason": "stage_timeout", "error": str(error)}
    except Exception as error:  # noqa: BLE001
        result = {"status": "REFUSED", "reason": f"profile_exception:{type(error).__name__}"}

    report: dict[str, Any] = {
        "schema": "native-poly-fresh-stage-profile/v1",
        "status": result["status"],
        "reason": result.get("reason"),
        "publish_allowed": False,
        "requested_layers": int(requested_layers),
        "actual_layers": int(actual_layers if actual_layers is not None else requested_layers),
        "input_sha256": input_sha256,
        "build_sha256": build_sha256,
        "stage_timings": {name: state.stage_timings[name] for name in sorted(state.stage_timings)},
        "stage_results": state.stage_results,
        "collision_counters": state.collision_counters,
        "peak_rss_kb": state.peak_rss_kb,
        "elapsed": time.perf_counter() - started,
        **{key: value for key, value in result.items() if key not in {"status", "reason"}},
    }
    report["profile_sha256"] = canonical_profile_sha256(report)
    if output_path is not None:
        destination = Path(output_path)
        if destination.resolve().is_relative_to(stage.resolve()):
            raise ValueError("profile_output_must_not_mutate_stage")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    return report


def _profile_admission(
    *,
    stage: Path,
    requested_layers: int,
    actual_layers: int,
    baseline: Mapping[str, Any] | None,
    before: Mapping[str, Any],
    input_sha256: str | None,
    build_sha256: str | None,
    provenance: Mapping[str, Any] | None,
    partitions: Mapping[str, Any] | Sequence[str] | None,
    allow_test_fixtures: bool,
    state: _ProfileState,
    stage_callbacks: Mapping[str, Callable[[], Any]] | None,
    readback_callbacks: Mapping[str, Callable[[], Any]] | None,
    fingerprint_fn: Callable[[str | Path], Mapping[str, Any]],
) -> dict[str, Any]:
    if requested_layers < 0 or actual_layers < 0:
        return {"status": "REFUSED", "reason": "layer_count_negative"}
    if requested_layers == 0:
        if actual_layers != 0:
            return {"status": "REFUSED", "reason": "bl0_actual_nonzero"}
        if baseline is None:
            return {"status": "REFUSED", "reason": "bl0_baseline_missing"}
        if dict(before) != dict(baseline):
            return {"status": "REGRESSION", "reason": "bl0_artifact_not_identity"}
        return {
            "status": "PASS",
            "reason": "bl0_disabled_identity",
            "observation_only": True,
            "publish_allowed": False,
        }

    if actual_layers != requested_layers:
        return {"status": "REFUSED", "reason": "requested_actual_layer_mismatch"}
    if (provenance is not None or partitions is not None) and not allow_test_fixtures:
        return {"status": "REFUSED", "reason": "caller_lineage_not_producer_evidence"}
    for name, value in (("input_sha256", input_sha256), ("build_sha256", build_sha256)):
        reason = _validate_fixed_digest(name, value)
        if reason:
            return {"status": "REFUSED", "reason": reason}
    reason = _validate_lineage(_load_provenance(stage, provenance))
    if reason:
        return {"status": "REFUSED", "reason": reason}
    normalized_partitions = _load_partitions(stage, partitions)
    reason = _validate_partitions(normalized_partitions)
    if reason:
        return {"status": "REFUSED", "reason": reason}

    for name, callback in (stage_callbacks or {}).items():
        try:
            state.run(name, callback)
        except TimeoutError:
            return {"status": "TIMEOUT", "reason": f"stage_timeout:{name}"}
        except Exception:
            return {"status": "REFUSED", "reason": f"stage_failed:{name}"}
    for name, callback in (readback_callbacks or {}).items():
        try:
            value = state.run(name, callback)
        except TimeoutError:
            return {"status": "TIMEOUT", "reason": f"stage_timeout:{name}"}
        except Exception:
            return {"status": "REFUSED", "reason": f"stage_failed:{name}"}
        if name in {"strict_topology", "quality_witness"} and not _accepted(value):
            return {"status": "REFUSED", "reason": f"{name}_gate_failed"}

    after = fingerprint_fn(stage)
    if dict(after) != dict(before):
        return {"status": "REGRESSION", "reason": "stage_mutated_after_admission"}
    return {
        "status": "PASS",
        "reason": "admitted_readonly_profile",
        "publish_allowed": False,
        "partitions": dict(normalized_partitions or {}),
        "artifact_before": dict(before),
        "artifact_after": dict(after),
    }


__all__ = ["REQUIRED_LINEAGE_DIGESTS", "canonical_profile_sha256", "profile_poly_bl_stage"]
