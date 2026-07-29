"""Typed patch roles for native poly wall-layer eligibility."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from core.utils.logging import get_logger

log = get_logger(__name__)

_WALL = "wall"
_UNKNOWN = "unknown"
_ROLE_ALIASES = {
    "wall": _WALL,
    "walls": _WALL,
    "inlet": "inlet",
    "inlets": "inlet",
    "outlet": "outlet",
    "outlets": "outlet",
    "symmetry": "symmetry",
    "symmetryplane": "symmetry",
    "symmetry_plane": "symmetry",
    "empty": "empty",
}
_FOAM_ROLE_ALIASES = {
    "wall": _WALL,
    "symmetryplane": "symmetry",
    "symmetry": "symmetry",
    "empty": "empty",
}
_NAME_NONWALL_ALIASES = {
    "inlet": "inlet",
    "outlet": "outlet",
    "symmetry": "symmetry",
    "symmetryplane": "symmetry",
    "empty": "empty",
}
_NONWALL_ROLES = {"inlet", "outlet", "symmetry", "empty"}


@dataclass(frozen=True)
class PolyPatchIntent:
    patch_id: int
    source_name: str
    output_name: str
    foam_type: str
    semantic_role: str
    source_face_ids: tuple[int, ...]
    provenance_confidence: str
    bl_enabled: bool


@dataclass(frozen=True)
class PolyFaceProvenanceDiagnostic:
    n_faces: int
    assigned_faces: int
    missing_faces: int
    invalid_face_assignments: int
    conflicting_face_assignments: int
    wall_faces: int
    nonwall_faces: int
    unknown_faces: int
    protected_interface_edges: tuple[tuple[int, int], ...]
    conflicts: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return (
            self.invalid_face_assignments == 0
            and self.conflicting_face_assignments == 0
            and self.missing_faces == 0
        )


def _get_field(patch: Any, *names: str, default: Any = None) -> Any:
    if isinstance(patch, dict):
        for name in names:
            if name in patch:
                return patch[name]
        return default
    for name in names:
        if hasattr(patch, name):
            return getattr(patch, name)
    return default


def _norm_token(value: Any) -> str:
    return str(value or "").strip()


def _norm_role(value: Any) -> str:
    key = _norm_token(value).replace("-", "_").replace(" ", "_").lower()
    return _ROLE_ALIASES.get(key, _UNKNOWN if not key else key)


def _role_from_name(name: str) -> str:
    key = name.strip().replace("-", "_").replace(" ", "_").lower()
    return _NAME_NONWALL_ALIASES.get(key, _UNKNOWN)


def _face_ids_from_patch(
    patch: Any,
    patch_id: int,
    face_patch_ids: np.ndarray | None,
    n_faces: int,
) -> tuple[int, ...]:
    raw = _get_field(patch, "source_face_ids", "face_ids", "faces")
    if raw is not None:
        try:
            ids = np.asarray(raw, dtype=np.int64).reshape(-1)
            return tuple(int(x) for x in np.unique(ids))
        except Exception:
            return ()
    if face_patch_ids is not None and face_patch_ids.shape[0] == int(n_faces):
        return tuple(int(x) for x in np.flatnonzero(face_patch_ids == int(patch_id)))
    return ()


def resolve_poly_patch_intents(
    boundary_patches: list[Any] | tuple[Any, ...] | None,
    *,
    n_faces: int,
    face_patch_ids: np.ndarray | None = None,
    explicit_wall_patch_names: list[str] | tuple[str, ...] | set[str] | None = None,
) -> list[PolyPatchIntent]:
    """Resolve foam patch type and semantic role without name-only wall inference."""
    if not boundary_patches:
        return []

    explicit_walls = {str(x).strip() for x in (explicit_wall_patch_names or []) if str(x).strip()}
    intents: list[PolyPatchIntent] = []
    for patch_id, patch in enumerate(boundary_patches):
        source_name = _norm_token(_get_field(patch, "source_name", "name", default=f"patch{patch_id}"))
        output_name = _norm_token(_get_field(patch, "output_name", "name", default=source_name))
        foam_type = _norm_token(_get_field(patch, "foam_type", "type", default="patch"))
        explicit_role_raw = _get_field(patch, "semantic_role", "role", "patch_role", default=None)

        confidence = "explicit_role"
        if explicit_role_raw is not None:
            semantic_role = _norm_role(explicit_role_raw)
        else:
            foam_key = foam_type.replace("-", "_").replace(" ", "_").lower()
            semantic_role = _FOAM_ROLE_ALIASES.get(foam_key, _UNKNOWN)
            confidence = "foam_type" if semantic_role != _UNKNOWN else "unknown"
            if semantic_role == _UNKNOWN:
                named_role = _role_from_name(source_name) or _role_from_name(output_name)
                if named_role != _UNKNOWN:
                    semantic_role = named_role
                    confidence = "name_nonwall"

        requested_wall = source_name in explicit_walls or output_name in explicit_walls
        if requested_wall:
            if semantic_role in _NONWALL_ROLES:
                log.warning(
                    "native_poly_wall_patch_conflict",
                    patch=output_name,
                    foam_type=foam_type,
                    semantic_role=semantic_role,
                )
            elif semantic_role != _WALL:
                semantic_role = _WALL
                confidence = "explicit_wall_selection"

        face_ids = _face_ids_from_patch(patch, patch_id, face_patch_ids, int(n_faces))
        intents.append(
            PolyPatchIntent(
                patch_id=int(patch_id),
                source_name=source_name,
                output_name=output_name,
                foam_type=foam_type,
                semantic_role=semantic_role,
                source_face_ids=face_ids,
                provenance_confidence=confidence,
                bl_enabled=semantic_role == _WALL,
            )
        )
    return intents


def _assign_face_intents(
    n_faces: int,
    intents: list[PolyPatchIntent] | tuple[PolyPatchIntent, ...] | None,
    *,
    face_patch_ids: np.ndarray | None = None,
) -> tuple[np.ndarray, int, int, tuple[str, ...]]:
    face_intent_ids = np.full(int(n_faces), -1, dtype=np.int64)
    invalid = 0
    conflicts: list[str] = []
    intent_by_patch = {int(intent.patch_id): intent for intent in (intents or [])}

    if face_patch_ids is not None and face_patch_ids.shape[0] == int(n_faces):
        patch_ids = np.asarray(face_patch_ids, dtype=np.int64).reshape(-1)
        for face_id, patch_id in enumerate(patch_ids):
            if int(patch_id) in intent_by_patch:
                face_intent_ids[int(face_id)] = int(patch_id)

    for intent in intents or ():
        patch_id = int(intent.patch_id)
        for raw_face_id in intent.source_face_ids:
            face_id = int(raw_face_id)
            if face_id < 0 or face_id >= int(n_faces):
                invalid += 1
                continue
            previous = int(face_intent_ids[face_id])
            if previous >= 0 and previous != patch_id:
                conflicts.append(f"face {face_id}: patch {previous} vs {patch_id}")
                continue
            face_intent_ids[face_id] = patch_id
    return face_intent_ids, invalid, len(conflicts), tuple(conflicts)


def face_intent_ids_from_intents(
    n_faces: int,
    intents: list[PolyPatchIntent] | tuple[PolyPatchIntent, ...] | None,
    *,
    face_patch_ids: np.ndarray | None = None,
) -> np.ndarray:
    """Return stable source-face -> patch-intent IDs; unknown faces are -1."""
    ids, _, _, _ = _assign_face_intents(
        int(n_faces),
        intents,
        face_patch_ids=face_patch_ids,
    )
    return ids


def wall_face_mask_from_intents(
    n_faces: int,
    intents: list[PolyPatchIntent] | tuple[PolyPatchIntent, ...] | None,
    *,
    face_patch_ids: np.ndarray | None = None,
) -> np.ndarray:
    """Return source-face mask where native poly may create boundary layers."""
    mask = np.zeros(int(n_faces), dtype=bool)
    if not intents:
        return mask
    patch_ids = {int(intent.patch_id) for intent in intents if intent.bl_enabled}
    if face_patch_ids is not None and face_patch_ids.shape[0] == int(n_faces):
        for patch_id in patch_ids:
            mask |= face_patch_ids == int(patch_id)
    for intent in intents:
        if not intent.bl_enabled:
            continue
        for face_id in intent.source_face_ids:
            if 0 <= int(face_id) < int(n_faces):
                mask[int(face_id)] = True
    return mask


def provenance_gated_wall_face_mask(
    surface_faces: np.ndarray,
    intents: list[PolyPatchIntent] | tuple[PolyPatchIntent, ...] | None,
    *,
    face_patch_ids: np.ndarray | None = None,
) -> tuple[np.ndarray, PolyFaceProvenanceDiagnostic]:
    """Return a BL wall mask only when source-face provenance is complete.

    Boundary-layer insertion changes topology at the wall. It must not infer
    a wall mask from a partial or contradictory patch assignment, because that
    could place layers across an inlet, outlet, or patch interface.
    """
    faces = np.asarray(surface_faces, dtype=np.int64)
    n_faces = int(faces.shape[0]) if faces.ndim >= 1 else 0
    diagnostic = diagnose_poly_face_provenance(
        faces,
        intents,
        face_patch_ids=face_patch_ids,
    )
    log.info(
        "native_poly_bl_provenance_evidence",
        allowed=bool(diagnostic.ok),
        assigned_faces=diagnostic.assigned_faces,
        missing_faces=diagnostic.missing_faces,
        invalid_face_assignments=diagnostic.invalid_face_assignments,
        conflicting_face_assignments=diagnostic.conflicting_face_assignments,
        wall_faces=diagnostic.wall_faces,
        protected_interface_edges=len(diagnostic.protected_interface_edges),
    )
    if not diagnostic.ok:
        return np.zeros(n_faces, dtype=bool), diagnostic
    return (
        wall_face_mask_from_intents(
            n_faces,
            intents,
            face_patch_ids=face_patch_ids,
        ),
        diagnostic,
    )


def protected_patch_interface_edges(
    surface_faces: np.ndarray,
    face_intent_ids: np.ndarray,
) -> tuple[tuple[int, int], ...]:
    """Edges shared by different source patch intents; never safe for face merge."""
    faces = np.asarray(surface_faces, dtype=np.int64)
    ids = np.asarray(face_intent_ids, dtype=np.int64).reshape(-1)
    if faces.ndim != 2 or faces.shape[0] != ids.shape[0]:
        return ()

    edge_to_intents: dict[tuple[int, int], set[int]] = {}
    for face_id, face in enumerate(faces):
        intent_id = int(ids[face_id])
        if intent_id < 0:
            continue
        verts = [int(v) for v in face.tolist()]
        for idx, a in enumerate(verts):
            b = verts[(idx + 1) % len(verts)]
            if a == b:
                continue
            edge = (a, b) if a < b else (b, a)
            edge_to_intents.setdefault(edge, set()).add(intent_id)

    protected = [edge for edge, edge_intents in edge_to_intents.items() if len(edge_intents) > 1]
    protected.sort()
    return tuple(protected)


def diagnose_poly_face_provenance(
    surface_faces: np.ndarray,
    intents: list[PolyPatchIntent] | tuple[PolyPatchIntent, ...] | None,
    *,
    face_patch_ids: np.ndarray | None = None,
) -> PolyFaceProvenanceDiagnostic:
    """POLY-TOPO1 diagnostic for source-face provenance before topology/merge."""
    faces = np.asarray(surface_faces, dtype=np.int64)
    n_faces = int(faces.shape[0]) if faces.ndim >= 1 else 0
    face_intent_ids, invalid, conflicting, conflicts = _assign_face_intents(
        n_faces,
        intents,
        face_patch_ids=face_patch_ids,
    )
    intent_by_patch = {int(intent.patch_id): intent for intent in (intents or [])}

    assigned = face_intent_ids >= 0
    wall_faces = 0
    nonwall_faces = 0
    unknown_faces = int((~assigned).sum())
    for patch_id in face_intent_ids[assigned]:
        intent = intent_by_patch.get(int(patch_id))
        if intent is None or intent.semantic_role == _UNKNOWN:
            unknown_faces += 1
        elif intent.semantic_role == _WALL:
            wall_faces += 1
        else:
            nonwall_faces += 1

    protected = protected_patch_interface_edges(faces, face_intent_ids)
    return PolyFaceProvenanceDiagnostic(
        n_faces=n_faces,
        assigned_faces=int(assigned.sum()),
        missing_faces=int((~assigned).sum()),
        invalid_face_assignments=int(invalid),
        conflicting_face_assignments=int(conflicting),
        wall_faces=int(wall_faces),
        nonwall_faces=int(nonwall_faces),
        unknown_faces=int(unknown_faces),
        protected_interface_edges=protected,
        conflicts=conflicts,
    )
