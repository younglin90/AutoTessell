"""Measure report-only 2:1 balancing of a real SAT sparse partition."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.analyzer.readers import read_stl  # noqa: E402
from core.generator.native_hex.sparse_closed_volume_l3 import (  # noqa: E402
    audit_sparse_closed_volume,
)
from core.generator.native_hex.sparse_mesh_balance_l1 import (  # noqa: E402
    balance_mesh_provenance_partition,
)
from core.generator.native_hex.sparse_mesh_provenance_l2 import (  # noqa: E402
    sampled_mesh_provenance_partition,
)
from core.generator.native_hex.sparse_pairing_l0 import (  # noqa: E402
    audit_sparse_octree_pairing,
)
from core.generator.native_hex.sparse_pairing_provenance_l2 import (  # noqa: E402
    pair_balance_reclassify_sparse_mesh,
)
from core.generator.native_hex.sparse_pairing_worklist_l1 import (  # noqa: E402
    pair_sparse_leaf_keys_worklist,
)
from core.generator.native_hex.sparse_surface_contract_l0 import (  # noqa: E402
    audit_sparse_selected_surface_contract,
)


def run_fixture(
    fixture: Path,
    *,
    max_level: int,
    leaf_budget: int,
    closure_face_tile_budget: int,
    pairing_leaf_budget: int,
) -> dict[str, object]:
    """Sample and balance one STL without changing the production octree."""
    surface = read_stl(fixture)
    vertices = np.asarray(surface.vertices, dtype=np.float64)
    faces = np.asarray(surface.faces, dtype=np.int64)
    lower, upper = vertices.min(axis=0), vertices.max(axis=0)
    target_edge = float(np.linalg.norm(upper - lower)) / 24.0
    root_shape = tuple(np.maximum(np.ceil((upper - lower) / target_edge).astype(int), 2).tolist())
    partition = sampled_mesh_provenance_partition(
        vertices,
        faces,
        root_min=lower,
        target_edge=target_edge,
        root_shape=root_shape,
        max_level=max_level,
        leaf_budget=leaf_budget,
    )
    result: dict[str, object] = {
        "fixture": str(fixture),
        "root_shape": list(root_shape),
        "partition_status": partition.status,
        "partition_leaves": len(partition.terminal_leaves),
        "partition_max_face_neighbor_level_difference": (
            partition.max_face_neighbor_level_difference
        ),
        "production_octree_changed": False,
    }
    if partition.status != "pass_complete_mesh_provenance_partition":
        return result

    balance = balance_mesh_provenance_partition(
        partition,
        vertices,
        faces,
        root_min=lower,
        target_edge=target_edge,
        root_shape=root_shape,
        max_level=max_level,
    )
    result.update(
        balance_status=balance.status,
        balance_refined_leaves=balance.balance_refined_leaves,
        balance_final_leaves=len(balance.final_leaves),
        balance_max_face_neighbor_level_difference=(balance.max_face_neighbor_level_difference),
        balance_reclassified_leaves=balance.reclassified_leaves,
        provenance_histogram=balance.provenance_histogram,
    )
    if balance.status == "pass_balanced_reclassified_partition":
        pairing = audit_sparse_octree_pairing(
            tuple(item.key for item in balance.final_leaves), max_level=max_level
        )
        pairing_worklist = pair_sparse_leaf_keys_worklist(
            tuple(item.key for item in balance.final_leaves),
            max_level=max_level,
            leaf_budget=pairing_leaf_budget,
        )
        pairing_provenance = pair_balance_reclassify_sparse_mesh(
            balance.final_leaves,
            vertices,
            faces,
            root_min=lower,
            target_edge=target_edge,
            root_shape=root_shape,
            max_level=max_level,
            leaf_budget=pairing_leaf_budget,
        )
        closure = audit_sparse_closed_volume(
            balance.final_leaves,
            max_level=max_level,
            face_tile_budget=closure_face_tile_budget,
        )
        result.update(
            pairing_status=pairing.status,
            pairing_parent_count=pairing.parent_count,
            pairing_unpaired_parent_count=pairing.unpaired_parent_count,
            pairing_first_unpaired_parent=pairing.first_unpaired_parent,
            pairing_first_unpaired_refined_child_mask=(pairing.first_unpaired_refined_child_mask),
            pairing_worklist_status=pairing_worklist.status,
            pairing_worklist_final_leaves=len(pairing_worklist.final_leaves),
            pairing_worklist_refined_terminal_leaves=(pairing_worklist.refined_terminal_leaves),
            pairing_worklist_sweeps=pairing_worklist.sweeps,
            pairing_worklist_final_unpaired_parent_count=(
                pairing_worklist.final_unpaired_parent_count
            ),
            pairing_provenance_status=pairing_provenance.status,
            pairing_provenance_final_leaves=len(pairing_provenance.final_leaves),
            pairing_provenance_reclassified_leaves=(pairing_provenance.reclassified_leaves),
            pairing_provenance_pairing_refined_terminal_leaves=(
                pairing_provenance.pairing_refined_terminal_leaves
            ),
            pairing_provenance_balance_refined_parent_leaves=(
                pairing_provenance.balance_refined_parent_leaves
            ),
            pairing_provenance_histogram=pairing_provenance.provenance_histogram,
            closure_status=closure.status,
            closure_selected_leaves=closure.selected_leaf_count,
            closure_face_owner_histogram=closure.face_owner_histogram,
            closure_boundary_face_tiles=closure.boundary_face_tiles,
            closure_boundary_edge_owner_histogram=closure.boundary_edge_owner_histogram,
            closure_connected_components=closure.connected_components,
            closure_closed_exterior_boundary=closure.closed_exterior_boundary,
        )
        if pairing_provenance.status == "pass_paired_balanced_reclassified_partition":
            paired_closure = audit_sparse_closed_volume(
                pairing_provenance.final_leaves,
                max_level=max_level,
                face_tile_budget=closure_face_tile_budget,
            )
            result.update(
                pairing_provenance_closure_status=paired_closure.status,
                pairing_provenance_closure_selected_leaves=(paired_closure.selected_leaf_count),
                pairing_provenance_closure_connected_components=(
                    paired_closure.connected_components
                ),
                pairing_provenance_closure_closed_exterior_boundary=(
                    paired_closure.closed_exterior_boundary
                ),
                pairing_provenance_closure_boundary_edge_owner_histogram=(
                    paired_closure.boundary_edge_owner_histogram
                ),
            )
            surface_contract = audit_sparse_selected_surface_contract(
                pairing_provenance.final_leaves,
                vertices,
                faces,
                root_min=lower,
                target_edge=target_edge,
                max_level=max_level,
                tolerance=float(np.linalg.norm(upper - lower)) * 1.0e-10,
            )
            result.update(
                surface_contract_status=surface_contract.status,
                surface_contract_candidate_to_source_max=(surface_contract.candidate_to_source_max),
                surface_contract_source_to_candidate_max=(surface_contract.source_to_candidate_max),
                surface_contract_tolerance=surface_contract.tolerance,
                surface_contract_sampled_coincident=surface_contract.sampled_coincident,
                surface_contract_strict_proven=(surface_contract.strict_surface_contract_proven),
            )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--max-level", type=int, required=True)
    parser.add_argument("--leaf-budget", type=int, default=50_000)
    parser.add_argument("--closure-face-tile-budget", type=int, default=3_000_000)
    parser.add_argument("--pairing-leaf-budget", type=int, default=100_000)
    args = parser.parse_args()
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_fixture(
            args.fixture,
            max_level=args.max_level,
            leaf_budget=args.leaf_budget,
            closure_face_tile_budget=args.closure_face_tile_budget,
            pairing_leaf_budget=args.pairing_leaf_budget,
        )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
