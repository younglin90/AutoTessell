"""L0 hand fixtures for the future surface wall-edge BL certificate."""
from __future__ import annotations

import copy

from core.layers.native_bl_atomic_certificate import (
    BLCandidate,
    GeneratedEntities,
    QualityTuple,
    SourceAuthority,
    SurfaceLineage,
    TopologyChecks,
    certify,
    certify_and_persist,
)


def _source() -> tuple[dict[str, object], SourceAuthority]:
    return ({"vertices": [[0, 0, 0], [1, 0, 0]], "faces": ["wall-face"]}, SourceAuthority(
        topology="surface-topo", source="surface-source", feature="ridge-lock", patch="wall",
        physical_group="wall-group", provenance="surface-ledger", wall_edges=("wall-edge-0",),
    ))


def _candidate(authority: SourceAuthority, output: dict[str, object]) -> BLCandidate:
    return BLCandidate(
        kind="surface", requested_layers=1, actual_layers=1, first_height=0.02,
        growth_ratio=1.2, product_type="mixed_prism_shell", authority=authority,
        topology=TopologyChecks(), generated=GeneratedEntities(("v-1",), ("f-1",)), output=output,
        quality=QualityTuple(min_area=0.2, min_jacobian=0.1),
        surface_lineage=(SurfaceLineage("wall-edge-0", 1, ("v-1",), ("f-1",)),),
    )


def test_surface_accepts_wall_edge_lineage_without_claiming_cells() -> None:
    output, authority = _source()
    certificate = certify(output, authority, _candidate(authority, {"faces": ["wall-face", "strip-face"]}))

    assert certificate.accepted
    assert certificate.actual_layers == 1


def test_surface_rejects_authority_mismatch_and_non_positive_area() -> None:
    output, authority = _source()
    wrong = SourceAuthority(**{**authority.__dict__, "patch": "not-wall"})
    candidate = _candidate(wrong, {"faces": ["wall-face", "strip-face"]})
    candidate = BLCandidate(**{**candidate.__dict__, "quality": QualityTuple(min_area=0.0)})

    certificate = certify(output, authority, candidate)

    assert not certificate.accepted
    assert {"source_authority_mismatch", "non_positive_min_area"} <= set(certificate.reasons)


def test_surface_persistence_failure_rolls_back_and_replay_is_deterministic() -> None:
    output, authority = _source()
    candidate = _candidate(authority, {"faces": ["wall-face", "strip-face"]})
    destination = copy.deepcopy(output)

    def fail(_: object) -> None:
        raise RuntimeError("injected persistence failure")

    failed = certify_and_persist(output, authority, candidate, destination, persist=fail)
    replay = [certify(output, authority, candidate).serialized() for _ in range(2)]

    assert not failed.accepted and failed.rolled_back
    assert destination == output
    assert replay[0] == replay[1]
