"""Digest-bound source identity and selector resolution.

The ledger deliberately exposes only identities that the parser can prove from
the uploaded source.  It never turns a filename, STL facet, XDE display label,
or free-form UI string into a physical group or feature authority claim.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

LEDGER_SCHEMA_VERSION = "1.0"
_STL_EXTENSIONS = {".stl"}
_CAD_EXTENSIONS = {".step", ".stp", ".iges", ".igs", ".brep"}
_NAMESPACE_KINDS = ("stl_facet", "cad_face", "cad_edge")
_SEMANTIC_KINDS = ("feature", "physical_group", "component", "stl_patch")


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _range_for_ids(ids: list[int]) -> list[list[int]]:
    if not ids:
        return []
    ordered = sorted(set(int(item) for item in ids))
    ranges: list[list[int]] = []
    start = previous = ordered[0]
    for value in ordered[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append([start, previous])
        start = previous = value
    ranges.append([start, previous])
    return ranges


def _namespace(
    *,
    kind: str,
    ids: list[int] | None = None,
    authority: str = "source_geometry",
    reason: str | None = None,
) -> dict[str, Any]:
    values = sorted(set(int(item) for item in (ids or [])))
    result: dict[str, Any] = {
        "kind": kind,
        "available": bool(values) and reason is None,
        "authority": authority if values and reason is None else "unavailable",
        "id_ranges": _range_for_ids(values),
        "count": len(values),
        "records": [{"id": value, "kind": kind} for value in values]
        if len(values) <= 4096 else [],
    }
    if reason is not None:
        result["reason"] = reason
    return result


def _unavailable_namespace(kind: str, reason: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "available": False,
        "authority": "unavailable",
        "id_ranges": [],
        "count": 0,
        "records": [],
        "reason": reason,
    }


def _base_ledger(path: Path, source_digest: str, size_bytes: int) -> dict[str, Any]:
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "source_digest": source_digest,
        "source": {
            "filename": path.name,
            "format": path.suffix.lower().lstrip("."),
            "size_bytes": size_bytes,
            "sha256": source_digest,
        },
        "parser": {"name": "AutoTessell source authority ledger", "version": LEDGER_SCHEMA_VERSION},
        "status": "unavailable",
        "authority_level": "unavailable",
        "selector_namespaces": {},
        "entities": {},
    }


def _finalize(ledger: dict[str, Any]) -> dict[str, Any]:
    for kind in (*_NAMESPACE_KINDS, *_SEMANTIC_KINDS):
        ledger["selector_namespaces"].setdefault(
            kind, _unavailable_namespace(kind, "parser does not expose this semantic namespace")
        )
    ledger["ledger_digest"] = _digest(
        {key: value for key, value in ledger.items() if key != "ledger_digest"}
    )
    return ledger


def build_source_authority_ledger(path: str | Path) -> dict[str, Any]:
    """Build a public, path-free ledger from a real uploaded source file.

    Parser failure returns an unavailable ledger with the source digest and the
    failure reason.  It does not synthesize entity IDs or semantic labels.
    """
    source = Path(path)
    if not source.exists() or not source.is_file():
        return _finalize({
            "schema_version": LEDGER_SCHEMA_VERSION,
            "source_digest": None,
            "source": {"filename": source.name, "format": source.suffix.lower().lstrip(".")},
            "parser": {"name": "AutoTessell source authority ledger", "version": LEDGER_SCHEMA_VERSION},
            "status": "unavailable",
            "authority_level": "unavailable",
            "selector_namespaces": {},
            "entities": {},
            "error": "source file is missing",
        })

    source_digest, size_bytes = _file_digest(source)
    ledger = _base_ledger(source, source_digest, size_bytes)
    ext = source.suffix.lower()
    try:
        if ext in _STL_EXTENSIONS:
            from core.analyzer.readers.stl import read_stl

            mesh = read_stl(source, dedupe=False)
            face_count = int(len(mesh.faces))
            ids = list(range(face_count))
            ledger["status"] = "authoritative_partial"
            ledger["authority_level"] = "source_facet_identity"
            ledger["selector_namespaces"]["stl_facet"] = _namespace(kind="stl_facet", ids=ids)
            ledger["entities"]["stl_facets"] = ledger["selector_namespaces"]["stl_facet"]
            ledger["metadata"] = {
                "face_count": face_count,
                "watertight": None,
                "manifold": None,
            }
        elif ext in _CAD_EXTENSIONS:
            from core.analyzer.readers.step import load_cad_native_with_provenance

            result = load_cad_native_with_provenance(source, ext)
            provenance = result.provenance
            face_ids = list(range(int(provenance.face_count)))
            edge_array = provenance.triangle_brep_edge_ids
            edge_ids = []
            if edge_array is not None:
                edge_ids = [int(value) for value in set(edge_array.reshape(-1).tolist()) if int(value) > 0]
            ledger["status"] = "authoritative_partial"
            ledger["authority_level"] = "brep_entity_identity"
            ledger["selector_namespaces"]["cad_face"] = _namespace(kind="cad_face", ids=face_ids)
            ledger["selector_namespaces"]["cad_edge"] = _namespace(kind="cad_edge", ids=edge_ids)
            ledger["entities"]["cad_faces"] = ledger["selector_namespaces"]["cad_face"]
            ledger["entities"]["cad_edges"] = ledger["selector_namespaces"]["cad_edge"]
            ledger["metadata"] = {
                "face_count": int(provenance.face_count),
                "topological_edge_count": int(provenance.topological_edge_count),
                "face_ordinals_authoritative": bool(provenance.face_ordinals_authoritative),
                "face_orientation_authoritative": bool(provenance.face_orientation_authoritative),
                "seam_connectivity_authoritative": bool(provenance.seam_connectivity_authoritative),
                "physical_groups_authoritative": bool(provenance.physical_groups_authoritative),
                "xde_layer_authoritative": bool(provenance.xde_layer_authoritative),
                "xde_assembly_identity_authoritative": bool(provenance.xde_assembly_identity_authoritative),
            }
        else:
            ledger["error"] = f"unsupported source format: {ext or '<none>'}"
    except Exception as exc:  # noqa: BLE001 — ledger must fail closed
        ledger["error"] = f"source parser unavailable: {type(exc).__name__}"

    return _finalize(ledger)


def _id_is_available(namespace: dict[str, Any], value: int) -> bool:
    for start, end in namespace.get("id_ranges", []):
        if int(start) <= value <= int(end):
            return True
    return False


def resolve_selector(
    ledger: dict[str, Any] | None,
    selector: Any,
    *,
    pointer: str,
    strict: bool = True,
) -> dict[str, Any]:
    """Resolve one explicit selector against a ledger without free-text guesses."""
    base = {"pointer": pointer, "requested": copy.deepcopy(selector), "status": "rejected", "matched_ids": []}
    if not isinstance(selector, dict):
        base["status"] = "rejected" if strict else "unavailable_missing_authority"
        base["reason"] = "selector must be an object with ledger_digest, kind, and ids"
        return base
    digest = selector.get("ledger_digest")
    kind = str(selector.get("kind", "")).strip().lower()
    ids = selector.get("ids")
    if not isinstance(digest, str) or not digest or kind not in _NAMESPACE_KINDS or not isinstance(ids, list) or not ids:
        base["status"] = "rejected" if strict else "unavailable_missing_authority"
        base["reason"] = "selector requires a ledger digest, supported kind, and non-empty ids"
        return base
    if ledger is None or digest != ledger.get("ledger_digest"):
        base["status"] = "rejected" if strict else "unavailable_stale_ledger"
        base["reason"] = "selector ledger digest does not match the uploaded source"
        return base
    namespace = ledger.get("selector_namespaces", {}).get(kind, {})
    if not namespace.get("available"):
        base["status"] = "rejected" if strict else "unavailable_missing_authority"
        base["reason"] = namespace.get("reason", f"namespace {kind} is unavailable")
        return base
    try:
        normalized = [int(value) for value in ids]
    except (TypeError, ValueError):
        normalized = []
    if not normalized or len(set(normalized)) != len(normalized) or any(not _id_is_available(namespace, value) for value in normalized):
        base["status"] = "rejected" if strict else "unavailable_invalid_entity"
        base["reason"] = "selector contains duplicate or unavailable entity IDs"
        return base
    base.update({
        "status": "resolved",
        "matched_ids": sorted(normalized),
        "ledger_digest": ledger["ledger_digest"],
        "kind": kind,
        "authority": namespace.get("authority"),
    })
    return base


def resolve_input_selectors(
    config: dict[str, Any],
    ledger: dict[str, Any] | None,
    *,
    strict: bool = True,
) -> dict[str, Any]:
    """Resolve BL/local-control selectors and return a run preflight report."""
    resolutions: list[dict[str, Any]] = []
    layers = config.get("boundary_layers", [])
    for index, entry in enumerate(layers if isinstance(layers, list) else []):
        if not isinstance(entry, dict):
            continue
        if int(entry.get("layers", 0) or 0) == 0:
            resolutions.append({"pointer": f"/boundary_layers/{index}", "status": "ignored_identity", "matched_ids": []})
            continue
        selector = entry.get("selector")
        if selector is None:
            selector = entry.get("source_selector")
        resolutions.append(resolve_selector(ledger, selector, pointer=f"/boundary_layers/{index}/selector", strict=strict))
    controls = config.get("local_controls", [])
    for index, entry in enumerate(controls if isinstance(controls, list) else []):
        selector = entry.get("selector") if isinstance(entry, dict) else None
        resolutions.append(resolve_selector(ledger, selector, pointer=f"/local_controls/{index}/selector", strict=strict))
    failed = [item for item in resolutions if item["status"] not in {"resolved", "ignored_identity"}]
    report = {
        "status": "resolved" if not failed else "rejected" if strict else "unavailable",
        "strict": bool(strict),
        "source_digest": (ledger or {}).get("source_digest"),
        "ledger_digest": (ledger or {}).get("ledger_digest"),
        "resolutions": resolutions,
        "failed": failed,
        "can_run": not failed,
    }
    return report


__all__ = [
    "LEDGER_SCHEMA_VERSION",
    "build_source_authority_ledger",
    "resolve_selector",
    "resolve_input_selectors",
]
