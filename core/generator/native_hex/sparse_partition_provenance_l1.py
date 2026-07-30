"""Immutable, report-only provenance labels for sparse diagnostic leaves."""

from __future__ import annotations

from dataclasses import dataclass

from .sparse_leaf_partition_l0 import SparseLeafKey


_PROVENANCE = frozenset(("inside", "outside", "surface"))


@dataclass(frozen=True, order=True)
class SparseProvenanceLeaf:
    """One sparse key with a geometry-derived diagnostic classification."""

    key: SparseLeafKey
    provenance: str

    def __post_init__(self) -> None:
        if self.provenance not in _PROVENANCE:
            raise ValueError("sparse provenance must be inside, outside, or surface")
