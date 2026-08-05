"""L0/L1 tests for the C++23 BL identity and atomic eligibility witness."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "auto_tessell_core" / "build"
if BUILD.exists():
    sys.path.insert(0, str(BUILD))
native = pytest.importorskip("native_bl_identity")

_DIGEST_FIELDS = (
    "source_sha256",
    "route_sha256",
    "geometry_sha256",
    "topology_sha256",
    "boundary_sha256",
    "feature_sha256",
    "physical_group_sha256",
    "component_sha256",
    "provenance_sha256",
    "artifact_tree_sha256",
    "quality_witness_digest",
    "authority_certificate_sha256",
)


def _record(product: str = "surface", mode: str = "disabled_identity", seed: str = "a") -> dict[str, str]:
    values = {}
    for index, field in enumerate(_DIGEST_FIELDS):
        letter = chr(ord(seed) + (index % 3))
        values[field] = letter * 64
    return {
        "schema": "autotessell/native-bl-identity/v1",
        "engine": "native",
        "product": product,
        "mode": mode,
        **values,
        "quality_profile_id": "surface-wall-edge-v2",
    }


def _topology(**updates: int) -> dict[str, int]:
    result = {
        "invalid": 0,
        "inverted": 0,
        "duplicate": 0,
        "non_manifold": 0,
        "self_intersecting": 0,
    }
    result.update(updates)
    return result


def _quality(accepted: bool = True, profile: str = "surface-wall-edge-v2") -> dict[str, object]:
    return {"accepted": accepted, "profile_id": profile}


def _call(
    baseline: dict[str, str],
    candidate: dict[str, str],
    requested: int,
    actual: int,
    *,
    topology: dict[str, int] | None = None,
    quality: dict[str, object] | None = None,
    authority: bool = True,
    receipt: bool = True,
    profile: str = "surface-wall-edge-v2",
):
    return native.evaluate_bl_identity_record(
        baseline,
        candidate,
        requested,
        actual,
        topology or _topology(),
        quality or _quality(),
        authority,
        receipt,
        profile,
    )


@pytest.mark.parametrize(
    "product",
    ["tet", "hex", "poly", "tri", "strict_quad", "tri_plus_quad", "surface"],
)
def test_bl0_requires_exact_identity_for_every_product(product: str) -> None:
    baseline = _record(product=product)
    candidate = copy.deepcopy(baseline)
    result = _call(baseline, candidate, 0, 0)
    assert result["accepted"] is True
    assert result["status"] == "identity_pass"
    assert result["actual_layers"] == 0
    assert result["baseline_identity"] is True

    changed = copy.deepcopy(candidate)
    changed["artifact_tree_sha256"] = "f" * 64
    refused = _call(baseline, changed, 0, 0)
    assert refused["accepted"] is False
    assert refused["status"] == "refused_rollback"
    assert refused["actual_layers"] == 0
    assert "bl0_baseline_identity_mismatch" in refused["reasons"]


def test_positive_bl_requires_exact_layers_quality_authority_and_receipt() -> None:
    baseline = _record(product="tet")
    candidate = _record(product="tet", mode="transaction_candidate", seed="b")
    candidate["source_sha256"] = baseline["source_sha256"]
    candidate["route_sha256"] = baseline["route_sha256"]
    result = _call(baseline, candidate, 3, 3)
    assert result["accepted"] is True
    assert result["status"] == "publish_eligible"
    assert result["actual_layers"] == 3

    for kwargs, reason in (
        ({"actual": 2}, "layer_count_mismatch"),
        ({"quality": _quality(False)}, "quality_witness_not_accepted"),
        ({"quality": _quality(True, "other-profile")}, "quality_witness_profile_mismatch"),
        ({"authority": False}, "authority_incomplete"),
        ({"receipt": False}, "stage_publish_receipt_missing"),
        ({"topology": _topology(inverted=1)}, "topology_nonzero:inverted"),
    ):
        actual = kwargs.pop("actual", 3)
        refused = _call(baseline, candidate, 3, actual, **kwargs)
        assert refused["accepted"] is False
        assert refused["actual_layers"] == 0
        assert reason in refused["reasons"]


def test_invalid_digest_and_identity_state_are_fail_closed_and_deterministic() -> None:
    baseline = _record()
    bad = copy.deepcopy(baseline)
    bad["source_sha256"] = "A" * 64
    first = _call(baseline, bad, 0, 0)
    second = _call(baseline, bad, 0, 0)
    assert first == second
    assert first["accepted"] is False
    assert "record_invalid_digest:source_sha256" in first["reasons"]
