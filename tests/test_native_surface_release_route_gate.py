from __future__ import annotations

from core.evaluator.native_surface_release_route import admit_authoritative_surface_release


def _digest(seed: str) -> str:
    seed = {"p": "1", "g": "2", "h": "3", "i": "4", "j": "5"}.get(seed, seed)
    return (seed * 64)[:64]


def _source() -> dict[str, str]:
    return {"raw_sha256": _digest("a"), "semantic_ledger_sha256": _digest("b"), "provenance_sha256": _digest("c")}


def _candidate(**updates: object) -> dict[str, object]:
    result: dict[str, object] = {
        "accepted": True,
        "candidate_discarded": False,
        "runtime_route": "native_surface_authority_bound",
        "publication_eligible": True,
        "source_authority_bound": True,
        "authority_checked": True,
        "transaction_atomic": True,
        "actual_layers": 1,
        "provenance": [{"source_wall_edge": "e0", "layer": 1}],
        "topology_invalid": 0,
        "topology_inverted": 0,
        "topology_duplicate": 0,
        "topology_non_manifold": 0,
        "source_digest": _digest("d"),
        "output_digest": _digest("e"),
    }
    result.update(updates)
    return result


def _package(candidate: dict[str, object]) -> dict[str, object]:
    return {
        "package_digest": _digest("f"),
        "output_geometry_sha256": _digest("g"),
        "output_topology_sha256": _digest("h"),
        "quality_receipt_sha256": _digest("i"),
        "parameter_sha256": _digest("j"),
        "atomic": True,
        "fsynced": True,
        "source_digest": candidate["source_digest"],
        "output_digest": candidate["output_digest"],
    }


def test_default_off_candidate_is_not_a_release_route() -> None:
    result = admit_authoritative_surface_release(
        _candidate(runtime_route="default_off"),
        source_certificate=_source(), parameter_digest=_digest("p"),
        packaging_receipt=_package(_candidate()), requested_layers=1,
        explicit_route=True,
    )
    assert result["accepted"] is False
    assert result["reason"] == "candidate_route_default_off"
    assert result["release_eligible"] is False


def test_missing_package_digest_refuses_atomically() -> None:
    candidate = _candidate()
    package = _package(candidate)
    package["quality_receipt_sha256"] = "missing"
    result = admit_authoritative_surface_release(
        candidate, source_certificate=_source(), parameter_digest=_digest("p"),
        packaging_receipt=package, requested_layers=1, explicit_route=True,
    )
    assert result["accepted"] is False
    assert result["reason"] == "packaging_receipt_incomplete"
    assert result["candidate_discarded"] is True


def test_complete_contract_is_admitted_without_threshold_relaxation() -> None:
    candidate = _candidate()
    result = admit_authoritative_surface_release(
        candidate, source_certificate=_source(), parameter_digest=_digest("p"),
        packaging_receipt=_package(candidate), requested_layers=1,
        explicit_route=True,
    )
    assert result["accepted"] is True
    assert result["release_eligible"] is True
    assert result["runtime_route"] == "native_surface_authority_bound"
