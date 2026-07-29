"""Read-only Chen worklist for source facets missing from a tet complex.

The current seed/re-Delaunay recovery merely adds off-surface barycentres.  A
constrained replacement needs a per-source-facet record of the actual local
intersection states before a Chen template can be selected.  This module
extracts that record without changing points, tets, or source connectivity.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from core.generator.native_tet.chen_penetration_l0 import (
    ChenPenetrationClassification,
    classify_constraint_triangle_penetration,
)
from core.generator.native_tet.insertion import find_missing_triangles


@dataclass(frozen=True)
class ChenSourceFacetWorkItem:
    """One direct-missing source face and its exact local tet classifications."""

    source_face_index: int
    source_face: tuple[int, int, int]
    unique_tet_ids: tuple[int, ...]
    subface_tet_ids: tuple[int, ...]
    ambiguous_tet_ids: tuple[int, ...]
    classification_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ChenSourceFacetWorklistResult:
    """Deterministic report-only recovery prerequisite."""

    accepted: bool
    reason: str
    missing_face_indices: tuple[int, ...]
    items: tuple[ChenSourceFacetWorkItem, ...]
    source_points_unchanged: bool
    production_mesh_changed: bool


def build_source_facet_recovery_worklist_l0(
    points: Sequence[Sequence[float | int]],
    tetrahedra: Sequence[Sequence[int]],
    source_faces: Sequence[Sequence[int]],
) -> ChenSourceFacetWorklistResult:
    """Classify every direct-missing source face against every current tet.

    ``unique`` is the only class eligible for a later literal Chen template.
    ``subface`` and all boundary/coplanar contacts are retained explicitly,
    rather than silently converted into a guessed ONE/TWO/THR/FOU template.
    """
    before = tuple(tuple(float(value) for value in point) for point in points)
    try:
        faces = tuple(
            (int(face[0]), int(face[1]), int(face[2]))
            for face in source_faces
            if len(face) == 3
        )
        tets = tuple(tuple(int(vertex) for vertex in tet) for tet in tetrahedra)
        if len(faces) != len(source_faces) or any(len(set(face)) != 3 for face in faces):
            raise ValueError
        if any(len(tet) != 4 or len(set(tet)) != 4 for tet in tets):
            raise ValueError
        if any(
            vertex < 0 or vertex >= len(before)
            for entity in (*faces, *tets)
            for vertex in entity
        ):
            raise ValueError
    except (TypeError, ValueError):
        return ChenSourceFacetWorklistResult(False, "invalid_source_or_tet_input", (), (), True, False)

    import numpy as np

    missing = tuple(int(index) for index in find_missing_triangles(
        np.asarray(faces, dtype=np.int64), np.asarray(tets, dtype=np.int64)
    ))
    items: list[ChenSourceFacetWorkItem] = []
    for source_index in missing:
        source_face = faces[source_index]
        source_triangle = tuple(before[vertex] for vertex in source_face)
        unique_ids: list[int] = []
        subface_ids: list[int] = []
        ambiguous_ids: list[int] = []
        counts: Counter[str] = Counter()
        for tet_index, tet in enumerate(tets):
            classification: ChenPenetrationClassification = classify_constraint_triangle_penetration(
                tuple(before[vertex] for vertex in tet), source_triangle
            )
            counts[classification.status] += 1
            if classification.status == "unique":
                unique_ids.append(tet_index)
            elif classification.status == "subface":
                subface_ids.append(tet_index)
            elif classification.status in {"coplanar_or_vertex_touch", "constraint_boundary_touch"}:
                ambiguous_ids.append(tet_index)
        items.append(ChenSourceFacetWorkItem(
            source_index,
            source_face,
            tuple(unique_ids),
            tuple(subface_ids),
            tuple(ambiguous_ids),
            tuple(sorted(counts.items())),
        ))
    unchanged = before == tuple(tuple(float(value) for value in point) for point in points)
    return ChenSourceFacetWorklistResult(
        True,
        "no_direct_missing_source_faces" if not items else "classified_direct_missing_source_faces",
        missing,
        tuple(items),
        unchanged,
        False,
    )
