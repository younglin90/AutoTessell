"""Report-only evidence for named mutation attribution of strict same-side debt."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from core.generator.native_tet.initial_overlap_source_l1 import InitialStrictOverlapSourceRecord
from core.generator.native_tet.same_side_mutation_attribution_l0 import (
    MutationPhase,
    SameSideAuditCallMetadata,
    SameSideMutationAttribution,
    attribute_first_same_side_mutation_l0,
    metadata_from_initial_overlap_records,
)

_ROOT = Path(__file__).resolve().parents[1]
_INITIAL_OVERLAP_WORKER = _ROOT / "tests" / "test_native_tet_initial_overlap_source_l1.py"
_L1_TIMEOUT_SECONDS = 480


def test_l0_named_cvt_candidate_can_be_classified_pre_or_post_without_runtime_permission() -> None:
    pre = attribute_first_same_side_mutation_l0(
        (
            SameSideAuditCallMetadata(3, 0, "cvt3d_candidate_relocation", MutationPhase.PRE),
            SameSideAuditCallMetadata(4, 4, "cvt3d_candidate_relocation", MutationPhase.PRE),
        )
    )
    post = attribute_first_same_side_mutation_l0(
        (
            SameSideAuditCallMetadata(3, 0, "cvt3d_candidate_relocation", MutationPhase.PRE),
            SameSideAuditCallMetadata(4, 4, "cvt3d_candidate_relocation", MutationPhase.POST),
        )
    )

    assert pre.attribution is SameSideMutationAttribution.PRE_NAMED_NON_SOURCE_MUTATION
    assert post.attribution is SameSideMutationAttribution.POST_NAMED_NON_SOURCE_MUTATION
    assert pre.runtime_classification_unchanged and post.runtime_classification_unchanged
    assert not pre.same_side_relaxation_authorized
    assert not post.same_side_relaxation_authorized


def test_l0_missing_or_unattributed_marker_defers_instead_of_inventing_causality() -> None:
    evidence = attribute_first_same_side_mutation_l0(
        (SameSideAuditCallMetadata(7, 2, None, MutationPhase.UNATTRIBUTED),)
    )

    assert evidence.attribution is SameSideMutationAttribution.DEFER_INSUFFICIENT_MUTATION_METADATA
    assert evidence.audit_call_index == 7
    assert evidence.runtime_classification_unchanged
    assert not evidence.same_side_relaxation_authorized


@pytest.mark.parametrize(
    "event",
    (
        SameSideAuditCallMetadata(-1, 1, None, MutationPhase.UNATTRIBUTED),
        SameSideAuditCallMetadata(True, 1, None, MutationPhase.UNATTRIBUTED),
        SameSideAuditCallMetadata(1, -1, None, MutationPhase.UNATTRIBUTED),
        SameSideAuditCallMetadata(1, True, None, MutationPhase.UNATTRIBUTED),
        SameSideAuditCallMetadata(1, 1, "", MutationPhase.POST),
        SameSideAuditCallMetadata(1, 1, "cvt3d", MutationPhase.UNATTRIBUTED),
        SameSideAuditCallMetadata(1, 1, None, MutationPhase.PRE),
        replace(
            SameSideAuditCallMetadata(1, 1, "cvt3d", MutationPhase.POST),
            mutation_phase="post",  # type: ignore[arg-type]
        ),
    ),
)
def test_l0_malformed_mutation_metadata_fails_closed(event: SameSideAuditCallMetadata) -> None:
    with pytest.raises(ValueError):
        attribute_first_same_side_mutation_l0((event,))


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
            f"L1 same-side attribution worker timed out after {_L1_TIMEOUT_SECONDS}s "
            f"for {fixture_name} repeat {repeat}; evidence is UNVERIFIED: {error}"
        )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(evidence.read_text(encoding="utf-8"))


def _records_from_payload(value: object) -> tuple[InitialStrictOverlapSourceRecord, ...]:
    assert isinstance(value, list)
    return tuple(InitialStrictOverlapSourceRecord(**record) for record in value)


@pytest.mark.parametrize("fixture_name", ("cube", "sphere"))
def test_l1_existing_audit_metadata_defers_and_preserves_refusal(
    fixture_name: str, tmp_path: Path
) -> None:
    payloads = tuple(
        _run_initial_overlap_worker(tmp_path, fixture_name, repeat) for repeat in range(3)
    )
    evidence = tuple(
        attribute_first_same_side_mutation_l0(
            metadata_from_initial_overlap_records(_records_from_payload(payload["records"]))
        )
        for payload in payloads
    )

    for payload, result in zip(payloads, evidence, strict=True):
        generator_result = payload["result"]
        assert isinstance(generator_result, dict)
        assert generator_result["success"] is False
        assert generator_result["writer_artifact_exists"] is False
        assert result.attribution in {
            SameSideMutationAttribution.DEFER_INSUFFICIENT_MUTATION_METADATA,
            SameSideMutationAttribution.NO_SAME_SIDE_OBSERVED,
        }
        assert result.runtime_classification_unchanged
        assert not result.same_side_relaxation_authorized
    assert evidence == (evidence[0], evidence[0], evidence[0])
    if fixture_name == "cube":
        result = payloads[0]["result"]
        assert isinstance(result, dict)
        assert result["message"] == "native_tet CVT candidate increases strict internal-face debt"
        assert result["n_cells"] == 5913
