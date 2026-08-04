from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

native_witness = pytest.importorskip("native_quality_witness")

sys.path.insert(0, str(Path(__file__).parent))
from test_native_quality_witness_v3_cpp23 import _authority, _cube_snapshot, _policy  # noqa: E402


def test_candidate_reread_requires_same_policy_and_authority() -> None:
    sealed = native_witness.seal_policy_v3(_policy(0))
    candidate = native_witness.evaluate_v3(_cube_snapshot(0), _authority(), sealed, "candidate")
    reread = native_witness.evaluate_v3(_cube_snapshot(0), _authority(), sealed, "reread")
    assert native_witness.compare_candidate_reread_v3(candidate, reread)["candidate_disk_parity"] is True

    changed_policy = native_witness.seal_policy_v3({**_policy(0), "target_cells": 100})
    changed = native_witness.evaluate_v3(_cube_snapshot(0), _authority(), changed_policy, "reread")
    refused_policy = native_witness.compare_candidate_reread_v3(candidate, changed)
    assert refused_policy["accepted"] is False
    assert refused_policy["reason"] == "quality_candidate_disk_digest_mismatch"

    changed_authority = copy.deepcopy(reread)
    changed_authority["source_sha256"] = "e" * 64
    refused_authority = native_witness.compare_candidate_reread_v3(candidate, changed_authority)
    assert refused_authority["accepted"] is False
    assert refused_authority["reason"] == "quality_candidate_disk_digest_mismatch"


def test_candidate_reread_refuses_entity_set_or_metric_tampering() -> None:
    sealed = native_witness.seal_policy_v3(_policy(0))
    candidate = native_witness.evaluate_v3(_cube_snapshot(0), _authority(), sealed, "candidate")
    reread = native_witness.evaluate_v3(_cube_snapshot(0), _authority(), sealed, "reread")

    entity_tampered = copy.deepcopy(reread)
    entity_tampered["face_uids"][-1] = "face-tampered"
    refused_entity = native_witness.compare_candidate_reread_v3(candidate, entity_tampered)
    assert refused_entity["accepted"] is False
    assert refused_entity["reason"] == "quality_candidate_disk_entity_set_mismatch"

    metric_tampered = copy.deepcopy(reread)
    metric_tampered["quality"]["aspect_ratio"]["max"] += 1.0e-5
    refused_metric = native_witness.compare_candidate_reread_v3(candidate, metric_tampered)
    assert refused_metric["accepted"] is False
    assert refused_metric["reason"] == "quality_candidate_disk_metric_mismatch"
