"""Boundary patch provenance for meshes generated from multiple STL surfaces."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from core.analyzer.readers import read_stl
from core.utils.aabb import TriangleBVH

_UNSAFE_WORD_CHARS = re.compile(r"[^A-Za-z0-9_]+")


def _sanitized_stem(path: str | Path) -> str:
    """Return an ASCII OpenFOAM-safe file stem."""
    stem = _UNSAFE_WORD_CHARS.sub("_", Path(path).stem).strip("_")
    return stem or "surface"


def source_surface_patch_names(input_paths: Sequence[str | Path]) -> list[str]:
    """Return deterministic, collision-free patch names in source order."""
    return [
        f"source_{source_index}_{_sanitized_stem(path)}"
        for source_index, path in enumerate(input_paths)
    ]


class SourceSurfacePatchClassifier:
    """Classify output boundary faces by nearest original STL surface."""

    def __init__(self, input_paths: Sequence[str | Path]) -> None:
        paths = tuple(Path(path) for path in input_paths)
        if not paths:
            raise ValueError("at least one source surface is required")

        bvhs: list[TriangleBVH] = []
        for path in paths:
            mesh = read_stl(path)
            vertices = np.asarray(mesh.vertices, dtype=np.float64)
            faces = np.asarray(mesh.faces, dtype=np.int64)
            self._validate_surface(path, vertices, faces)
            bvhs.append(TriangleBVH.build(vertices, faces))

        self.input_paths = paths
        self.patch_names = tuple(source_surface_patch_names(paths))
        self._bvhs = tuple(bvhs)

    @staticmethod
    def _validate_surface(
        path: Path,
        vertices: np.ndarray,
        faces: np.ndarray,
    ) -> None:
        if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) == 0:
            raise ValueError(f"source surface has invalid vertices: {path}")
        if not np.isfinite(vertices).all():
            raise ValueError(f"source surface has non-finite vertices: {path}")
        if faces.ndim != 2 or faces.shape[1] != 3 or len(faces) == 0:
            raise ValueError(f"source surface has no valid triangles: {path}")
        if int(faces.min()) < 0 or int(faces.max()) >= len(vertices):
            raise ValueError(f"source surface has invalid triangle indices: {path}")

    def __call__(
        self,
        face: Sequence[int],
        vertices: np.ndarray,
    ) -> tuple[str, str]:
        """Classify one face while preserving the writer callback API."""
        return self.classify_many([face], vertices)[0]

    def classify_many(
        self,
        faces: Sequence[Sequence[int]],
        vertices: np.ndarray,
    ) -> list[tuple[str, str]]:
        """Classify face centroids with one vectorized query per source BVH."""
        if len(faces) == 0:
            return []

        points = np.asarray(vertices, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 3:
            raise ValueError("vertices must have shape (N, 3)")

        centroids: list[np.ndarray] = []
        for face in faces:
            indices = np.asarray(face, dtype=np.int64)
            if indices.ndim != 1 or len(indices) < 3:
                raise ValueError("boundary faces must contain at least three vertices")
            if int(indices.min()) < 0 or int(indices.max()) >= len(points):
                raise ValueError("boundary face contains an invalid vertex index")
            centroids.append(points[indices].mean(axis=0))

        centroid_array = np.asarray(centroids, dtype=np.float64)
        distances = np.stack(
            [bvh.unsigned_distances(centroid_array) for bvh in self._bvhs],
            axis=0,
        )
        nearest_sources = np.argmin(distances, axis=0)
        return [
            (self.patch_names[int(source_index)], "wall")
            for source_index in nearest_sources
        ]
