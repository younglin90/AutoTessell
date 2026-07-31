"""L1 isolated test instrumentation for strict same-side mutation markers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from core.generator.native_tet.mutation_boundary_marker_l1 import (
    NamedMutationBoundaryMarker,
    marker_from_arrays_l1,
    metadata_for_strict_audit_call_l1,
)
from core.generator.native_tet.same_side_mutation_attribution_l0 import (
    MutationPhase,
    SameSideAuditCallMetadata,
    SameSideMutationAttribution,
)

_ROOT = Path(__file__).resolve().parents[1]
_CUBE = _ROOT / "tests" / "benchmarks" / "cube.stl"
_SPHERE = _ROOT / "tests" / "benchmarks" / "sphere.stl"
_L1_TIMEOUT_SECONDS = 480


def _arrays(offset: float) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(
        ((0.0 + offset, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        dtype=np.float64,
    )
    tets = np.asarray(((0, 1, 2, 3),), dtype=np.int64)
    return points, tets


def test_l0_exact_pre_post_marker_never_labels_unrelated_or_unchanged_arrays() -> None:
    pre_points, tets = _arrays(0.0)
    post_points, _ = _arrays(0.1)
    marker = marker_from_arrays_l1(
        "cvt3d_candidate_relocation", pre_points, tets, post_points, tets
    )
    assert marker is not None
    pre = metadata_for_strict_audit_call_l1(0, pre_points, tets, (marker,))
    post = metadata_for_strict_audit_call_l1(1, post_points, tets, (marker,))
    unrelated_points, _ = _arrays(0.2)
    unrelated = metadata_for_strict_audit_call_l1(2, unrelated_points, tets, (marker,))

    assert pre.mutation_phase is MutationPhase.PRE
    assert post.mutation_phase is MutationPhase.POST
    assert unrelated.mutation_phase is MutationPhase.UNATTRIBUTED
    assert unrelated.mutation_name is None
    assert marker_from_arrays_l1("noop", pre_points, tets, pre_points, tets) is None


def _worker_payload(fixture_name: str, repeat: int, case_dir: Path) -> dict[str, object]:
    if fixture_name == "cube":
        os.environ["AUTO_TESSELL_VVV2_QUEUE"] = "0"
        for name in (
            "AUTO_TESSELL_VVV5B_OFF",
            "AUTO_TESSELL_VVV6_OFF",
            "AUTO_TESSELL_VVV7_OFF",
            "AUTO_TESSELL_VVV8_OFF",
            "AUTO_TESSELL_VVV9_OFF",
            "AUTO_TESSELL_VVV10_OFF",
            "AUTO_TESSELL_VVV11_OFF",
            "AUTO_TESSELL_VVV12_OFF",
            "AUTO_TESSELL_VVV13_OFF",
            "AUTO_TESSELL_VVV14_OFF",
            "AUTO_TESSELL_TET_QUALITY1_OFF",
            "AUTO_TESSELL_STELLAR_KLINGNER",
        ):
            os.environ[name] = "1"
        os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "0"

    import core.generator.native_tet.cvt3d as cvt3d
    import core.generator.native_tet.rescue_gate as rescue_gate
    from core.analyzer.readers import read_stl
    from core.generator.native_tet.mesher import generate_native_tet
    from core.generator.native_tet.mutation_boundary_marker_l1 import (
        marker_from_arrays_l1,
        metadata_for_strict_audit_call_l1,
    )
    from core.generator.native_tet.same_side_mutation_attribution_l0 import (
        SameSideAuditCallMetadata,
        attribute_first_same_side_mutation_l0,
    )

    fixture = {"cube": _CUBE, "sphere": _SPHERE}[fixture_name]
    mesh = read_stl(fixture)
    markers: list[NamedMutationBoundaryMarker] = []
    events: list[SameSideAuditCallMetadata] = []
    original_cvt = cvt3d.lloyd_cvt_3d
    original_audit = rescue_gate.audit_internal_face_sidedness
    call_index = 0

    def traced_cvt(
        points: np.ndarray, tets: np.ndarray, *args: object, **kwargs: object
    ) -> tuple[np.ndarray, object]:
        candidate_points, result = original_cvt(points, tets, *args, **kwargs)
        marker = marker_from_arrays_l1(
            "cvt3d_candidate_relocation", points, tets, candidate_points, tets
        )
        if marker is not None:
            markers.append(marker)
        return candidate_points, result

    def traced_audit(
        points: np.ndarray, tets: np.ndarray, *args: object, **kwargs: object
    ) -> object:
        nonlocal call_index
        observed = original_audit(points, tets, *args, **kwargs)
        metadata = metadata_for_strict_audit_call_l1(
            call_index, points, tets, tuple(markers)
        )
        events.append(
            SameSideAuditCallMetadata(
                metadata.audit_call_index,
                observed.n_same_side_internal_faces,
                metadata.mutation_name,
                metadata.mutation_phase,
            )
        )
        call_index += 1
        return observed

    cvt3d.lloyd_cvt_3d = traced_cvt
    rescue_gate.audit_internal_face_sidedness = traced_audit
    try:
        kwargs: dict[str, object] = {"target_cells": 2000}
        if fixture_name == "sphere":
            kwargs.update(
                enable_bsp_insertion=False,
                enable_edge_recovery=False,
                enable_phase_b=False,
                enable_phase_c=False,
            )
        result = generate_native_tet(
            np.asarray(mesh.vertices, dtype=np.float64),
            np.asarray(mesh.faces, dtype=np.int64),
            case_dir,
            **kwargs,
        )
    finally:
        cvt3d.lloyd_cvt_3d = original_cvt
        rescue_gate.audit_internal_face_sidedness = original_audit

    attribution = attribute_first_same_side_mutation_l0(tuple(events))
    return {
        "fixture": fixture_name,
        "repeat": repeat,
        "result": {
            "success": result.success,
            "message": result.message,
            "n_cells": result.n_cells,
            "writer_artifact_exists": (case_dir / "constant" / "polyMesh").exists(),
        },
        "markers": [marker.as_json() for marker in markers],
        "attribution": attribution.as_json(),
    }


def _run_worker(tmp_path: Path, fixture_name: str, repeat: int) -> dict[str, object]:
    evidence = tmp_path / f"{fixture_name}_{repeat}.json"
    case_dir = tmp_path / f"{fixture_name}_{repeat}"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
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
            f"L1 mutation-marker worker timed out after {_L1_TIMEOUT_SECONDS}s "
            f"for {fixture_name} repeat {repeat}; evidence is UNVERIFIED: {error}"
        )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(evidence.read_text(encoding="utf-8"))


@pytest.mark.parametrize("fixture_name", ("cube", "sphere"))
def test_l1_test_only_cvt_marker_is_deterministic_and_preserves_refusal(
    fixture_name: str, tmp_path: Path
) -> None:
    payloads = tuple(_run_worker(tmp_path, fixture_name, repeat) for repeat in range(3))
    for payload in payloads:
        result = payload["result"]
        attribution = payload["attribution"]
        assert isinstance(result, dict) and isinstance(attribution, dict)
        assert result["success"] is False
        assert result["writer_artifact_exists"] is False
        assert attribution["runtime_classification_unchanged"] is True
        assert attribution["same_side_relaxation_authorized"] is False
    deterministic_payloads = tuple(
        {key: value for key, value in payload.items() if key != "repeat"}
        for payload in payloads
    )
    assert deterministic_payloads == (
        deterministic_payloads[0],
        deterministic_payloads[0],
        deterministic_payloads[0],
    )
    if fixture_name == "cube":
        assert payloads[0]["markers"]
        attribution = payloads[0]["attribution"]
        assert isinstance(attribution, dict)
        assert attribution["attribution"] in {
            SameSideMutationAttribution.POST_NAMED_NON_SOURCE_MUTATION,
            SameSideMutationAttribution.DEFER_INSUFFICIENT_MUTATION_METADATA,
        }


def _main() -> None:
    if len(sys.argv) != 6 or sys.argv[1] != "--worker":
        raise SystemExit(
            "usage: test_native_tet_mutation_boundary_marker_l1.py "
            "--worker fixture repeat case evidence"
        )
    fixture_name, repeat_text, case_text, evidence_text = sys.argv[2:]
    payload = _worker_payload(fixture_name, int(repeat_text), Path(case_text))
    Path(evidence_text).write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )


if __name__ == "__main__":
    _main()
