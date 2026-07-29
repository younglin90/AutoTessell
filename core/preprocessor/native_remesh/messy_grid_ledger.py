"""QUAD-MESSY-GRID-TOL1 report-only discrepancy ledger.

This module records the deviations already exposed by QUAD-POSY1.  It is
deliberately downstream of :mod:`posy_diagnostic`: it does not alter the
position field, choose a branch, solve an integer system, or call any quad
extraction/generation path.

The card is motivated by the abstract of Ray, *On Quad Mesh Extraction From
Messy Grid Preserving Maps* (arXiv:2507.15404).  The abstract says that
non-grid-preserving inputs should first have their differences specified and
represented by discrete operations.  The full paper has not been read here,
so this ledger defines no acceptable tolerance.  Every value below is an
observed count, exact integer residual, or exact branch-option comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.preprocessor.native_remesh.posy_diagnostic import (
    Int2,
    PositionOffsetLedger,
)


def _unique_sorted(values: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(sorted(set(int(value) for value in values)))


def _pairwise_positive_differences(values: tuple[int, ...]) -> tuple[int, ...]:
    ordered = _unique_sorted(values)
    return tuple(
        ordered[right] - ordered[left]
        for left in range(len(ordered))
        for right in range(left + 1, len(ordered))
    )


@dataclass(frozen=True)
class MessyGridDiscrepancyEntry:
    """Observed discrepancy values for one POSY face entry."""

    face: int
    face_vertex_ids: tuple[int, int, int]
    centroid: tuple[float, float, float]
    unresolved: bool
    unresolved_reasons: tuple[str, ...]
    expected_branch_indices: tuple[int, ...]
    observed_branch_indices: tuple[int, ...]
    lost_branch_indices: tuple[int, ...]
    branch_offset_differences: tuple[int, ...]
    branch_offset_span: int
    local_integer_discrepancies: tuple[Int2, ...]
    local_integer_discrepancy_l1: tuple[int, ...]
    position_singularity: bool
    expected_half_index_branches: tuple[int, ...]
    observed_half_index_branches: tuple[int, ...]
    lost_half_index_branches: tuple[int, ...]

    @property
    def branch_entry(self) -> bool:
        """Whether the source ledger exposed more than one branch option."""

        return len(self.expected_branch_indices) > 1

    @property
    def local_integer_discrepancy(self) -> bool:
        """Whether any observed branch has a non-zero integer residual."""

        return any(value != (0, 0) for value in self.local_integer_discrepancies)

    @property
    def branch_loss_count(self) -> int:
        return len(self.lost_branch_indices)

    @property
    def half_index_branch_loss_count(self) -> int:
        return len(self.lost_half_index_branches)


@dataclass(frozen=True)
class MessyGridDiscrepancyLedger:
    """Immutable, report-only QUAD-MESSY-GRID-TOL1 ledger."""

    shape_name: str
    n_vertices: int
    n_sweeps: int
    seed: int
    multires: bool
    entries: tuple[MessyGridDiscrepancyEntry, ...] = field(default_factory=tuple)

    @property
    def n_faces(self) -> int:
        return len(self.entries)

    @property
    def position_singularity_face_count(self) -> int:
        """Number of faces with at least one non-zero POSY residual."""

        return sum(entry.position_singularity for entry in self.entries)

    @property
    def position_singularity_candidate_count(self) -> int:
        """Number of branch candidates with a non-zero POSY residual."""

        return sum(
            discrepancy != (0, 0)
            for entry in self.entries
            for discrepancy in entry.local_integer_discrepancies
        )

    @property
    def local_integer_discrepancy_candidate_count(self) -> int:
        """Number of candidate residuals that are not exactly zero."""

        return self.position_singularity_candidate_count

    @property
    def local_integer_discrepancy_l1_total(self) -> int:
        """Sum of exact L1 norms of all candidate residuals."""

        return sum(value for entry in self.entries for value in entry.local_integer_discrepancy_l1)

    @property
    def local_integer_discrepancy_l1_max(self) -> int:
        """Maximum exact L1 norm among candidate residuals."""

        return max(
            (value for entry in self.entries for value in entry.local_integer_discrepancy_l1),
            default=0,
        )

    @property
    def branch_entry_count(self) -> int:
        return sum(entry.branch_entry for entry in self.entries)

    @property
    def branch_offset_difference_count(self) -> int:
        return sum(len(entry.branch_offset_differences) for entry in self.entries)

    @property
    def branch_offset_span_total(self) -> int:
        return sum(entry.branch_offset_span for entry in self.entries)

    @property
    def branch_offset_span_max(self) -> int:
        return max((entry.branch_offset_span for entry in self.entries), default=0)

    @property
    def branch_loss_count(self) -> int:
        return sum(entry.branch_loss_count for entry in self.entries)

    @property
    def half_index_entry_count(self) -> int:
        return sum(bool(entry.expected_half_index_branches) for entry in self.entries)

    @property
    def half_index_expected_branch_count(self) -> int:
        return sum(len(entry.expected_half_index_branches) for entry in self.entries)

    @property
    def half_index_observed_branch_count(self) -> int:
        return sum(len(entry.observed_half_index_branches) for entry in self.entries)

    @property
    def half_index_branch_loss_count(self) -> int:
        return sum(entry.half_index_branch_loss_count for entry in self.entries)


def build_messy_grid_discrepancy_ledger(
    posy_ledger: PositionOffsetLedger,
    *,
    shape_name: str = "",
    n_vertices: int = 0,
    n_sweeps: int = 0,
    seed: int = 0,
    multires: bool = True,
) -> MessyGridDiscrepancyLedger:
    """Convert the immutable POSY ledger into a discrepancy-only view.

    ``expected_branch_indices`` are the options carried from the existing
    QUAD-SINGULARITY1 source ledger.  ``observed_branch_indices`` are the
    candidate labels actually present in QUAD-POSY1.  A lost branch is an
    exact set difference; no numerical comparison or tolerance is used.
    Half-index branches are the source labels ``-2`` and ``+2`` (the existing
    quarter-turn encoding of ``-1/2`` and ``+1/2``).
    """

    entries: list[MessyGridDiscrepancyEntry] = []
    for source in posy_ledger.entries:
        expected = _unique_sorted(source.admissible_orientation_indices)
        observed = _unique_sorted(
            tuple(candidate.orientation_index for candidate in source.candidates)
        )
        lost = tuple(value for value in expected if value not in observed)
        differences = _pairwise_positive_differences(expected)
        half_expected = tuple(value for value in expected if abs(value) == 2)
        half_observed = tuple(value for value in observed if abs(value) == 2)
        half_lost = tuple(value for value in half_expected if value not in half_observed)
        residuals = tuple(candidate.regularity_residual for candidate in source.candidates)
        residual_l1 = tuple(abs(x) + abs(y) for x, y in residuals)
        entries.append(
            MessyGridDiscrepancyEntry(
                face=source.face,
                face_vertex_ids=source.face_vertex_ids,
                centroid=source.centroid,
                unresolved=source.unresolved,
                unresolved_reasons=source.unresolved_reasons,
                expected_branch_indices=expected,
                observed_branch_indices=observed,
                lost_branch_indices=lost,
                branch_offset_differences=differences,
                branch_offset_span=max(differences, default=0),
                local_integer_discrepancies=residuals,
                local_integer_discrepancy_l1=residual_l1,
                position_singularity=any(value != (0, 0) for value in residuals),
                expected_half_index_branches=half_expected,
                observed_half_index_branches=half_observed,
                lost_half_index_branches=half_lost,
            )
        )
    return MessyGridDiscrepancyLedger(
        shape_name=shape_name,
        n_vertices=n_vertices,
        n_sweeps=n_sweeps,
        seed=seed,
        multires=multires,
        entries=tuple(entries),
    )


__all__ = [
    "MessyGridDiscrepancyEntry",
    "MessyGridDiscrepancyLedger",
    "build_messy_grid_discrepancy_ledger",
]
