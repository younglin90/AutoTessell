"""Tier 0: MeshPy 기반 2D 메시 생성기 (2D 입구/출구/단면용).

3D STL을 2D 평면으로 투영한 후 Triangle Delaunay 메싱을 수행한다.
입구/출구 또는 단면 메싱에 적합.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from core.generator.polymesh_writer import PolyMeshWriter
from core.schemas import MeshStrategy, TierAttempt
from core.utils.errors import format_missing_dependency_message
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier0_2d_meshpy"


class Tier2DMeshPyGenerator:
    """MeshPy Triangle 기반 2D 메시 생성기.

    3D STL을 2D 평면으로 투영한 후 Delaunay 삼각형 메싱을 수행한다.
    입구/출구/단면 메싱에 적합한 2D 메시를 생성한다.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        """MeshPy Triangle 2D 파이프라인을 실행한다.

        Args:
            strategy: 메쉬 전략.
            preprocessed_path: 전처리된 STL 파일 경로.
            case_dir: OpenFOAM 케이스 디렉터리 경로.

        Returns:
            실행 결과를 담은 TierAttempt.
        """
        t_start = time.monotonic()
        logger.info("tier0_2d_meshpy_start", preprocessed_path=str(preprocessed_path))

        # meshpy import 시도
        try:
            import meshpy.triangle as mtri  # noqa: F401
        except ImportError as exc:
            elapsed = time.monotonic() - t_start
            logger.warning(
                "tier0_2d_meshpy_import_failed",
                error=str(exc),
                hint="meshpy 미설치. pip install meshpy",
            )
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=format_missing_dependency_message(
                    dependency="meshpy",
                    fallback="3D 메시로 전환",
                    action="pip install meshpy",
                    detail=str(exc),
                ),
            )

        # 파일 존재 확인
        if not preprocessed_path.exists():
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"전처리 파일을 찾을 수 없습니다: {preprocessed_path}",
            )

        try:
            import meshpy.triangle as mtri
            import trimesh as _trimesh

            # STL 로드
            surf: _trimesh.Trimesh = _trimesh.load(
                str(preprocessed_path), force="mesh"
            )  # type: ignore[assignment]

            # 2D 평면 감지 및 투영
            plane_axis, projected_2d, z_values = self._detect_and_project_2d(surf.vertices)
            logger.info(
                "tier0_2d_projection_done",
                plane_axis=plane_axis,
                z_range=f"[{z_values.min():.6f}, {z_values.max():.6f}]",
            )

            # 경계 추출 및 정규화
            boundary_2d = self._extract_boundary(projected_2d, surf.faces)
            logger.info(
                "tier0_2d_boundary_extracted",
                num_boundary_pts=len(boundary_2d),
            )

            # 파라미터 설정
            params = strategy.tier_specific_params
            target_area = params.get(
                "meshpy_max_area_2d",
                (strategy.surface_mesh.target_cell_size ** 2) / 2.0,
            )
            min_angle = params.get("meshpy_min_angle", 30.0)

            logger.info(
                "tier0_2d_meshing",
                target_area=target_area,
                min_angle=min_angle,
            )

            # MeshPy Triangle MeshInfo 구성
            mesh_info = mtri.MeshInfo()
            mesh_info.set_points(projected_2d.tolist())

            # 경계 추적: boundary_2d의 연속된 포인트를 facet으로 지정
            facets = [[i, (i + 1) % len(boundary_2d)] for i in range(len(boundary_2d))]
            mesh_info.set_facets(facets)

            # Triangle 옵션: 품질 메싱
            opts = mtri.Options(
                "p",  # p=PLCmesh (경계 조건 메싱)
                max_area=target_area,
                min_angle=min_angle,
            )

            result_mesh = mtri.build(mesh_info, opts)

            tri_v_2d = np.array(result_mesh.points, dtype=np.float64)
            tri_f = np.array(result_mesh.elements, dtype=np.int64)

            if len(tri_v_2d) == 0 or len(tri_f) == 0:
                raise RuntimeError("MeshPy Triangle이 빈 메쉬를 반환했습니다.")

            logger.info(
                "tier0_2d_mesh_built",
                num_points_2d=len(tri_v_2d),
                num_triangles=len(tri_f),
            )

            # 2D 메시를 3D로 확장 (Z 값 복원)
            tri_v_3d = self._expand_2d_to_3d(tri_v_2d, plane_axis, z_values.mean())

            # 2D 삼각형 메시를 Tet으로 extrude하여 OpenFOAM polyMesh 변환
            mesh_stats = self._write_2d_polymesh(tri_v_3d, tri_f, case_dir, plane_axis)

            elapsed = time.monotonic() - t_start
            logger.info("tier0_2d_meshpy_success", elapsed=elapsed, mesh_stats=mesh_stats)

            return TierAttempt(
                tier=TIER_NAME,
                status="success",
                time_seconds=elapsed,
            )

        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier0_2d_meshpy_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"Tier 0 (2D) 실행 실패: {exc}",
            )

    def _detect_and_project_2d(
        self,
        vertices: npt.NDArray[Any],
    ) -> tuple[str, npt.NDArray[Any], npt.NDArray[Any]]:
        """3D 점군을 2D 평면으로 투영한다.

        Z 좌표 분산이 가장 작은 축을 평면으로 선택한다.

        Args:
            vertices: (N, 3) float array.

        Returns:
            (plane_axis, projected_2d, z_values) tuple:
            - plane_axis: "XY", "XZ", "YZ" 중 하나
            - projected_2d: (N, 2) float array (투영된 2D 좌표)
            - z_values: (N,) float array (투영 축의 원래 값)
        """
        z_var = vertices[:, 2].var()
        y_var = vertices[:, 1].var()
        x_var = vertices[:, 0].var()

        variances = {"X": x_var, "Y": y_var, "Z": z_var}
        min_axis = min(variances, key=variances.get)

        if min_axis == "Z":
            plane_axis = "XY"
            projected_2d = vertices[:, :2]
            z_values = vertices[:, 2]
        elif min_axis == "Y":
            plane_axis = "XZ"
            projected_2d = vertices[:, [0, 2]]
            z_values = vertices[:, 1]
        else:  # X
            plane_axis = "YZ"
            projected_2d = vertices[:, [1, 2]]
            z_values = vertices[:, 0]

        logger.debug(
            "detect_and_project_2d",
            plane_axis=plane_axis,
            variances=variances,
        )

        return plane_axis, projected_2d, z_values

    def _extract_boundary(
        self,
        projected_2d: npt.NDArray[Any],
        faces: npt.NDArray[Any],
    ) -> npt.NDArray[Any]:
        """삼각형 메시의 경계를 추출한다.

        경계 에지(1개의 인접 삼각형만 가진 에지)를 찾아 정렬된 경로로 변환한다.

        Args:
            projected_2d: (N, 2) float array (2D 좌표).
            faces: (M, 3) int array (삼각형 면 인덱스).

        Returns:
            (K, 2) float array (경계 점들의 정렬된 순서).
        """
        # 에지 → 인접 삼각형 수 맵핑
        edge_count = {}
        for face in faces:
            for i in range(3):
                v1, v2 = face[i], face[(i + 1) % 3]
                edge = tuple(sorted([v1, v2]))
                edge_count[edge] = edge_count.get(edge, 0) + 1

        # 경계 에지: 1개의 삼각형에만 인접
        boundary_edges = [edge for edge, cnt in edge_count.items() if cnt == 1]

        if not boundary_edges:
            logger.warning("no_boundary_edges_found", fallback="전체 점 사용")
            return projected_2d

        # 경계 에지를 연결된 경로로 정렬
        edge_dict = {}
        for v1, v2 in boundary_edges:
            if v1 not in edge_dict:
                edge_dict[v1] = []
            edge_dict[v1].append(v2)

        # DFS로 경계 추적
        boundary_path = [boundary_edges[0][0]]
        current = boundary_edges[0][1]
        visited = set([boundary_edges[0]])

        while current != boundary_path[0] and len(boundary_path) < len(boundary_edges) + 10:
            boundary_path.append(current)
            neighbors = edge_dict.get(current, [])
            next_v = None
            for neighbor in neighbors:
                edge = tuple(sorted([current, neighbor]))
                if edge not in visited:
                    visited.add(edge)
                    next_v = neighbor
                    break
            if next_v is None:
                break
            current = next_v

        boundary_indices = np.array(boundary_path, dtype=int)
        boundary_2d = projected_2d[boundary_indices]

        logger.info(
            "extract_boundary_done",
            num_boundary_edges=len(boundary_edges),
            boundary_path_length=len(boundary_path),
        )

        return boundary_2d

    def _expand_2d_to_3d(
        self,
        tri_v_2d: npt.NDArray[Any],
        plane_axis: str,
        z_mean: float,
    ) -> npt.NDArray[Any]:
        """2D 메시를 3D로 확장한다.

        평면축에 평균 Z 값을 복원하여 3D 좌표를 생성한다.

        Args:
            tri_v_2d: (N, 2) float array (2D 메시 점).
            plane_axis: "XY", "XZ", "YZ".
            z_mean: 복원할 평면축 값.

        Returns:
            (N, 3) float array (3D 확장된 점).
        """
        tri_v_3d = np.zeros((len(tri_v_2d), 3), dtype=np.float64)

        if plane_axis == "XY":
            tri_v_3d[:, 0] = tri_v_2d[:, 0]
            tri_v_3d[:, 1] = tri_v_2d[:, 1]
            tri_v_3d[:, 2] = z_mean
        elif plane_axis == "XZ":
            tri_v_3d[:, 0] = tri_v_2d[:, 0]
            tri_v_3d[:, 1] = z_mean
            tri_v_3d[:, 2] = tri_v_2d[:, 1]
        else:  # YZ
            tri_v_3d[:, 0] = z_mean
            tri_v_3d[:, 1] = tri_v_2d[:, 0]
            tri_v_3d[:, 2] = tri_v_2d[:, 1]

        return tri_v_3d

    def _write_2d_polymesh(
        self,
        vertices: npt.NDArray[Any],
        faces: npt.NDArray[Any],
        case_dir: Path,
        plane_axis: str,
    ) -> dict[str, int]:
        """2D 삼각형 메시를 OpenFOAM polyMesh로 변환한다.

        각 2D 삼각형을 extrude하여 3개의 Tet으로 분할한 후 polyMesh 생성.

        Args:
            vertices: (N, 3) float array (3D 확장된 점).
            faces: (M, 3) int array (삼각형 면).
            case_dir: OpenFOAM 케이스 디렉터리.
            plane_axis: "XY", "XZ", "YZ" (경계 조건 분류용).

        Returns:
            메시 통계 dict.
        """
        extrude_height = 0.001
        normal = self._get_normal_vector(plane_axis)

        # 확장된 정점: 원본 + 확장된 복사본
        vertices_extruded = np.vstack([
            vertices,
            vertices + normal * extrude_height,
        ])

        n_orig = len(vertices)

        # 각 2D 삼각형을 extrude하여 prism으로 만들고, 3개의 Tet으로 분할
        # 삼각형 [v0, v1, v2] → Prism [v0, v1, v2, v0_top, v1_top, v2_top]
        # Prism을 3개의 Tet으로 분할
        tets = []
        for v0, v1, v2 in faces:
            v0_top = v0 + n_orig
            v1_top = v1 + n_orig
            v2_top = v2 + n_orig

            # Prism을 3개의 Tet으로 분할 (표준 분할)
            tets.append([v0, v1, v2, v0_top])
            tets.append([v1, v1_top, v0_top, v2_top])
            tets.append([v1, v2, v2_top, v1_top])

        tets_array = np.array(tets, dtype=np.int64)

        logger.info(
            "write_2d_polymesh",
            num_vertices=len(vertices_extruded),
            num_triangles=len(faces),
            num_tets=len(tets_array),
        )

        writer = PolyMeshWriter()
        mesh_stats = writer.write(vertices_extruded, tets_array, case_dir)

        return mesh_stats

    def _get_normal_vector(self, plane_axis: str) -> npt.NDArray[Any]:
        """평면에 수직인 단위 벡터를 반환한다.

        Args:
            plane_axis: "XY", "XZ", "YZ".

        Returns:
            (3,) float array (단위 법선 벡터).
        """
        if plane_axis == "XY":
            return np.array([0.0, 0.0, 1.0], dtype=np.float64)
        elif plane_axis == "XZ":
            return np.array([0.0, 1.0, 0.0], dtype=np.float64)
        else:  # YZ
            return np.array([1.0, 0.0, 0.0], dtype=np.float64)
