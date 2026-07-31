"""Policy-evidence-only tests for native-tet strict-overlap records."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from core.generator.native_tet.initial_overlap_source_l1 import (
    InitialStrictOverlapSourceRecord,
    capture_initial_strict_overlap_source_l1,
)
from core.generator.native_tet.strict_overlap_policy_l0 import (
    StrictOverlapPolicyDisposition,
    evaluate_strict_overlap_policy_l0,
)

_ROOT = Path(__file__).resolve().parents[1]
_INITIAL_OVERLAP_WORKER = _ROOT / "tests" / "test_native_tet_initial_overlap_source_l1.py"
_L1_TIMEOUT_SECONDS = 480


def _two_tet_surface(second_apex_z: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points = np.asarray(
        (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (0.25, 0.25, second_apex_z),
        ),
        dtype=np.float64,
    )
    source_faces = np.asarray(
        ((0, 1, 3), (0, 3, 2), (1, 2, 3), (0, 2, 4), (0, 4, 1), (2, 1, 4)),
        dtype=np.int64,
    )
    tets = np.asarray(((0, 1, 2, 3), (0, 2, 1, 4)), dtype=np.int64)
    return points, source_faces, tets


def _record(second_apex_z: float) -> InitialStrictOverlapSourceRecord:
    points, source_faces, tets = _two_tet_surface(second_apex_z)
    return capture_initial_strict_overlap_source_l1(
        fixture="two_tet",
        repeat=0,
        audit_call_index=0,
        source_points=points,
        source_faces=source_faces,
        candidate_points=points,
        candidate_tets=tets,
    )


def test_l0_same_side_with_exact_source_provenance_is_explicitly_unrelaxable() -> None:
    record = _record(1.0)
    evidence = evaluate_strict_overlap_policy_l0(record)

    assert record.source_faces_preserved
    assert record.n_same_side_internal_faces == 1
    assert evidence.disposition is StrictOverlapPolicyDisposition.UNRELAXABLE_SAME_SIDE
    assert evidence.reason == "same_side_overlap_with_source_provenance_preserved"
    assert not evidence.future_calibration_eligible
    assert evidence.runtime_classification_unchanged
    assert not evidence.runtime_relaxation_authorized


def test_l0_ambiguity_is_only_future_calibration_evidence_not_permission() -> None:
    record = _record(1.0e-15)
    evidence = evaluate_strict_overlap_policy_l0(record)

    assert record.n_same_side_internal_faces == 0
    assert record.n_ambiguous_internal_faces == 1
    assert evidence.disposition is StrictOverlapPolicyDisposition.FUTURE_CALIBRATION_ELIGIBLE
    assert evidence.future_calibration_eligible
    assert evidence.runtime_classification_unchanged
    assert not evidence.runtime_relaxation_authorized


def test_l0_provenance_debt_is_not_reclassified_as_a_threshold_problem() -> None:
    record = replace(
        _record(-1.0),
        source_faces_preserved=False,
        n_overlap_pairs=1,
        overlap_source_class="planar_patch_overlap_without_same_side_overlap",
    )
    evidence = evaluate_strict_overlap_policy_l0(record)

    assert evidence.disposition is StrictOverlapPolicyDisposition.PROVENANCE_REPAIR_REQUIRED
    assert not evidence.future_calibration_eligible
    assert evidence.runtime_classification_unchanged
    assert not evidence.runtime_relaxation_authorized


def test_l0_provenance_debt_precedes_ambiguity_calibration_eligibility() -> None:
    record = replace(
        _record(1.0e-15),
        source_faces_preserved=False,
        n_overlap_pairs=1,
        overlap_source_class="strict_ambiguity_with_source_provenance_debt",
    )
    evidence = evaluate_strict_overlap_policy_l0(record)

    assert record.n_same_side_internal_faces == 0
    assert record.n_ambiguous_internal_faces == 1
    assert evidence.disposition is StrictOverlapPolicyDisposition.PROVENANCE_REPAIR_REQUIRED
    assert not evidence.future_calibration_eligible
    assert evidence.runtime_classification_unchanged
    assert not evidence.runtime_relaxation_authorized


def _run_initial_overlap_worker(
    tmp_path: Path, fixture_name: str, repeat: int
) -> dict[str, object]:
    evidence = tmp_path / f"{fixture_name}_{repeat}.json"
    case_dir = tmp_path / f"{fixture_name}_{repeat}"
    command = [
        sys.executable,
        str(_INITIAL_OVERLAP_WORKER),
        "--worker",
        fixture_name,
        str(repeat),
        str(case_dir),
        str(evidence),
    ]
    environment = dict(os.environ)
    prior_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = (
        str(_ROOT) if not prior_pythonpath else f"{_ROOT}:{prior_pythonpath}"
    )
    try:
        completed = subprocess.run(
            command,
            cwd=_ROOT,
            check=False,
            capture_output=True,
            env=environment,
            text=True,
            timeout=_L1_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        pytest.fail(
            f"L1 strict-overlap policy worker timed out after {_L1_TIMEOUT_SECONDS}s "
            f"for {fixture_name} repeat {repeat}; evidence is UNVERIFIED: {error}"
        )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(evidence.read_text(encoding="utf-8"))


def _record_from_payload(value: object) -> InitialStrictOverlapSourceRecord | None:
    if value is None:
        return None
    assert isinstance(value, dict)
    return InitialStrictOverlapSourceRecord(**value)


@pytest.mark.parametrize("fixture_name", ("cube", "sphere"))
def test_l1_policy_evidence_is_deterministic_and_keeps_writer_refusal(
    fixture_name: str, tmp_path: Path
) -> None:
    payloads = tuple(
        _run_initial_overlap_worker(tmp_path, fixture_name, repeat) for repeat in range(3)
    )
    policies = tuple(
        evaluate_strict_overlap_policy_l0(_record_from_payload(payload["first_strict_overlap"]))
        for payload in payloads
    )

    for payload, policy in zip(payloads, policies, strict=True):
        result = payload["result"]
        assert isinstance(result, dict)
        assert result["success"] is False
        assert result["writer_artifact_exists"] is False
        assert policy.runtime_classification_unchanged
        assert not policy.runtime_relaxation_authorized
    assert policies == (policies[0], policies[0], policies[0])
    if fixture_name == "cube":
        result = payloads[0]["result"]
        assert isinstance(result, dict)
        assert result["message"] == "native_tet CVT candidate increases strict internal-face debt"
        assert result["n_cells"] == 5913
