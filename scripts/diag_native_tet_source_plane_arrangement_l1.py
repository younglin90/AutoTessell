"""Report-only L1 census of source-plane arrangements in raw native-tet seeds.

This intentionally stops before recovery.  It recreates the initial
surface-vertex plus interior-grid Delaunay state, identifies direct-missing
source faces, and reports whether each finite source-plane arrangement is
eligible for a later atomic Chen template plan.  It neither writes a mesh nor
modifies the production generator.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import Delaunay

from core.generator.native_tet.chen_coplanar_source_shell_owner_l0 import (
    audit_coplanar_source_shell_owner_l0,
)
from core.generator.native_tet.chen_source_edge_chain_l1 import audit_source_edge_chain_l1
from core.generator.native_tet.chen_source_edge_presence_l0 import (
    audit_source_edge_presence_l0,
)
from core.generator.native_tet.chen_source_facet_worklist_l0 import (
    build_source_facet_recovery_worklist_l0,
)
from core.generator.native_tet.chen_source_missing_region_extraction_l1 import (
    extract_source_missing_region_l1,
)
from core.generator.native_tet.chen_source_plane_arrangement_l0 import (
    build_source_plane_arrangement_l0,
)
from core.generator.native_tet.mesher import _inside_winding_number, _seed_points_uniform
from core.generator.native_tet.seed_source_coordinate_dedupe_l0 import (
    plan_seed_source_coordinate_dedupe_l0,
)
from core.generator.native_tet.si_segment_split_plan_l0 import plan_si_segment_split_l0
from core.generator.native_tet.source_complex_canonicalization_l0 import (
    canonicalize_source_complex_l0,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--seed-density", type=int, default=4)
    parser.add_argument(
        "--weld-vertices",
        action="store_true",
        help="diagnose a coordinate-welded canonical surface complex (read-only)",
    )
    parser.add_argument(
        "--dedupe-grid-source-coordinates",
        action="store_true",
        help="apply the read-only source/grid collision plan to this diagnostic seed only",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    mesh = trimesh.load_mesh(args.fixture, process=False)
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError("fixture must contain one triangular surface mesh")
    raw_points = np.asarray(mesh.vertices, dtype=np.float64)
    raw_faces = np.asarray(mesh.faces, dtype=np.int64)
    canonical = canonicalize_source_complex_l0(raw_points, raw_faces)
    if args.weld_vertices:
        if not canonical.accepted:
            raise ValueError(f"canonical source complex rejected: {canonical.reason}")
        points = np.asarray(canonical.canonical_points, dtype=np.float64)
        faces = np.asarray(canonical.canonical_faces, dtype=np.int64)
    else:
        points, faces = raw_points, raw_faces
    bbox_min, bbox_max = points.min(axis=0), points.max(axis=0)
    target = float(np.linalg.norm(bbox_max - bbox_min)) / max(1, args.seed_density)
    grid = _seed_points_uniform(bbox_min, bbox_max, target)
    if grid.size:
        grid = grid[_inside_winding_number(grid, points, faces)]
    dedupe = plan_seed_source_coordinate_dedupe_l0(points, grid)
    if args.dedupe_grid_source_coordinates:
        grid = np.asarray(dedupe.filtered_grid_points, dtype=np.float64)
    initial_points = np.vstack((points, grid)) if grid.size else points.copy()
    initial_tets = np.asarray(Delaunay(initial_points).simplices, dtype=np.int64)
    source_edges = tuple(
        tuple(sorted((int(face[index]), int(face[(index + 1) % 3]))))
        for face in faces
        for index in range(3)
    )
    source_edge_presence = audit_source_edge_presence_l0(
        len(initial_points), source_edges, initial_tets
    )
    source_edge_chain_rows = tuple(
        (edge, audit_source_edge_chain_l1(initial_points, edge, initial_tets))
        for edge in sorted(set(source_edges))
    )
    source_edge_chains = tuple(audit for _, audit in source_edge_chain_rows)
    source_edge_chain_reasons = Counter(audit.reason for audit in source_edge_chains)
    source_edge_split_rows = tuple(
        (edge, plan_si_segment_split_l0(initial_points, edge, source_edges))
        for edge, audit in source_edge_chain_rows
        if audit.reason == "source_edge_partition_gap"
    )
    worklist = build_source_facet_recovery_worklist_l0(initial_points, initial_tets, faces)
    rows: list[dict[str, object]] = []
    for item in worklist.items:
        source_triangle = tuple(points[index] for index in item.source_face)
        arrangement = build_source_plane_arrangement_l0(
            initial_points, initial_tets, source_triangle
        )
        coplanar_shell = audit_coplanar_source_shell_owner_l0(
            initial_points, initial_tets, source_triangle
        )
        missing_region = extract_source_missing_region_l1(
            initial_points, item.source_face, initial_tets
        )
        rows.append(
            {
                "source_face_index": item.source_face_index,
                "strict_tets": len(item.unique_tet_ids),
                "ambiguous_tets": len(item.ambiguous_tet_ids),
                "arrangement_accepted": arrangement.accepted,
                "arrangement_reason": arrangement.reason,
                "components": len(arrangement.components),
                "fragments": len(arrangement.fragments),
                "unresolved_parents": len(arrangement.unresolved_parent_indices),
                "boundary_contact_parents": len(arrangement.boundary_contact_parent_indices),
                "fragment_classifications": [
                    {
                        "parent": fragment.parent_index,
                        "type": fragment.clusterel_type,
                        "classification": fragment.classification_reason,
                        "node": fragment.node_reason,
                    }
                    for fragment in arrangement.fragments
                ],
                "literal_template_ready": arrangement.literal_template_ready,
                "coplanar_shell_accepted": coplanar_shell.accepted,
                "coplanar_shell_reason": coplanar_shell.reason,
                "coplanar_owner_count": len(coplanar_shell.owners),
                "coplanar_selected_side": coplanar_shell.selected_side,
                "missing_region_accepted": missing_region.accepted,
                "missing_region_reason": missing_region.reason,
                "missing_region_touch_tets": len(missing_region.source_edge_touch_tet_ids),
                "missing_region_crossing_tets": len(missing_region.crossing_tet_ids),
                "missing_region_zero_side_tets": len(missing_region.zero_side_tet_ids),
                "missing_region_selected_side": (
                    None if missing_region.plan is None else missing_region.plan.selected_side
                ),
            }
        )
    print(
        json.dumps(
            {
                "fixture": str(args.fixture),
                "vertex_mode": "coordinate_welded" if args.weld_vertices else "raw_stl_indices",
                "source_canonicalization": {
                    "accepted": canonical.accepted,
                    "raw_points": len(raw_points),
                    "canonical_points": len(canonical.canonical_points),
                    "raw_triangles_preserved": canonical.raw_triangle_count_preserved,
                },
                "grid_source_coordinate_dedupe": {
                    "planned_removed": len(dedupe.removed_grid_indices),
                    "applied": args.dedupe_grid_source_coordinates,
                },
                "seed_density": args.seed_density,
                "initial_points": int(initial_points.shape[0]),
                "initial_tets": int(initial_tets.shape[0]),
                "missing_source_faces": len(worklist.items),
                "source_edge_presence": {
                    "accepted": source_edge_presence.accepted,
                    "present": len(source_edge_presence.present_edges),
                    "missing": len(source_edge_presence.missing_edges),
                    "reason": source_edge_presence.reason,
                },
                "source_edge_chain": {
                    "accepted": sum(audit.accepted for audit in source_edge_chains),
                    "total": len(source_edge_chains),
                    "reasons": dict(sorted(source_edge_chain_reasons.items())),
                    "failures": [
                        {
                            "edge": edge,
                            "reason": audit.reason,
                            "on_segment_vertices": audit.on_segment_vertex_ids,
                            "chain_edges": audit.chain_edges,
                        }
                        for edge, audit in source_edge_chain_rows
                        if not audit.accepted
                    ],
                    "si_split_proposals": [
                        {
                            "edge": edge,
                            "reason": plan.reason,
                            "encroacher": plan.chosen_encroacher_index,
                            "acute": plan.endpoint_is_acute,
                            "parameter": (
                                None
                                if plan.candidate_parameter is None
                                else str(plan.candidate_parameter)
                            ),
                        }
                        for edge, plan in source_edge_split_rows
                    ],
                },
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
