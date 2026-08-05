from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pytest

from core.evaluator.native_l2_evidence_audit import audit_native_l2_persisted_evidence


ENGINES = (
    "native_tet", "native_hex", "native_poly", "native_tri",
    "strict_quad", "tri_quad", "surface",
)


def _write(path: Path, text: str | bytes) -> bytes:
    raw = text if isinstance(text, bytes) else text.encode()
    path.write_bytes(raw)
    return raw


def _geometry(engine: str, layers: int):
    front = layers > 0
    if engine in {"native_tet", "native_poly"}:
        points = [(0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (0., 0., 1.)]
        triangles = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
        quads, cells = [], [(0, 1, 2, 3)]
        wall_edges = [(0, 2), (0, 1), (0, 3), (1, 2)]
    elif engine == "native_hex":
        points = [
            (0., 0., 0.), (1., 0., 0.), (1., 1., 0.), (0., 1., 0.),
            (0., 0., 1.), (1., 0., 1.), (1., 1., 1.), (0., 1., 1.),
        ]
        triangles = []
        quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                 (3, 7, 6, 2), (0, 4, 7, 3), (1, 2, 6, 5)]
        cells, wall_edges = [(0, 1, 2, 3, 4, 5, 6, 7)], [(0, 3), (4, 5), (0, 1), (3, 7), (0, 4), (1, 2)]
    elif engine == "strict_quad":
        points = [(0., 0., 0.), (1., 0., 0.), (1., 1., 0.), (0., 1., 0.)]
        triangles, quads, cells, wall_edges = [], [(0, 1, 2, 3)], [], [(0, 1)]
    elif engine == "tri":
        points = [(0., 0., 0.), (1., 0., 0.), (0., 1., 0.)]
        triangles, quads, cells, wall_edges = [(0, 1, 2)], [], [], [(0, 1)]
    else:
        points = [(0., 0., 0.), (1., 0., 0.), (0., 1., 0.),
                  (3., 0., 0.), (4., 0., 0.), (4., 1., 0.), (3., 1., 0.)]
        triangles, quads, cells, wall_edges = [(0, 1, 2)], [(3, 4, 5, 6)], [], [(0, 1), (3, 4)]
    face_rows = list(triangles) + list(quads)
    if front:
        base = len(points)
        front_edges = []
        for i, (a, b) in enumerate(wall_edges):
            face = face_rows[i % len(face_rows)]
            p0, p1, p2 = (points[face[0]], points[face[1]], points[face[2]])
            u = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
            v = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
            if len(face) == 4:
                p3 = points[face[3]]
                v = (p3[0] - p0[0], p3[1] - p0[1], p3[2] - p0[2])
            n = (u[1] * v[2] - u[2] * v[1],
                 u[2] * v[0] - u[0] * v[2],
                 u[0] * v[1] - u[1] * v[0])
            length = math.sqrt(sum(value * value for value in n))
            n = tuple(value / length for value in n)
            points.extend([(points[a][0] + .1 * n[0], points[a][1] + .1 * n[1], points[a][2] + .1 * n[2]),
                           (points[b][0] + .1 * n[0], points[b][1] + .1 * n[1], points[b][2] + .1 * n[2])])
            front_edges.append((base + 2 * i, base + 2 * i + 1))
    else:
        front_edges = [(a, b) for a, b in wall_edges]
    return points, triangles, quads, cells, wall_edges, front_edges


def _make_pack(root: Path, engine: str, layers: int) -> Path:
    root.mkdir()
    points, triangles, quads, cells, wall_edges, front_edges = _geometry(engine, layers)
    face_rows = list(triangles) + list(quads)
    source = f"source-{engine}-v2".encode()
    output = f"output-{engine}-bl{layers}-v2".encode()
    baseline = hashlib.sha256(b"baseline").hexdigest()
    candidate = hashlib.sha256(output if layers else b"baseline").hexdigest()
    point_raw = "\n".join("%.17g %.17g %.17g" % p for p in points) + "\n"
    tri_raw = "\n".join(" ".join(map(str, row)) for row in triangles) + ("\n" if triangles else "")
    quad_raw = "\n".join(" ".join(map(str, row)) for row in quads) + ("\n" if quads else "")
    cell_raw = "\n".join(" ".join(map(str, row)) for row in cells) + ("\n" if cells else "")
    geom_digest = hashlib.sha256((point_raw + tri_raw + quad_raw + cell_raw).encode()).hexdigest()
    source_face_ids = []
    ledger_rows = []
    binding_rows = []
    for i, face in enumerate(face_rows):
        face_id = f"face-{i}"
        source_face_ids.append(face_id)
        ledger_rows.append("\t".join((face_id, f"edge-{i}", "feature", "patch",
                                      "fluid", "component", "forward",
                                      ",".join(map(str, face)), "direct")))
        w0, w1 = wall_edges[i % len(wall_edges)]
        f0, f1 = front_edges[i % len(front_edges)]
        binding_rows.append("\t".join((face_id, "", "", f"edge-{i}", f"wall-{i}",
                                       f"strip-{i}", f"out-{i}", f"vol-{i}",
                                       "feature", "patch", "fluid", "component", "direct",
                                       str(w0), str(w1), str(f0), str(f1), "", f"front-{i}",
                                       "forward", "0", "0", "0")))
    _write(root / "source.bin", source)
    _write(root / "output.bin", output)
    for i in range(1, 4):
        _write(root / f"run_output_{i}.bin", output)
    _write(root / "points.txt", point_raw)
    _write(root / "triangles.txt", tri_raw)
    _write(root / "quads.txt", quad_raw)
    _write(root / "cells.txt", cell_raw)
    _write(root / "ledger.tsv", "\n".join(ledger_rows) + ("\n" if ledger_rows else ""))
    _write(root / "binding.tsv", "\n".join(binding_rows) + ("\n" if binding_rows else ""))
    source_digest = hashlib.sha256(source).hexdigest()
    output_digest = hashlib.sha256(output).hexdigest()
    fields = {
        "schema": "native-l2-persisted-evidence/v2",
        "engine": engine,
        "authority_level": "L0_synthetic",
        "source_path": "source.bin", "output_path": "output.bin",
        "points_path": "points.txt", "triangles_path": "triangles.txt",
        "quads_path": "quads.txt", "cells_path": "cells.txt",
        "ledger_path": "ledger.tsv", "binding_path": "binding.tsv",
        "run_output_1": "run_output_1.bin", "run_output_2": "run_output_2.bin",
        "run_output_3": "run_output_3.bin", "source_sha256": source_digest,
        "output_sha256": output_digest, "geometry_sha256": geom_digest,
        "build_sha256": "b" * 64, "config_sha256": "c" * 64,
        "baseline_digest": baseline if layers else output_digest,
        "candidate_digest": candidate if layers else output_digest,
        "requested_layers": str(layers), "actual_layers": str(layers),
        "bl0_exact_identity": "true" if layers == 0 else "false",
        "thickness_monotone": "true", "growth_ratio_error": "0.0",
        "total_thickness": "0.1" if layers else "0.0",
    }
    _write(root / "evidence.atne", "\n".join(f"{k}={v}" for k, v in fields.items()) + "\n")
    return root


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("layers", (0, 1, 3))
def test_v2_replays_all_products_and_bl_modes(tmp_path: Path, engine: str, layers: int):
    result = audit_native_l2_persisted_evidence(str(_make_pack(tmp_path / "pack", engine, layers)))
    assert result["accepted"] is True, (engine, layers, result)
    assert result["evidence_pack_schema"] == "native-l2-persisted-evidence/v2"
    assert result["authority_level"] == "L0_synthetic"
    assert result["publication_eligible"] is False
    assert result["requested_layers"] == result["actual_layers"] == layers
    assert result["topology"]["duplicate"] == 0
    assert result["topology"]["non_manifold"] == 0
    assert result["topology"]["inverted"] == 0
    assert result["topology"]["degenerate"] == 0


def test_v2_rejects_raw_geometry_semantic_and_run_tamper(tmp_path: Path):
    root = _make_pack(tmp_path / "pack", "surface", 1)
    (root / "output.bin").write_bytes(b"tampered")
    result = audit_native_l2_persisted_evidence(str(root))
    assert result["accepted"] is False
    assert result["atomic_rollback"] is True
    assert result["candidate_discarded"] is True

    root = _make_pack(tmp_path / "pack2", "surface", 1)
    text = (root / "binding.tsv").read_text()
    (root / "binding.tsv").write_text(text.replace("feature\tpatch", "wrong\tpatch", 1))
    result = audit_native_l2_persisted_evidence(str(root))
    assert result["accepted"] is False
    assert result["atomic_rollback"] is True

    root = _make_pack(tmp_path / "pack3", "surface", 1)
    (root / "run_output_2.bin").write_bytes(b"different-run")
    result = audit_native_l2_persisted_evidence(str(root))
    assert result["accepted"] is False
    assert result["reason"] == "persisted_run_repeatability_mismatch"


def test_v2_rejects_path_escape_and_missing_authority(tmp_path: Path):
    root = _make_pack(tmp_path / "pack", "surface", 0)
    text = (root / "evidence.atne").read_text()
    (root / "evidence.atne").write_text(text.replace("points_path=points.txt", "points_path=../points.txt"))
    result = audit_native_l2_persisted_evidence(str(root))
    assert result["accepted"] is False
    assert result["reason"] == "persisted_geometry_path_invalid"

    root = _make_pack(tmp_path / "pack2", "surface", 0)
    text = "\n".join(line for line in (root / "evidence.atne").read_text().splitlines()
                        if not line.startswith("authority_level=")) + "\n"
    (root / "evidence.atne").write_text(text)
    result = audit_native_l2_persisted_evidence(str(root))
    assert result["accepted"] is False
    assert result["reason"] == "persisted_authority_level_missing"
