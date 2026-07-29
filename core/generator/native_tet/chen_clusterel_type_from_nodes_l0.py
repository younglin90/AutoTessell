"""Chen clusterel type derived from the exact five-way node ledger.

Figure 4 defines a clusterel type by the number of tetrahedron edges that
*cut through* the missing facet.  In the node ledger, only an open-segment
``NOD_MID`` is such a cut; NUL/EXT and endpoint contacts are retained as
provenance but do not add a cutting edge.  This is read-only and does not
select a decomposition template.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from core.generator.native_tet.chen_clusterel_node_state_l0 import (
    ChenClusterelNodeStateResult,
)

ClusterelTypeFromNodes = Literal["CO_PLAN", "ONE_EDG", "TWO_EDG", "THR_EDG", "FOU_EDG"]


@dataclass(frozen=True)
class ChenClusterelTypeFromNodesResult:
    """Exact cut-edge count derived from an already accepted node ledger."""

    accepted: bool
    reason: str
    clusterel_type: ClusterelTypeFromNodes | None
    cutting_local_edges: tuple[tuple[int, int], ...]


def classify_clusterel_type_from_nodes_l0(
    nodes: ChenClusterelNodeStateResult,
) -> ChenClusterelTypeFromNodesResult:
    """Count only strict open facet crossings; preserve all other node states."""
    if not nodes.accepted:
        return ChenClusterelTypeFromNodesResult(False, f"node_ledger_failed:{nodes.reason}", None, ())
    cutting = tuple(node.local_edge for node in nodes.nodes if node.node_type == "NOD_MID")
    mapping: dict[int, ClusterelTypeFromNodes] = {
        0: "CO_PLAN", 1: "ONE_EDG", 2: "TWO_EDG", 3: "THR_EDG", 4: "FOU_EDG"
    }
    clusterel_type = mapping.get(len(cutting))
    if clusterel_type is None:
        return ChenClusterelTypeFromNodesResult(False, "more_than_four_cutting_edges", None, ())
    return ChenClusterelTypeFromNodesResult(True, "accepted", clusterel_type, cutting)
