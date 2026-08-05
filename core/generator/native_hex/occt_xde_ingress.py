"""Fail-closed orchestration for the optional Native Hex OCCT/XDE ingress."""

from __future__ import annotations

import os
from hashlib import sha256
from pathlib import Path
from typing import Any, Sequence

from core.utils.native_extensions import import_native_extension


_SEMANTIC_FIELDS = ("feature", "patch", "physical_group", "component", "provenance")


def canonical_semantic_ledger_digest(
    semantic_rows: Sequence[dict[str, Any]],
) -> str:
    """Return the C++-compatible canonical semantic-ledger SHA-256."""
    parts = ["native-hex-semantic-ledger-v1|"]
    for index, row in enumerate(semantic_rows):
        if not isinstance(row, dict):
            raise ValueError("semantic_row_not_object")
        for ordinal_key in ("source_face", "face_id"):
            if ordinal_key in row and int(row[ordinal_key]) != index:
                raise ValueError(f"semantic_{ordinal_key}_not_canonical")
        parts.append(f"source_face={index}|")
        for key in _SEMANTIC_FIELDS:
            value = row.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(f"semantic_field_missing_or_empty:{key}")
            encoded = value.encode("utf-8")
            parts.append(f"{key}={len(encoded)}:{value}|")
        parts.append(";")
    return sha256("".join(parts).encode("utf-8")).hexdigest()


def read_authoritative_step_xde(
    step_path: str | Path,
    *,
    sdk_root: str | Path | None = None,
    expected_occt_version: str = "",
    expected_abi: str = "",
    semantic_rows: Sequence[dict[str, Any]] = (),
    expected_compiler_abi: str = "",
    expected_build_identity: str = "",
    provisioning_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Request a C++ OCCT/XDE certificate without an OCP/STL fallback."""
    path = Path(step_path)
    root = "" if sdk_root is None else str(sdk_root)
    manifest = (
        ""
        if provisioning_manifest_path is None
        else str(provisioning_manifest_path)
    )
    if not manifest:
        manifest = os.environ.get("AUTOTESSELL_OCCT_PROVISIONING_MANIFEST", "")
    if not manifest and root:
        manifest = str(
            Path(root) / "autotessell_native_hex_occt_provisioning.manifest"
        )
    try:
        kernel = import_native_extension("native_hex_occt_xde_ingress")
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "authoritative": False,
            "status": "native_hex_occt_xde_ingress_refused",
            "reason": f"native_extension_unavailable:{type(exc).__name__}",
            "step_path": str(path),
            "sdk_root": root,
            "candidate_discarded": True,
            "publication_eligible": False,
        }
    try:
        result = dict(
            kernel.read_step_xde(
                str(path),
                root,
                str(expected_occt_version),
                str(expected_abi),
                list(semantic_rows),
                str(expected_compiler_abi),
                str(expected_build_identity),
                manifest,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "accepted": False,
            "authoritative": False,
            "status": "native_hex_occt_xde_ingress_refused",
            "reason": f"native_ingress_exception:{type(exc).__name__}",
            "step_path": str(path),
            "sdk_root": root,
            "candidate_discarded": True,
            "publication_eligible": False,
        }
    result["step_path"] = str(path)
    result["sdk_root"] = root
    result["provisioning_manifest_path"] = manifest
    result["authority_contract"] = (
        "autotessell/native-hex-occt-xde-ingress/v1"
    )
    if result.get("accepted") is not True:
        result["authoritative"] = False
        result["candidate_discarded"] = True
        result["publication_eligible"] = False
    else:
        provisioning_digest = result.get("occt_provisioning_manifest_sha256")
        if not isinstance(provisioning_digest, str) or len(provisioning_digest) != 64:
            result.update({
                "accepted": False,
                "authoritative": False,
                "status": "native_hex_occt_xde_ingress_refused",
                "reason": "occt_provisioning_manifest_digest_missing",
                "candidate_discarded": True,
                "publication_eligible": False,
            })
            return result
        supplied_digest = result.get("semantic_ledger_sha256")
        if not isinstance(supplied_digest, str) or len(supplied_digest) != 64:
            result.update({
                "accepted": False,
                "authoritative": False,
                "status": "native_hex_occt_xde_ingress_refused",
                "reason": "semantic_ledger_digest_missing",
                "candidate_discarded": True,
                "publication_eligible": False,
            })
        else:
            try:
                expected_digest = canonical_semantic_ledger_digest(semantic_rows)
            except Exception as exc:  # noqa: BLE001
                result.update({
                    "accepted": False,
                    "authoritative": False,
                    "status": "native_hex_occt_xde_ingress_refused",
                    "reason": f"semantic_ledger_invalid:{type(exc).__name__}",
                    "candidate_discarded": True,
                    "publication_eligible": False,
                })
            else:
                if expected_digest != supplied_digest:
                    result.update({
                        "accepted": False,
                        "authoritative": False,
                        "status": "native_hex_occt_xde_ingress_refused",
                        "reason": "semantic_ledger_digest_mismatch",
                        "candidate_discarded": True,
                        "publication_eligible": False,
                    })
    return result


__all__ = ["canonical_semantic_ledger_digest", "read_authoritative_step_xde"]
