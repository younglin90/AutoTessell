from __future__ import annotations

from pathlib import Path

import pytest

from core.evaluator.native_evidence_pack_v2_writer import (
    write_native_evidence_pack_v2,
)


def _surface_run(layers: int, run_id: str, *, semantic: str = "feature") -> dict:
    points = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    front0, front1 = 0, 1
    if layers:
        points += [[0.0, 0.0, 0.1], [1.0, 0.0, 0.1]]
        front0, front1 = 3, 4
    return {
        "producer_run_id": run_id, "producer_run_nonce": run_id + "-nonce",
        "source_bytes": b"surface-source-v2",
        "baseline_bytes": b"baseline" if layers else b"surface-candidate-v2",
        "output_bytes": b"surface-candidate-v2",
        "points": points,
        "triangles": [[0, 1, 2]], "quads": [], "cells": [],
        "ledger": [{
            "source_face_id": "face-0", "source_edge": "edge-0",
            "feature_id": semantic, "patch_id": "patch-0",
            "physical_group": "fluid_wall", "component_id": "body-0",
            "orientation": "forward", "provenance": "direct",
            "source_vertex_ids": [0, 1, 2],
        }],
        "boundary_binding": [{
            "source_face": "face-0", "source_edge": "edge-0",
            "wall_edge": "wall-0", "bl_strip": "strip-0",
            "output_boundary_face": "out-0", "volume_boundary_face": "vol-0",
            "feature": semantic, "patch": "patch-0",
            "physical_group": "fluid_wall", "component": "body-0",
            "orientation": "forward", "provenance": "direct",
            "wall0": 0, "wall1": 1, "front0": front0, "front1": front1,
            "tangent_face": "", "first_strip_face": "front-0",
        }],
    }


def _volume_run(layers: int, run_id: str, engine: str) -> dict:
    if engine == "native_hex":
        points = [[0., 0., 0.], [1., 0., 0.], [1., 1., 0.], [0., 1., 0.],
                  [0., 0., 1.], [1., 0., 1.], [1., 1., 1.], [0., 1., 1.]]
        face = [0, 1, 2, 3]
        cells = [[0, 1, 2, 3, 4, 5, 6, 7]]
    else:
        points = [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]
        face = [0, 1, 2]
        cells = [[0, 1, 2, 3]]
    front0, front1 = 0, 1
    if layers:
        base = len(points)
        points += [[points[0][0], points[0][1], points[0][2] + .1],
                   [points[1][0], points[1][1], points[1][2] + .1]]
        front0, front1 = base, base + 1
    return {
        "producer_run_id": run_id, "producer_run_nonce": run_id + "-nonce", "source_bytes": b"volume-source-v2",
        "baseline_bytes": b"baseline" if layers else b"volume-candidate-v2",
        "output_bytes": b"volume-candidate-v2", "points": points,
        "triangles": [face] if len(face) == 3 else [],
        "quads": [face] if len(face) == 4 else [], "cells": cells,
        "ledger": [{"source_face_id": "face-0", "source_edge": "edge-0",
                     "feature_id": "feature", "patch_id": "patch-0",
                     "physical_group": "fluid_wall", "component_id": "body-0",
                     "orientation": "forward", "provenance": "direct",
                     "source_vertex_ids": face}],
        "boundary_binding": [{"source_face": "face-0", "source_edge": "edge-0",
                               "wall_edge": "wall-0", "bl_strip": "strip-0",
                               "output_boundary_face": "out-0", "volume_boundary_face": "vol-0",
                               "feature": "feature", "patch": "patch-0",
                               "physical_group": "fluid_wall", "component": "body-0",
                               "orientation": "forward", "provenance": "direct",
                               "wall0": 0, "wall1": 1, "front0": front0, "front1": front1,
                               "tangent_face": "", "first_strip_face": "front-0"}],
    }


def _runs(layers: int, *, semantic: str = "feature", engine: str = "surface") -> list[dict]:
    if engine in {"native_tet", "native_hex", "native_poly"}:
        return [_volume_run(layers, f"producer-run-{index}", engine) for index in range(3)]
    return [_surface_run(layers, f"producer-run-{index}", semantic=semantic)
            for index in range(3)]


def test_writer_persists_actual_bl0_and_bl1_snapshots_atomically(tmp_path: Path):
    for layers in (0, 1):
        target = tmp_path / f"pack-{layers}"
        result = write_native_evidence_pack_v2(target, "surface", _runs(layers), layers)
        assert result["accepted"] is True, result
        assert result["authority_level"] == "L0_synthetic"
        assert result["publication_eligible"] is False
        assert result["run_count"] == 3
        assert (target / "evidence.atne").is_file()
        assert "native-l2-persisted-evidence/v2" in (target / "evidence.atne").read_text()


def test_writer_consumes_actual_tri_quad_transaction_snapshots(tmp_path: Path):
    from tests.test_native_tri_quad_actual_mixed_bl_transaction import (
        CO_NORMALS, POINTS, QUADS, SOURCE, TRIANGLES, WALL_LOOP, _receipt, _run,
    )

    runs = []
    for index in range(3):
        produced = _run(1)
        runs.append({
            "producer_run_id": f"tri-quad-run-{index}", "producer_run_nonce": f"tri-quad-nonce-{index}",
            "source_bytes": SOURCE,
            "baseline_bytes": b"tri-quad-baseline",
            "output_bytes": b"tri-quad-candidate",
            "points": produced["points"], "triangles": produced["triangles"],
            "quads": produced["quads"], "cells": [],
            "ledger": [
                {"source_face_id": "t0", "source_edge": "edge-t0", "feature_id": "wall",
                 "patch_id": "wall-1", "physical_group": "fluid_wall", "component_id": "body-1",
                 "orientation": "forward", "provenance": "direct", "source_vertex_ids": [4, 5, 6]},
                {"source_face_id": "q0", "source_edge": "edge-q0", "feature_id": "wall",
                 "patch_id": "wall-1", "physical_group": "fluid_wall", "component_id": "body-1",
                 "orientation": "forward", "provenance": "direct", "source_vertex_ids": [0, 1, 3, 2]},
            ],
            "boundary_binding": [
                {"source_face": "t0", "source_edge": "edge-t0", "wall_edge": "wall-t0", "bl_strip": "strip-t0",
                 "output_boundary_face": "out-t0", "volume_boundary_face": "vol-t0", "feature": "wall",
                 "patch": "wall-1", "physical_group": "fluid_wall", "component": "body-1",
                 "orientation": "forward", "provenance": "direct", "wall0": 0, "wall1": 1,
                 "front0": 7, "front1": 8, "tangent_face": "", "first_strip_face": "front-t0"},
                {"source_face": "q0", "source_edge": "edge-q0", "wall_edge": "wall-q0", "bl_strip": "strip-q0",
                 "output_boundary_face": "out-q0", "volume_boundary_face": "vol-q0", "feature": "wall",
                 "patch": "wall-1", "physical_group": "fluid_wall", "component": "body-1",
                 "orientation": "forward", "provenance": "direct", "wall0": 0, "wall1": 1,
                 "front0": 7, "front1": 8, "tangent_face": "", "first_strip_face": "front-q0"},
            ],
        })
    result = write_native_evidence_pack_v2(tmp_path / "tri-quad-pack", "tri_quad", runs, 1)
    assert result["accepted"] is True, result


@pytest.mark.parametrize("engine", ("native_tet", "native_hex", "native_poly", "native_tri", "strict_quad", "tri_quad", "surface"))
@pytest.mark.parametrize("layers", (0, 1, 3))
def test_writer_private_seven_product_bl_matrix(tmp_path: Path, engine: str, layers: int):
    result = write_native_evidence_pack_v2(tmp_path / f"{engine}-{layers}", engine, _runs(layers, engine=engine), layers)
    assert result["accepted"] is True, result
    assert result["engine"] == engine
    assert result["requested_layers"] == result["actual_layers"] == layers


def test_writer_refuses_copied_run_identity_semantics_and_nonempty_target(tmp_path: Path):
    runs = _runs(1)
    runs[1]["producer_run_id"] = runs[0]["producer_run_id"]
    result = write_native_evidence_pack_v2(tmp_path / "duplicate", "surface", runs, 1)
    assert result["accepted"] is False
    assert result["reason"] == "writer_run_identity_invalid"
    assert not (tmp_path / "duplicate").exists()

    target = tmp_path / "existing"
    target.mkdir()
    result = write_native_evidence_pack_v2(target, "surface", _runs(0), 0)
    assert result["accepted"] is False
    assert result["reason"] == "writer_target_nonempty"

    tampered = _runs(1)
    tampered[0]["boundary_binding"][0]["feature"] = "wrong"
    result = write_native_evidence_pack_v2(tmp_path / "tampered", "surface", tampered, 1)
    assert result["accepted"] is False
    assert result["reason"] == "writer_run_content_mismatch"
    assert not (tmp_path / "tampered").exists()
