"""Ordered multi-surface Boolean occupancy and patch provenance."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np

from core.analyzer.file_reader import load_mesh
from core.utils.boundary_provenance import SourceSurfacePatchClassifier
from core.utils.geometry import inside_boolean_winding_number


class BooleanSurfaceSet:
    """Load source surfaces once and classify points with ordered Boolean rules."""

    OPERATIONS = frozenset({"union", "intersection", "difference"})

    def __init__(
        self,
        input_paths: Sequence[str | Path],
        *,
        operation: str = "union",
        source_names: Sequence[str] | None = None,
    ) -> None:
        self.input_paths = tuple(Path(path) for path in input_paths)
        if len(self.input_paths) < 2:
            raise ValueError("boolean operation requires at least two input surfaces")
        self.operation = str(operation).strip().lower()
        if self.operation not in self.OPERATIONS:
            raise ValueError(f"unsupported boolean operation: {operation!r}")
        if source_names is not None and len(source_names) != len(self.input_paths):
            raise ValueError("source_names must align with input_paths")

        surfaces: list[tuple[np.ndarray, np.ndarray]] = []
        for path in self.input_paths:
            mesh = load_mesh(path)
            vertices = np.asarray(mesh.vertices, dtype=np.float64)
            faces = np.asarray(mesh.faces, dtype=np.int64)
            if vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices):
                raise ValueError(f"source surface has invalid vertices: {path}")
            if faces.ndim != 2 or faces.shape[1] != 3 or not len(faces):
                raise ValueError(f"source surface has invalid faces: {path}")
            surfaces.append((vertices, faces))
        self.surfaces = tuple(surfaces)
        self.patch_classifier = SourceSurfacePatchClassifier(
            self.input_paths, source_names
        )

    def contains(self, points: np.ndarray) -> np.ndarray:
        """Return one Boolean occupancy mask aligned with ``points``."""
        query = np.asarray(points, dtype=np.float64)
        return inside_boolean_winding_number(
            query,
            list(self.surfaces),
            operation=self.operation,
        )
