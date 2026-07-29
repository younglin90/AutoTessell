"""Report-only census for the native-poly concave/fan split card.

This diagnostic deliberately reconstructs the pre-fan-component dual cell
assembly in memory.  It does not call a split operator and it does not modify
the production dual geometry, placement, or solid gates.  The fixture is kept
inline to match the historical regression in ``tests/test_native_poly_dual.py``.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.spatial import ConvexHull

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.generator.native_poly import dual as dual_module  # noqa: E402, I001

_TARGET_CELL = 2
_TARGET_EDGE = (4, 0)
_TARGET_NORMALIZED_VOLUME = -5.261812553915713e-05
_PROVENANCE_NOTE = (
    "synthetic fixture_wall label; no CAD/source patch map is attached to the "
    "inline regression fixture"
)


@dataclass(frozen=True)
class FanFixture:
    vertices: np.ndarray
    tets: np.ndarray
    provenance: dict[tuple[int, int, int], dict[str, str]]
    source: str


def nonmanifold_fan_fixture() -> FanFixture:
    """Return the canonical 3-tet fan that exposes the old invalid cells."""
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, 1.0, 0.0],
            [0.5, 0.0, 1.0],
            [0.5, -1.0, 0.0],
            [0.5, 2.0, 2.0],
            [0.5, 3.0, 2.0],
        ],
        dtype=np.float64,
    )
    tets = np.array(
        [[0, 1, 2, 3], [0, 1, 3, 4], [0, 1, 5, 6]],
        dtype=np.int64,
    )
    face_tets = dual_module._build_tet_topology(tets, len(vertices))[2]
    boundary_faces = dual_module._extract_boundary(face_tets)
    provenance = {
        tri: {
            "patch": "fixture_wall",
            "type": "wall",
            "entity": "boundary_triangle",
        }
        for tri in boundary_faces
    }
    return FanFixture(
        vertices=vertices,
        tets=tets,
        provenance=provenance,
        source="tests/test_native_poly_dual.py::inline_nonmanifold_fan",
    )


def _boundary_edges(
    boundary_faces: list[tuple[int, int, int]],
) -> set[tuple[int, int]]:
    edges: set[tuple[int, int]] = set()
    for tri in boundary_faces:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            edges.add((min(a, b), max(a, b)))
    return edges


def _add_point_factory(
    all_points: list[np.ndarray],
) -> tuple[dict[tuple[int, int, int], int], Any]:
    point_ids: dict[tuple[int, int, int], int] = {}

    def add_point(point: np.ndarray) -> int:
        key = tuple(np.round(point * 1.0e9).astype(np.int64).tolist())
        if key not in point_ids:
            point_ids[key] = len(point_ids)
            all_points.append(np.asarray(point, dtype=np.float64))
        return point_ids[key]

    return point_ids, add_point


def _legacy_union_census(fixture: FanFixture) -> dict[str, Any]:
    """Rebuild the old one-cell-per-primal-vertex candidate, read-only.

    The implementation intentionally mirrors the historical assembly only far
    enough to expose the signed face-edge witnesses.  It is diagnostic code,
    not a second production dual implementation.
    """
    vertices = fixture.vertices
    tets = fixture.tets
    n_vertices = len(vertices)
    vert_tets, edge_tets, face_tets = dual_module._build_tet_topology(tets, n_vertices)
    boundary_faces = dual_module._extract_boundary(face_tets)
    boundary_edges = _boundary_edges(boundary_faces)
    boundary_faces_of_vertex: dict[int, list[tuple[int, int, int]]] = {}
    boundary_edges_of_vertex: dict[int, list[tuple[int, int]]] = {}
    for tri in boundary_faces:
        for vertex in tri:
            boundary_faces_of_vertex.setdefault(vertex, []).append(tri)
    for edge in boundary_edges:
        boundary_edges_of_vertex.setdefault(edge[0], []).append(edge)
        boundary_edges_of_vertex.setdefault(edge[1], []).append(edge)

    tet_dual_points = vertices[tets].mean(axis=1)
    all_points: list[np.ndarray] = []
    _, add_point = _add_point_factory(all_points)
    tet_point_id = np.array(
        [add_point(tet_dual_points[index]) for index in range(len(tets))],
        dtype=np.int64,
    )
    bface_pid = {tri: add_point(vertices[list(tri)].mean(axis=0)) for tri in boundary_faces}
    bedge_pid = {
        edge: add_point(0.5 * (vertices[edge[0]] + vertices[edge[1]])) for edge in boundary_edges
    }
    boundary_vertex_pid = {vertex: add_point(vertices[vertex]) for vertex in range(n_vertices)}
    point_provenance: dict[int, dict[str, Any]] = {}
    for index in range(len(tets)):
        point_provenance[int(tet_point_id[index])] = {
            "kind": "tet_dual_point",
            "tet": index,
        }
    for tri, point_id in bface_pid.items():
        point_provenance[point_id] = {"kind": "primal_boundary_face_centroid", "face": tri}
    for edge, point_id in bedge_pid.items():
        point_provenance[point_id] = {"kind": "primal_boundary_edge_midpoint", "edge": edge}
    for vertex, point_id in boundary_vertex_pid.items():
        point_provenance[point_id] = {"kind": "primal_boundary_vertex", "vertex": vertex}

    cell_faces: list[list[list[int]]] = []
    cell_centers: list[np.ndarray] = []
    for vertex in range(n_vertices):
        incident_tets = vert_tets.get(vertex, [])
        local_points = [tet_dual_points[index] for index in incident_tets]
        local_points.extend(
            vertices[list(tri)].mean(axis=0) for tri in boundary_faces_of_vertex.get(vertex, [])
        )
        local_points.extend(
            0.5 * (vertices[edge[0]] + vertices[edge[1]])
            for edge in boundary_edges_of_vertex.get(vertex, [])
        )
        local_points.append(vertices[vertex])
        points = np.asarray(local_points, dtype=np.float64)
        hull = ConvexHull(points, qhull_options="QJ")
        grouped: dict[tuple[int, ...], list[int]] = {}
        equation_keys = np.round(hull.equations * 1.0e6).astype(np.int64)
        for simplex_index, key in enumerate(map(tuple, equation_keys.tolist())):
            grouped.setdefault(key, []).append(simplex_index)

        local_faces: list[list[int]] = []
        center = points.mean(axis=0)
        for simplex_ids in grouped.values():
            local_vertex_ids: set[int] = set()
            for simplex_id in simplex_ids:
                local_vertex_ids.update(int(value) for value in hull.simplices[simplex_id])
            ordered_local = sorted(local_vertex_ids)
            polygon_points = points[ordered_local]
            polygon_center = polygon_points.mean(axis=0)
            normal = hull.equations[simplex_ids[0], :3]
            tangent = polygon_points[0] - polygon_center
            tangent = tangent - normal * float(np.dot(tangent, normal))
            if np.linalg.norm(tangent) < 1.0e-30:
                continue
            tangent = tangent / np.linalg.norm(tangent)
            bitangent = np.cross(normal, tangent)
            projected = np.stack(
                [
                    (polygon_points - polygon_center) @ tangent,
                    (polygon_points - polygon_center) @ bitangent,
                ],
                axis=1,
            )
            order = np.argsort(np.arctan2(projected[:, 1], projected[:, 0]))
            ordered_local = [ordered_local[int(index)] for index in order]
            global_face = []
            for local_index in ordered_local:
                if local_index < len(incident_tets):
                    global_face.append(int(tet_point_id[incident_tets[local_index]]))
                elif local_index < len(incident_tets) + len(
                    boundary_faces_of_vertex.get(vertex, [])
                ):
                    tri = boundary_faces_of_vertex[vertex][local_index - len(incident_tets)]
                    global_face.append(bface_pid[tri])
                elif local_index < len(incident_tets) + len(
                    boundary_faces_of_vertex.get(vertex, [])
                ) + len(boundary_edges_of_vertex.get(vertex, [])):
                    edge_index = (
                        local_index
                        - len(incident_tets)
                        - len(boundary_faces_of_vertex.get(vertex, []))
                    )
                    global_face.append(bedge_pid[boundary_edges_of_vertex[vertex][edge_index]])
                else:
                    global_face.append(boundary_vertex_pid[vertex])
            if len(global_face) >= 3:
                local_faces.append(global_face)
        cell_faces.append(local_faces)
        cell_centers.append(center)

    def flip_if_inward(face: list[int], center: np.ndarray) -> list[int]:
        points = np.asarray(all_points, dtype=np.float64)[face]
        normal = np.cross(points[1] - points[0], points[2] - points[0])
        if float(np.dot(normal, points.mean(axis=0) - center)) < 0.0:
            return list(reversed(face))
        return face

    internal_faces: list[list[int]] = []
    internal_owner: list[int] = []
    internal_neighbour: list[int] = []
    for edge in edge_tets:
        if edge in boundary_edges:
            continue
        ring, closed = dual_module._ordered_tet_ring(edge, edge_tets, face_tets, tets)
        if not closed or len(ring) < 3:
            continue
        owner = edge[0]
        neighbour = edge[1]
        internal_faces.append(
            flip_if_inward([int(tet_point_id[index]) for index in ring], cell_centers[owner])
        )
        internal_owner.append(owner)
        internal_neighbour.append(neighbour)

    # Historical boundary-edge separating faces are part of the witness.  The
    # production fan-component guard adds an additional connectivity check;
    # this report-only reconstruction intentionally does not.
    edge_to_boundary_faces: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
    for tri in boundary_faces:
        for edge in (
            (min(tri[0], tri[1]), max(tri[0], tri[1])),
            (min(tri[1], tri[2]), max(tri[1], tri[2])),
            (min(tri[2], tri[0]), max(tri[2], tri[0])),
        ):
            edge_to_boundary_faces.setdefault(edge, []).append(tri)
    for edge in boundary_edges:
        boundary_triangles = edge_to_boundary_faces.get(edge, [])
        if len(boundary_triangles) != 2:
            continue
        ring, _closed = dual_module._ordered_tet_ring(edge, edge_tets, face_tets, tets)
        if not ring:
            continue
        raw = (
            [bface_pid[boundary_triangles[0]]]
            + [int(tet_point_id[index]) for index in ring]
            + [bface_pid[boundary_triangles[1]], bedge_pid[edge]]
        )
        face: list[int] = []
        for point_id in raw:
            if not face or face[-1] != point_id:
                face.append(point_id)
        if len(face) > 1 and face[0] == face[-1]:
            face.pop()
        if len(face) < 3:
            continue
        internal_faces.append(flip_if_inward(face, cell_centers[edge[0]]))
        internal_owner.append(edge[0])
        internal_neighbour.append(edge[1])

    boundary_dual_faces: list[list[int]] = []
    boundary_dual_owner: list[int] = []
    for vertex in range(n_vertices):
        for tri in boundary_faces_of_vertex.get(vertex, []):
            others = [int(value) for value in tri if int(value) != vertex]
            raw = [
                boundary_vertex_pid[vertex],
                bedge_pid[(min(vertex, others[0]), max(vertex, others[0]))],
                bface_pid[tri],
                bedge_pid[(min(vertex, others[1]), max(vertex, others[1]))],
            ]
            face: list[int] = []
            for point_id in raw:
                if not face or face[-1] != point_id:
                    face.append(point_id)
            if len(face) >= 3:
                boundary_dual_faces.append(flip_if_inward(face, cell_centers[vertex]))
                boundary_dual_owner.append(vertex)

    final_faces, final_owner, final_neighbour, n_boundary = dual_module._order_and_concat(
        internal_faces,
        internal_owner,
        internal_neighbour,
        boundary_dual_faces,
        boundary_dual_owner,
    )
    points_array = np.asarray(all_points, dtype=np.float64)
    invalid_cells, invalid_subtets, examples = dual_module._star_validity(
        points_array,
        final_faces,
        final_owner,
        final_neighbour,
        len(cell_faces),
    )
    return {
        "n_cells": len(cell_faces),
        "n_points": len(all_points),
        "n_faces": len(final_faces),
        "n_boundary_faces": n_boundary,
        "invalid_cells": invalid_cells,
        "invalid_subtets": invalid_subtets,
        "examples": [dict(example) for example in examples],
        "points": points_array,
        "faces": final_faces,
        "owner": final_owner,
        "neighbour": final_neighbour,
        "cell_primal_vertex": list(range(n_vertices)),
        "cell_primal_tets": [vert_tets.get(vertex, []) for vertex in range(n_vertices)],
        "point_provenance": point_provenance,
        "boundary_faces": boundary_faces,
        "boundary_edges": sorted(boundary_edges),
        "face_kind": [
            "internal" if index < len(final_faces) - n_boundary else "boundary"
            for index in range(len(final_faces))
        ],
    }


def _concavity_census(candidate: dict[str, Any], cell_id: int) -> dict[str, Any]:
    points = candidate["points"]
    faces = candidate["faces"]
    owner = candidate["owner"]
    neighbour = candidate["neighbour"]
    n_cells = candidate["n_cells"]
    cell_faces: list[list[tuple[list[int], int]]] = [[] for _ in range(n_cells)]
    for face_id, face in enumerate(faces):
        cell_faces[owner[face_id]].append((list(face), face_id))
        if face_id < len(neighbour):
            cell_faces[neighbour[face_id]].append((list(reversed(face)), face_id))
    scale = max(float(np.linalg.norm(points.max(axis=0) - points.min(axis=0))) ** 3, 1.0e-30)
    cell_vertex_ids = sorted({vertex for face, _ in cell_faces[cell_id] for vertex in face})
    region_center = points[np.asarray(cell_vertex_ids)].mean(axis=0)
    records: list[dict[str, Any]] = []
    for face, face_id in cell_faces[cell_id]:
        face_center = points[np.asarray(face)].mean(axis=0)
        edge_records: list[dict[str, Any]] = []
        for a, b in zip(face, face[1:] + face[:1]):
            signed = float(
                np.dot(
                    points[b] - points[a],
                    np.cross(face_center - points[a], region_center - points[a]),
                )
            )
            edge_records.append(
                {
                    "edge": (int(a), int(b)),
                    "normalized_signed_volume6": -signed / scale,
                    "concave": -signed / scale <= 1.0e-12,
                    "point_provenance": [
                        candidate["point_provenance"].get(int(a), {}),
                        candidate["point_provenance"].get(int(b), {}),
                    ],
                }
            )
        records.append(
            {
                "face": face_id,
                "kind": candidate["face_kind"][face_id],
                "concave": any(edge["concave"] for edge in edge_records),
                "min_normalized_signed_volume6": min(
                    edge["normalized_signed_volume6"] for edge in edge_records
                ),
                "edges": edge_records,
            }
        )
    return {
        "cell": cell_id,
        "primal_vertex": candidate["cell_primal_vertex"][cell_id],
        "primal_tets": candidate["cell_primal_tets"][cell_id],
        "faces": records,
        "concave_faces": [record["face"] for record in records if record["concave"]],
        "concave_edges": sorted(
            {
                tuple(edge["edge"])
                for record in records
                for edge in record["edges"]
                if edge["concave"]
            }
        ),
    }


def _fan_topology_census(fixture: FanFixture) -> dict[str, Any]:
    _, edge_tets, face_tets = dual_module._build_tet_topology(fixture.tets, len(fixture.vertices))
    nonmanifold_edges = {edge: owners for edge, owners in edge_tets.items() if len(owners) > 2}
    fan_components = {
        vertex: dual_module._vertex_fan_components(
            vertex,
            [index for index, tet in enumerate(fixture.tets) if vertex in tet],
            fixture.tets,
        )
        for vertex in range(len(fixture.vertices))
    }
    return {
        "nonmanifold_primal_edges": [
            {"edge": edge, "tet_ids": owners} for edge, owners in sorted(nonmanifold_edges.items())
        ],
        "vertex_fan_components": fan_components,
        "boundary_patch_provenance": [
            {"triangle": tri, **label, "note": _PROVENANCE_NOTE}
            for tri, label in sorted(fixture.provenance.items())
        ],
    }


def build_census() -> dict[str, Any]:
    """Build the deterministic report-only feasibility census."""
    fixture = nonmanifold_fan_fixture()
    legacy = _legacy_union_census(fixture)
    target = _concavity_census(legacy, _TARGET_CELL)
    topology = _fan_topology_census(fixture)
    with tempfile.TemporaryDirectory(prefix="native_poly_concave_diag_") as temp_dir:
        original_vertices = fixture.vertices.copy()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            current = dual_module.tet_to_poly_dual(
                fixture.vertices,
                fixture.tets,
                Path(temp_dir),
                boundary_face_classifier=lambda _triangle, _vertices: {
                    "patch": "fixture_wall",
                    "type": "wall",
                    "entity": "boundary_triangle",
                },
                _dual_point_mode="centroid",
            )
        surface_vertices_unchanged = bool(np.array_equal(fixture.vertices, original_vertices))

    has_target_edge = any(
        _TARGET_EDGE in [tuple(edge["edge"]), tuple(reversed(edge["edge"]))]
        for face in target["faces"]
        for edge in face["edges"]
    )
    boundary_apex = target["primal_vertex"] in {
        vertex for tri in legacy["boundary_faces"] for vertex in tri
    }
    incident_boundary_edges = [
        edge for edge in legacy["boundary_edges"] if target["primal_vertex"] in edge
    ]
    topology_blockers = [
        "non-manifold primal edge (0, 1) has three tet owners",
        "fixture has synthetic patch labels rather than source CAD entity provenance",
    ]
    return {
        "card": "POLY-CONCAVE-SPLIT1",
        "mode": "report_only",
        "source": fixture.source,
        "literature": {
            "doi": "10.1016/j.proeng.2015.10.131",
            "method": "conical cell decomposition/bisection along a concave edge",
            "base": "polygonal primal-edge cut-face",
            "apex": "dual boundary vertex",
            "implementation": "not attempted",
        },
        "target": {
            "cell": _TARGET_CELL,
            "edge": _TARGET_EDGE,
            "expected_normalized_signed_volume6": _TARGET_NORMALIZED_VOLUME,
            "reproduced": legacy["invalid_cells"] == 2
            and legacy["invalid_subtets"] == 18
            and has_target_edge,
        },
        "legacy_union_candidate": {
            key: value
            for key, value in legacy.items()
            if key not in {"points", "faces", "owner", "neighbour"}
        },
        "current_fan_component_reference": {
            "invalid_cells": current.invalid_star_cells,
            "invalid_subtets": current.invalid_star_subtets,
            "message": current.message,
        },
        "primal_topology_and_provenance": topology,
        "cell_boundary_concavity": target,
        "conical_decomposition_feasibility": {
            "geometric_candidate": bool(target["concave_faces"] and boundary_apex),
            "boundary_apex_present": boundary_apex,
            "incident_boundary_edges": incident_boundary_edges,
            "target_edge_seen": has_target_edge,
            "split_feasible": False,
            "classification": "STRUCTURAL_UNRESOLVED",
            "status": "blocked_pending_provenance_and_transactional_topology",
            "blockers": topology_blockers,
            "reason": (
                "The witness has a boundary apex and concave signed face-edge "
                "subtets, but the non-manifold primal fan and synthetic-only "
                "patch labels do not justify an accepted child topology."
            ),
        },
        "surface_vertex_invariant": {
            "changed": not surface_vertices_unchanged,
            "unchanged": surface_vertices_unchanged,
            "operation": "no split; no placement or geometry mutation",
        },
        "solid_gate": {
            "changed": False,
            "status": "not evaluated by this card",
        },
        "reproduction": {
            "command": "python3 scripts/diagnose_native_poly_concave_split.py --json",
            "fixture_command": (
                "python3 -m pytest tests/test_native_poly_dual.py::"
                "test_tet_to_poly_dual_star_validity_convex_and_nonmanifold -q"
            ),
            "note": "The exact V/T fixture is inline, not a standalone mesh file.",
        },
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    census = _json_safe(build_census())
    if args.json:
        print(json.dumps(census, indent=2, sort_keys=True))
    else:
        target = census["target"]
        feasibility = census["conical_decomposition_feasibility"]
        print("POLY-CONCAVE-SPLIT1 report-only feasibility census")
        print(f"fixture={census['source']}")
        print(
            "legacy_invalid="
            f"{census['legacy_union_candidate']['invalid_cells']} cells / "
            f"{census['legacy_union_candidate']['invalid_subtets']} subtets"
        )
        print(
            f"target=cell {target['cell']} edge {tuple(target['edge'])} "
            f"reproduced={target['reproduced']}"
        )
        print(
            "conical_candidate="
            f"{feasibility['geometric_candidate']} "
            f"split_feasible={feasibility['split_feasible']}"
        )
        print(
            f"surface_vertices_unchanged={census['surface_vertex_invariant']['unchanged']} "
            "placement_dual_geometry_solid_gate=unchanged"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
