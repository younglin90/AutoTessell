from __future__ import annotations

from copy import deepcopy

import numpy as np

from core.generator.native_tet.admission import admit_candidate
from core.generator.native_tet.full_ledger import _graph_digest
from tests.test_native_tet_full_ledger import _payload


def _positive_policy() -> dict[str, object]:
    return {
        "min_signed_volume": 0.1,
        "min_scaled_jacobian": 0.3,
        "max_skewness": 0.4,
        "max_non_orthogonality": 40.0,
        "max_aspect_ratio": 1.5,
        "policy_sha256": "d" * 64,
    }


def _authority() -> dict[str, str]:
    return {
        "source_sha256": "a" * 64,
        "semantic_ledger_sha256": "b" * 64,
    }


def _mesh() -> tuple[np.ndarray, np.ndarray]:
    return (
        np.asarray(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        ),
        np.asarray([[0, 1, 2, 3]], dtype=np.int64),
    )


def test_python_bridge_requires_and_verifies_full_ledger_before_cpp_gate() -> None:
    points, tets = _mesh()
    result = admit_candidate(
        points,
        tets,
        np.empty((0, 3), dtype=np.int64),
        _positive_policy(),
        1,
        ledger=_payload(),
        authority=_authority(),
    )

    assert result["accepted"] is True
    assert result["status"] == "candidate_admitted"
    assert result["ledger_verification"]["accepted"] is True
    assert result["publication_eligible"] is False


def test_python_bridge_refuses_ledger_inverse_loss_before_geometry() -> None:
    points, tets = _mesh()
    ledger = deepcopy(_payload())
    del ledger["inverse"]["tet_to_prism"]["c2"]
    ledger["graph_sha256"] = _graph_digest(ledger)

    result = admit_candidate(
        points,
        tets,
        np.empty((0, 3), dtype=np.int64),
        _positive_policy(),
        1,
        ledger=ledger,
        authority=_authority(),
    )

    assert result["accepted"] is False
    assert result["candidate_discarded"] is True
    assert result["refusal_stage"] == "ledger"
    assert "tet_inverse_coverage_mismatch" in result["ledger_verification"]["errors"]

