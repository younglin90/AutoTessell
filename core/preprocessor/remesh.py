"""표면 리메쉬 모듈 (L2 단계).

pyacvd가 설치된 경우 Voronoi 기반 균일 리메쉬를 수행한다.
추가로 pymeshlab isotropic remeshing을 선택적으로 적용한다.
없을 경우 trimesh 패스스루.
L2 리메쉬 완료 후 gate 검사(watertight + manifold)를 수행한다.
"""

from __future__ import annotations

import time

import trimesh

from core.schemas import GeometryReport
from core.utils.logging import get_logger

log = get_logger(__name__)

try:
    import pyacvd  # type: ignore[import]
    import pyvista as pv  # type: ignore[import]
    _PYACVD_AVAILABLE = True
except ImportError:
    _PYACVD_AVAILABLE = False
    log.info("pyacvd_unavailable", msg="pyacvd/pyvista 미설치 — 리메쉬 패스스루")

try:
    import pymeshlab  # type: ignore[import]
    _PYMESHLAB_AVAILABLE = True
except ImportError:
    _PYMESHLAB_AVAILABLE = False
    log.info("pymeshlab_unavailable", msg="pymeshlab 미설치 — isotropic remesh 건너뜀")


class SurfaceRemesher:
    """표면 리메쉬기 (L2).

    pyACVD Voronoi 기반 균일 리메쉬를 수행하여 삼각형 품질을 향상시킨다.
    remesh_l2()는 (mesh, gate_passed, step_record) 튜플을 반환한다.
    """

    def remesh_l2(
        self,
        mesh: trimesh.Trimesh,
        target_faces: int | None = None,
        element_size: float | None = None,
    ) -> tuple[trimesh.Trimesh, bool, dict]:
        """L2 리메쉬 수행 후 gate 검사.

        pyACVD로 1차 균일 리메쉬 후 pymeshlab isotropic remeshing을 선택 적용한다.

        Args:
            mesh: 입력 trimesh.Trimesh 객체.
            target_faces: 목표 삼각형 수 (None이면 자동 계산).
            element_size: pymeshlab isotropic remesh용 목표 엣지 길이 (None이면 건너뜀).

        Returns:
            (리메쉬된 메쉬, gate_passed, step_record) 튜플.
        """
        from core.preprocessor.repair import gate_check

        step_start = time.perf_counter()
        input_faces = len(mesh.faces)
        methods_used: list[str] = []

        remeshed = mesh
        # pyACVD 리메쉬
        computed_target = target_faces or self._compute_target_faces(mesh)
        if _PYACVD_AVAILABLE:
            try:
                remeshed = self._run_pyacvd(remeshed, computed_target)
                methods_used.append("pyacvd")
            except Exception as exc:
                log.warning("l2_pyacvd_failed", error=str(exc))
        else:
            log.info("l2_pyacvd_skipped", reason="pyacvd unavailable")

        # pymeshlab isotropic remesh (선택적 추가 개선)
        if _PYMESHLAB_AVAILABLE and element_size is not None:
            try:
                remeshed = self._run_pymeshlab_isotropic(remeshed, element_size)
                methods_used.append("pymeshlab")
            except Exception as exc:
                log.warning("l2_pymeshlab_failed", error=str(exc))
        elif _PYMESHLAB_AVAILABLE and not _PYACVD_AVAILABLE:
            # pyACVD 없을 때 pymeshlab만으로 대체 시도
            try:
                auto_size = self._estimate_element_size(remeshed)
                remeshed = self._run_pymeshlab_isotropic(remeshed, auto_size)
                methods_used.append("pymeshlab")
            except Exception as exc:
                log.warning("l2_pymeshlab_fallback_failed", error=str(exc))

        elapsed = time.perf_counter() - step_start
        passed = gate_check(remeshed)
        method_str = "+".join(methods_used) if methods_used else "passthrough"

        log.info(
            "l2_remesh_gate",
            gate_passed=passed,
            is_watertight=remeshed.is_watertight,
            methods=methods_used,
            input_faces=input_faces,
            output_faces=len(remeshed.faces),
        )

        step_record = {
            "step": "l2_remesh",
            "method": method_str,
            "params": {
                "target_faces": computed_target,
                "subdivide": 3,
            },
            "input_faces": input_faces,
            "output_faces": len(remeshed.faces),
            "time_seconds": round(elapsed, 4),
            "gate_passed": passed,
        }
        return remeshed, passed, step_record

    def _estimate_element_size(self, mesh: trimesh.Trimesh) -> float:
        """BBox 대각선 기반 목표 엣지 길이 추정."""
        bbox_extents = mesh.bounding_box.extents
        diagonal = float((bbox_extents ** 2).sum() ** 0.5)
        return max(diagonal / 50.0, 1e-9)

    def _run_pymeshlab_isotropic(
        self,
        mesh: trimesh.Trimesh,
        element_size: float,
    ) -> trimesh.Trimesh:
        """pymeshlab isotropic explicit remeshing 수행."""
        import tempfile
        import numpy as np
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            in_stl = Path(tmp) / "in.stl"
            out_stl = Path(tmp) / "out.stl"
            mesh.export(str(in_stl))

            ms = pymeshlab.MeshSet()
            ms.load_new_mesh(str(in_stl))
            ms.meshing_isotropic_explicit_remeshing(
                targetlen=pymeshlab.AbsoluteValue(element_size)
            )
            ms.save_current_mesh(str(out_stl))

            result = trimesh.load(str(out_stl), force="mesh")
            if isinstance(result, trimesh.Scene):
                meshes = list(result.geometry.values())
                result = trimesh.util.concatenate(meshes)

        log.info(
            "pymeshlab_isotropic_done",
            element_size=element_size,
            output_faces=len(result.faces),
        )
        return result

    def should_remesh(self, report: GeometryReport) -> bool:
        """리메쉬 필요 여부 판단.

        조건:
        - edge_length_ratio > 100 (삼각형 크기 편차 과다)
        - num_faces > 200000 (과다 삼각형)
        - has_degenerate_faces == True

        Args:
            report: Analyzer가 생성한 GeometryReport.

        Returns:
            True이면 리메쉬 권장.
        """
        surface = report.geometry.surface
        if surface.edge_length_ratio > 100:
            log.info(
                "remesh_recommended",
                reason="edge_length_ratio > 100",
                value=surface.edge_length_ratio,
            )
            return True
        if surface.num_faces > 200_000:
            log.info(
                "remesh_recommended",
                reason="num_faces > 200000",
                value=surface.num_faces,
            )
            return True
        if surface.has_degenerate_faces:
            log.info("remesh_recommended", reason="has_degenerate_faces")
            return True
        return False

    def remesh(
        self,
        mesh: trimesh.Trimesh,
        target_faces: int | None = None,
    ) -> trimesh.Trimesh:
        """표면 균일 리메쉬 수행.

        Args:
            mesh: 입력 trimesh.Trimesh.
            target_faces: 목표 삼각형 수. None이면 자동 계산.

        Returns:
            리메쉬된 trimesh.Trimesh (pyacvd 미설치 시 원본 반환).
        """
        if not _PYACVD_AVAILABLE:
            log.info("remesh_passthrough", reason="pyacvd unavailable")
            return mesh

        computed_target = target_faces or self._compute_target_faces(mesh)
        log.info("remesh_start", target_faces=computed_target, input_faces=len(mesh.faces))

        try:
            return self._run_pyacvd(mesh, computed_target)
        except Exception as exc:
            log.warning("remesh_failed", error=str(exc), fallback="passthrough")
            return mesh

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    def _compute_target_faces(self, mesh: trimesh.Trimesh) -> int:
        """BBox 기반 목표 삼각형 수 자동 계산."""
        surface_area = float(mesh.area)
        # characteristic element size: bbox 대각선 / 50
        bbox_extents = mesh.bounding_box.extents
        diagonal = float((bbox_extents ** 2).sum() ** 0.5)
        element_size = max(diagonal / 50.0, 1e-9)

        target = int(surface_area / (element_size ** 2) * 2)
        target = max(10_000, min(100_000, target))
        log.info(
            "remesh_target_computed",
            surface_area=surface_area,
            element_size=element_size,
            target_faces=target,
        )
        return target

    def _run_pyacvd(self, mesh: trimesh.Trimesh, target_faces: int) -> trimesh.Trimesh:
        """pyacvd 리메쉬 실행."""
        import numpy as np

        # trimesh → pyvista PolyData 변환
        vertices = mesh.vertices
        faces = mesh.faces
        # pyvista face format: [3, v0, v1, v2, ...]
        n_faces = len(faces)
        pv_faces = np.hstack([
            np.full((n_faces, 1), 3, dtype=np.int64),
            faces.astype(np.int64),
        ]).ravel()

        poly = pv.PolyData(vertices, pv_faces)

        clus = pyacvd.Clustering(poly)
        clus.subdivide(3)
        clus.cluster(target_faces)
        remeshed_poly = clus.create_mesh()

        # pyvista → trimesh 변환
        pts = np.asarray(remeshed_poly.points)
        raw_faces = np.asarray(remeshed_poly.faces).reshape(-1, 4)
        tri_faces = raw_faces[:, 1:4]

        result = trimesh.Trimesh(vertices=pts, faces=tri_faces, process=False)
        log.info(
            "remesh_done",
            input_faces=len(mesh.faces),
            output_faces=len(result.faces),
        )
        return result
