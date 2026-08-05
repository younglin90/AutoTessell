"""C++23-backed Native Tri STL source-authority certificate adapter.

The adapter constructs no geometry and never infers semantics.  It only calls
the private C++ source reader with an explicit semantic ledger and external
trust anchor.  Positive boundary-layer requests remain an atomic refusal until
an authority-bound Tri BL writer exists.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from core.utils.native_extensions import import_native_extension


def _refusal(reason: str) -> dict[str, Any]:
    return {
        "accepted": False,
        "status": "native_tri_authority_source_refused",
        "reason": reason,
        "certificate_accepted": False,
        "eligible_for_tri_bl": False,
        "actual_layers": 0,
        "publication_eligible": False,
        "candidate_discarded": True,
        "artifact_emitted": False,
        "runtime_route": "private_default_off",
        "route_calls": 0,
        "generated_vertices": [],
        "generated_faces": [],
        "provenance": [],
    }


def _ledger_row(
    face_id: int,
    vertices: Sequence[int],
    feature: str,
    patch: str,
    physical_group: str,
    component: str,
    provenance: str,
) -> dict[str, Any]:
    return {
        "face_id": int(face_id),
        "source_facet_id": int(face_id),
        "vertices": [int(value) for value in vertices],
        "feature": str(feature),
        "patch": str(patch),
        "physical_group": str(physical_group),
        "component": str(component),
        "provenance": str(provenance),
    }


def semantic_ledger_from_faces(
    faces: Any,
    *,
    feature: str,
    patch: str,
    physical_group: str,
    component: str,
    provenance: str,
) -> list[dict[str, Any]]:
    """Create explicit labels for a caller-owned face ledger.

    This helper does not inspect geometry or infer labels; callers must provide
    the authoritative values and should persist the returned ledger.
    """

    array = np.asarray(faces, dtype=np.int64)
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError("tri_semantic_faces_shape_invalid")
    return [
        _ledger_row(
            index,
            row,
            feature,
            patch,
            physical_group,
            component,
            provenance,
        )
        for index, row in enumerate(array.tolist())
    ]


def _semantic_stream(ledger: Sequence[Mapping[str, Any]]) -> str:
    rows = sorted(ledger, key=lambda row: int(row["face_id"]))
    pieces = [f"rows={len(rows)}|"]
    for row in rows:
        vertices = [int(value) for value in row["vertices"]]
        pieces.append(
            f"{int(row['face_id'])}:{vertices[0]},{vertices[1]},{vertices[2]}|"
        )
        for key in ("feature", "patch", "physical_group", "component", "provenance"):
            value = str(row[key])
            pieces.append(f"{len(value)}:{value}|")
    return "".join(pieces)


def semantic_ledger_sha256(ledger: Sequence[Mapping[str, Any]]) -> str:
    """Return the C++ certificate's canonical semantic-ledger digest."""

    return hashlib.sha256(_semantic_stream(ledger).encode("utf-8")).hexdigest()


def make_external_trust_anchor(
    source: str | Path,
    ledger: Sequence[Mapping[str, Any]],
    *,
    issuer: str,
    key_id: str,
) -> dict[str, object]:
    """Build a registration record for tests or an external authority store."""

    path = Path(source)
    if path.is_symlink() or not path.is_file():
        raise ValueError("tri_source_file_must_be_real")
    payload = path.read_bytes()
    return {
        "source_sha256": hashlib.sha256(payload).hexdigest(),
        "source_byte_count": len(payload),
        "semantic_ledger_sha256": semantic_ledger_sha256(ledger),
        "issuer": str(issuer),
        "key_id": str(key_id),
    }


def validate_native_tri_authority_source(
    source: str | Path,
    ledger: Sequence[Mapping[str, Any]],
    trust_anchor: Mapping[str, Any],
    *,
    requested_layers: int = 0,
) -> dict[str, Any]:
    """Read and certify a real STL source through the C++23 ingress."""

    try:
        module = import_native_extension("native_tri_cad_stl_authority_ingress")
        result = dict(
            module.validate_native_tri_authority_source(
                str(Path(source)),
                dict(trust_anchor),
                [dict(row) for row in ledger],
                int(requested_layers),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _refusal(f"native_tri_authority_source_unavailable:{type(exc).__name__}")
    return result


def admit_native_tri_authority_certificate(
    certificate_result: Mapping[str, Any],
    *,
    requested_layers: int = 0,
) -> dict[str, Any]:
    """Admit only a C++-sealed certificate; never turns it into publication."""

    if not isinstance(certificate_result, Mapping) or not certificate_result.get(
        "certificate_accepted", False
    ):
        return _refusal("tri_source_certificate_required")
    if int(requested_layers) > 0:
        return _refusal("native_tri_bl_writer_unavailable")
    return {
        "accepted": True,
        "status": "native_tri_authority_release_admission_sealed",
        "reason": "cpp_source_certificate_and_bl0_contract_verified",
        "certificate_accepted": True,
        "actual_layers": 0,
        "publication_eligible": False,
        "runtime_route": "private_default_off",
        "route_calls": 0,
        "candidate_discarded": False,
        "artifact_emitted": False,
        "generated_vertices": [],
        "generated_faces": [],
        "provenance": [],
        "source_certificate_sha256": certificate_result.get(
            "source_certificate_sha256"
        ),
        "semantic_ledger_sha256": certificate_result.get("semantic_ledger_sha256"),
    }


__all__ = [
    "admit_native_tri_authority_certificate",
    "make_external_trust_anchor",
    "semantic_ledger_from_faces",
    "semantic_ledger_sha256",
    "validate_native_tri_authority_source",
]
