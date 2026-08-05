"""L0 hand fixtures for the runtime-disconnected volume BL certificate."""
from __future__ import annotations

import copy

from core.layers.native_bl_atomic_certificate import (
    BLCandidate,
    GeneratedEntities,
    QualityTuple,
    SourceAuthority,
    TopologyChecks,
    VolumeLineage,
    certify,
    certify_and_persist,
)


def _source() -> tuple[dict[str, object], SourceAuthority]:
    return ({"points": [[0, 0, 0]], "cells": ["tet-0"]}, SourceAuthority(
        topology="topo-1", source="source-1", feature="feature-1", patch="wall",
        physical_group="wall-group", provenance="ledger-1", wall_faces=("wall-face-0",),
    ))


def _candidate(source: SourceAuthority, output: dict[str, object]) -> BLCandidate:
    generated = GeneratedEntities(("v-1",), ("f-1",), ("c-1",), ("tet",))
    return BLCandidate(
        kind="volume", requested_layers=1, actual_layers=1, first_height=0.01,
        growth_ratio=1.0, product_type="pure_tet", authority=source,
        topology=TopologyChecks(), generated=generated, output=output,
        quality=QualityTuple(min_jacobian=0.5, min_volume=0.1, count_error=99),
        volume_lineage=(VolumeLineage("wall-face-0", 1, ("v-1",), ("f-1",), ("c-1",)),),
    )


def test_bl0_is_byte_identical_and_generates_no_lineage() -> None:
    output, authority = _source()
    candidate = BLCandidate(
        kind="volume", requested_layers=0, actual_layers=0, first_height=0.0,
        growth_ratio=0.0, product_type="pure_tet", authority=authority,
        topology=TopologyChecks(), generated=GeneratedEntities(), output=copy.deepcopy(output),
    )

    certificate = certify(output, authority, candidate)

    assert certificate.accepted
    assert certificate.source_sha256 == certificate.output_sha256
    assert certificate.requested_layers == certificate.actual_layers == 0


def test_volume_rejects_partial_layers_bad_topology_and_false_pure_tet() -> None:
    output, authority = _source()
    candidate = _candidate(authority, {"points": [[0, 0, 0], [0, 0, 1]]})
    candidate = BLCandidate(
        **{**candidate.__dict__, "actual_layers": 0, "topology": TopologyChecks(inverted=1),
           "generated": GeneratedEntities(("v-1",), ("f-1",), ("c-1",), ("prism",))}
    )

    certificate = certify(output, authority, candidate)

    assert not certificate.accepted
    assert {"layer_count_mismatch", "topology_inverted", "false_pure_tet_claim"} <= set(certificate.reasons)


def test_volume_persistence_failure_rolls_back_and_replay_is_deterministic() -> None:
    output, authority = _source()
    candidate = _candidate(authority, {"points": [[0, 0, 0], [0, 0, 1]], "cells": ["tet-1"]})
    destination = copy.deepcopy(output)
    before = copy.deepcopy(destination)

    def fail(_: object) -> None:
        raise OSError("injected persistence failure")

    failed = certify_and_persist(output, authority, candidate, destination, persist=fail)
    replay_a = certify(output, authority, candidate)
    replay_b = certify(output, authority, candidate)

    assert not failed.accepted and failed.rolled_back
    assert failed.reasons == ("persistence_failure",)
    assert destination == before == output
    assert replay_a.serialized() == replay_b.serialized()
    assert replay_a.quality_tuple[-1] == 99
