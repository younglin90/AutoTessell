"""CoreSurfaceMesh — AutoTessell 자체 표면 메쉬 표현.

trimesh.Trimesh 대체. numpy 배열 기반의 경량 dataclass 로, reader 의 공통 반환
타입. 지오메트리 연산은 별도 유틸 (core/analyzer/topology.py) 에서 제공한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class CoreSurfaceMesh:
    """표면 메쉬 (vertices + triangular faces).

    Attributes:
        vertices: (V, 3) float64 좌표.
        faces: (F, 3) int64 vertex index (triangles only).
        metadata: 포맷별 부가 정보 (파일명, header comment 등).
    """

    vertices: np.ndarray
    faces: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.vertices = np.asarray(self.vertices, dtype=np.float64)
        self.faces = np.asarray(self.faces, dtype=np.int64)
        if self.vertices.ndim != 2 or self.vertices.shape[1] != 3:
            raise ValueError(
                f"vertices shape must be (V,3), got {self.vertices.shape}"
            )
        if self.faces.size and (self.faces.ndim != 2 or self.faces.shape[1] != 3):
            raise ValueError(
                f"faces shape must be (F,3) for triangles, got {self.faces.shape}"
            )

    # ------------------------------------------------------------------
    # 기본 속성 (trimesh.Trimesh 호환성)
    # ------------------------------------------------------------------

    @property
    def n_vertices(self) -> int:
        return int(self.vertices.shape[0])

    @property
    def n_faces(self) -> int:
        return int(self.faces.shape[0])

    def compute_face_normals(self) -> np.ndarray:
        """각 face 의 non-unit normal vector (cross product)."""
        if self.n_faces == 0:
            return np.zeros((0, 3), dtype=np.float64)
        v = self.vertices[self.faces]
        return np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])

    def compute_face_areas(self) -> np.ndarray:
        """각 face 의 (signed) area (0.5 * |cross|)."""
        if self.n_faces == 0:
            return np.zeros((0,), dtype=np.float64)
        return 0.5 * np.linalg.norm(self.compute_face_normals(), axis=1)

    def compute_bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        if self.n_vertices == 0:
            z = np.zeros(3)
            return z, z
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    def __repr__(self) -> str:
        return (
            f"CoreSurfaceMesh(V={self.n_vertices}, F={self.n_faces}, "
            f"metadata_keys={list(self.metadata.keys())})"
        )
