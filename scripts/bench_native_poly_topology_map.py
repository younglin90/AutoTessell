"""Map low-valence/orphan primal points to dual-ring geometry.

Diagnostic only.  No tet connectivity or point coordinate is changed.
"""

from __future__ import annotations

import json
import importlib.util
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np

os.environ.setdefault("AUTO_TESSELL_P4C_PYTETWILD", "0")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.analyzer.readers import read_stl  # noqa: E402
from core.generator.native_poly.dual import _build_tet_topology  # noqa: E402
from core.generator.native_tet.mesher import generate_native_tet  # noqa: E402

_TET_RESCUE = Path("/home/younglin90/work/claude_code/AutoTessell/core/generator/native_tet/rescue_gate.py")
_spec = importlib.util.spec_from_file_location("native_tet_rescue_gate_diag", _TET_RESCUE)
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load {_TET_RESCUE}")
_rescue_gate = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _rescue_gate
_spec.loader.exec_module(_rescue_gate)
audit_tet_boundary = _rescue_gate.audit_tet_boundary


def _boundary_vertices(face_tets: dict[tuple[int, int, int], list[int]]) -> set[int]:
    return {vertex for face, incident in face_tets.items() if len(incident) == 1 for vertex in face}


def _ring_warpage(points: np.ndarray) -> float:
    if len(points) < 3:
        return float("nan")
    center = points.mean(axis=0)
    _, _, vh = np.linalg.svd(points - center, full_matrices=False)
    normal = vh[-1]
    diameter = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))
    if diameter <= 1e-14:
        return float("inf")
    return float(np.max(np.abs((points - center) @ normal)) / diameter)


def _map(vertices: np.ndarray, tets: np.ndarray) -> dict[str, object]:
    vert_tets, edge_tets, face_tets = _build_tet_topology(tets, len(vertices))
    boundary = _boundary_vertices(face_tets)
    boundary_edges = {
        (min(edge[0], edge[1]), max(edge[0], edge[1]))
        for face, incident in face_tets.items()
        if len(incident) == 1
        for edge in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0]))
    }
    neighbours: list[set[int]] = [set() for _ in range(len(vertices))]
    vertex_edges: list[list[tuple[int, int]]] = [[] for _ in range(len(vertices))]
    ring_warpage: dict[tuple[int, int], float] = {}
    for edge, incident in edge_tets.items():
        a, b = edge
        neighbours[a].add(b)
        neighbours[b].add(a)
        vertex_edges[a].append(edge)
        vertex_edges[b].append(edge)
        if edge not in boundary_edges and len(incident) >= 3:
            centroids = vertices[tets[np.asarray(incident, dtype=np.int64)]].mean(axis=1)
            ring_warpage[edge] = _ring_warpage(centroids)

    low_vertices = [
        index for index in range(len(vertices))
        if index not in boundary and len(neighbours[index]) < 7
    ]
    orphan_vertices = [index for index in low_vertices if not vert_tets.get(index)]
    low_edges = {edge for index in low_vertices for edge in vertex_edges[index] if edge in ring_warpage}
    normal_edges = set(ring_warpage) - low_edges
    low_warp = [ring_warpage[edge] for edge in low_edges]
    normal_warp = [ring_warpage[edge] for edge in normal_edges]
    incomplete_edges = [
        edge for edge, incident in edge_tets.items()
        if edge not in boundary_edges and len(incident) < 3
    ]

    link_samples = []
    for edge in incomplete_edges[:8]:
        a, b = edge
        link_edges = []
        for tet_id in edge_tets[edge]:
            opposite = sorted(
                int(vertex) for vertex in tets[int(tet_id)] if vertex not in (a, b)
            )
            link_edges.append({
                "tet": int(tet_id),
                "tet_vertices": [int(vertex) for vertex in tets[int(tet_id)]],
                "opposite_pair": opposite,
            })
        link_vertices = sorted({
            vertex for item in link_edges for vertex in item["opposite_pair"]
        })
        edge_faces = []
        for face, owners in face_tets.items():
            if a in face and b in face:
                edge_faces.append({
                    "face": [int(vertex) for vertex in face],
                    "n_incident_tets": int(len(owners)),
                    "incident_tets": [int(tet_id) for tet_id in owners],
                })
        link_samples.append({
            "edge": [int(a), int(b)],
            "boundary_edge": bool(edge in boundary_edges),
            "edge_faces": edge_faces,
            "link_vertices": link_vertices,
            "link_edges": link_edges,
            "link_edge_count": len(link_edges),
            "link_is_cycle_candidate": len(link_edges) >= 3 and len(link_vertices) >= 3,
        })

    details = []
    for index in low_vertices:
        edges = sorted(vertex_edges[index])
        rings = [ring_warpage[edge] for edge in edges if edge in ring_warpage]
        details.append({
            "vertex": int(index),
            "boundary": bool(index in boundary),
            "n_incident_tets": int(len(vert_tets.get(index, []))),
            "valence": int(len(neighbours[index])),
            "edges": [[int(a), int(b)] for a, b in edges],
            "n_closed_ring_candidates": int(len(rings)),
            "max_ring_warpage": float(max(rings)) if rings else 0.0,
            "warped_ring_candidates": int(sum(value > 1e-6 for value in rings)),
        })

    audit = audit_tet_boundary(vertices, tets)
    return {
        "points": int(len(vertices)),
        "tets": int(len(tets)),
        "boundary_vertices": int(len(boundary)),
        "low_vertices": details,
        "orphan_vertices": [int(index) for index in orphan_vertices],
        "internal_edges": int(len(ring_warpage)),
        "internal_rings_lt3": int(
            sum(len(edge_tets[edge]) < 3 for edge in edge_tets if edge not in boundary_edges)
        ),
        "incomplete_ring_samples": [
            {
                "edge": [int(edge[0]), int(edge[1])],
                "n_incident_tets": int(len(edge_tets[edge])),
                "incident_tets": [int(tet) for tet in edge_tets[edge]],
            }
            for edge in incomplete_edges[:8]
        ],
        "incomplete_link_samples": link_samples,
        "low_adjacent_edges": int(len(low_edges)),
        "normal_edges": int(len(normal_edges)),
        "low_adjacent_max_warpage": float(max(low_warp)) if low_warp else 0.0,
        "low_adjacent_mean_warpage": float(np.mean(low_warp)) if low_warp else 0.0,
        "normal_max_warpage": float(max(normal_warp)) if normal_warp else 0.0,
        "normal_mean_warpage": float(np.mean(normal_warp)) if normal_warp else 0.0,
        "native_tet_audit": {
            "n_boundary_faces": int(audit.n_boundary_faces),
            "n_open_edges": int(audit.n_open_edges),
            "n_nonmanifold_edges": int(audit.n_nonmanifold_edges),
            "n_nonmanifold_faces": int(audit.n_nonmanifold_faces),
            "n_boundary_components": int(audit.n_boundary_components),
            "n_duplicate_tets": int(audit.n_duplicate_tets),
            "n_degenerate_tets": int(audit.n_degenerate_tets),
            "valid": bool(audit.valid),
        },
    }


def main() -> None:
    rows: dict[str, object] = {}
    for shape in ("cube", "cylinder", "sphere"):
        mesh = read_stl(ROOT / "tests" / "benchmarks" / f"{shape}.stl")
        with tempfile.TemporaryDirectory(prefix="native_poly_topology_map_") as temp:
            result = generate_native_tet(
                mesh.vertices,
                mesh.faces,
                Path(temp) / shape,
                seed_density=6,
            )
        if not result.success or result.tet_points is None or result.tets is None:
            rows[shape] = {"success": False, "message": result.message}
            continue
        rows[shape] = _map(
            np.asarray(result.tet_points, dtype=np.float64),
            np.asarray(result.tets, dtype=np.int64),
        )
    print(json.dumps(rows, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
