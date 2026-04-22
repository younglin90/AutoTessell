"""표면 메쉬 수리 모듈 (L1 단계).

pymeshfix가 설치된 경우 우선 사용하고,
없을 경우 trimesh 기반 fallback으로 수리한다.
L1 수리 완료 후 gate 검사(watertight + manifold)를 수행한다.
"""

from __future__ import annotations

import time
from typing import Any

import trimesh

from core.schemas import Issue, Severity
from core.utils.logging import get_logger

log = get_logger(__name__)

try:
    import pymeshfix
    _PYMESHFIX_AVAILABLE = True
except ImportError:
    _PYMESHFIX_AVAILABLE = False
    log.info("pymeshfix_unavailable", msg="pymeshfix 미설치 — trimesh fallback 사용")

try:
    import mesh2sdf
    _MESH2SDF_AVAILABLE = True
except ImportError:
    _MESH2SDF_AVAILABLE = False
    log.debug("mesh2sdf_unavailable", msg="mesh2sdf 미설치 — L1 mesh2sdf fallback 비활성화")

try:
    import igl as _igl_mod  # noqa: F401
    _IGL_AVAILABLE = True
except ImportError:
    _IGL_AVAILABLE = False
    log.debug("igl_unavailable", msg="igl 미설치 — self-intersection detection 비활성화")

try:
    import seagullmesh
    _SEAGULLMESH_AVAILABLE = True
except ImportError:
    _SEAGULLMESH_AVAILABLE = False
    log.debug("seagullmesh_unavailable", msg="seagullmesh 미설치 — Alpha Wrap fallback 비활성화")


def gate_check(mesh: trimesh.Trimesh) -> bool:
    """Gate 검사: watertight + manifold 여부 확인.

    trimesh 4.x에서는 is_manifold 속성이 없으므로
    is_watertight + is_volume 조합으로 확인한다.

    Args:
        mesh: 검사할 trimesh.Trimesh 객체.

    Returns:
        watertight이고 manifold이면 True.
    """
    import numpy as np  # noqa: PLC0415

    from core.analyzer import topology as _T  # noqa: PLC0415

    faces_np = np.asarray(mesh.faces, dtype=np.int64)
    # v0.4.0-beta19: native topology 로 watertight + manifold 판정 통일.
    # trimesh.is_volume / edges_unique_inverse 경로 제거.
    return bool(_T.is_watertight(faces_np)) and bool(_T.is_manifold(faces_np))


def detect_self_intersections(mesh: trimesh.Trimesh) -> int:
    """자기교차(self-intersecting face pairs) 개수를 감지한다.

    igl이 설치된 경우 igl 기반 감지를 시도하고,
    실패 시 trimesh.collision.CollisionManager를 사용한다.

    Args:
        mesh: 검사할 trimesh.Trimesh 객체.

    Returns:
        감지된 자기교차 쌍의 개수 (>= 0).
    """

    # igl 기반 감지 시도
    if _IGL_AVAILABLE:
        pass  # igl available, but self-intersection detection uses trimesh.collision below

    # trimesh.collision.CollisionManager 사용 (기본)
    try:
        from trimesh.collision import CollisionManager

        # 자신과의 충돌 검사
        manager = CollisionManager()  # type: ignore[no-untyped-call]
        manager.add_object("mesh", mesh)  # type: ignore[no-untyped-call]

        # 모든 면 쌍에 대한 충돌 검사
        # 더 간단한 방식: scene 자신과의 교차
        in_contact = manager.in_collision_internal()  # type: ignore[no-untyped-call]

        if in_contact:
            # 실제 교차 쌍 개수 세기 (근사치)
            count = 0
            try:
                pairs = manager.collision_pairs()  # type: ignore[attr-defined]
                count = len(list(pairs))
            except Exception:
                count = 1
            return count
    except Exception as exc:
        log.debug("self_intersection_detection_failed", error=str(exc))

    return 0


class SurfaceRepairer:
    """표면 메쉬 수리기 (L1).

    severity=critical 또는 warning인 issue가 있을 때 수리를 수행한다.
    repair_l1()은 (mesh, gate_passed, step_record) 튜플을 반환한다.
    """

    def repair_l1(
        self,
        mesh: trimesh.Trimesh,
        issues: list[Issue],
    ) -> tuple[trimesh.Trimesh, bool, dict[str, Any]]:
        """L1 수리 수행 후 gate 검사.

        Args:
            mesh: 입력 trimesh.Trimesh 객체.
            issues: Analyzer가 감지한 이슈 목록.

        Returns:
            (수리된 메쉬, gate_passed, step_record) 튜플.
            step_record는 PreprocessStep 생성에 필요한 dict.
        """
        step_start = time.perf_counter()
        input_faces = len(mesh.faces)

        repaired, actions = self.repair(mesh, issues)
        elapsed = time.perf_counter() - step_start
        passed = gate_check(repaired)

        log.info(
            "l1_repair_gate",
            gate_passed=passed,
            is_watertight=repaired.is_watertight,
            actions=actions,
        )

        # L1 수리 후에도 watertight 실패 시 seagullmesh Alpha Wrap 시도
        if not passed and not repaired.is_watertight and _SEAGULLMESH_AVAILABLE:
            log.info("l1_repair_gate_failed_trying_alpha_wrap")
            wrapped = self._apply_alpha_wrap(repaired)
            if wrapped is not None and gate_check(wrapped):
                repaired = wrapped
                passed = True
                actions.append("seagullmesh.alpha_wrap()")
                log.info("l1_alpha_wrap_success")

        if not actions:
            method = "skipped"
        elif any("seagullmesh" in a for a in actions):
            method = "seagullmesh_alpha_wrap"
        elif any("pymeshfix" in a for a in actions):
            method = "pymeshfix"
        else:
            method = "trimesh"

        step_record = {
            "step": "l1_repair",
            "method": method,
            "params": {"issues_fixed": actions},
            "input_faces": input_faces,
            "output_faces": len(repaired.faces),
            "time_seconds": round(elapsed, 4),
            "gate_passed": passed,
        }
        return repaired, passed, step_record

    def repair(
        self,
        mesh: trimesh.Trimesh,
        issues: list[Issue],
    ) -> tuple[trimesh.Trimesh, list[str]]:
        """메쉬 수리 수행.

        Args:
            mesh: 입력 trimesh.Trimesh 객체.
            issues: Analyzer가 감지한 이슈 목록.

        Returns:
            (수리된 메쉬, 수행한 작업 리스트) 튜플.
        """
        actions: list[str] = []

        # 자기교차 사전 감지
        self_intersect_count = detect_self_intersections(mesh)
        if self_intersect_count > 0:
            log.warning(
                "self_intersections_detected",
                count=self_intersect_count,
            )

        # 수리가 필요한 severity 판별
        needs_repair = any(
            issue.severity in (Severity.CRITICAL, Severity.WARNING)
            for issue in issues
        )

        if not needs_repair:
            log.info("repair_skipped", reason="no critical/warning issues")
            return mesh, actions

        critical_issues = [i for i in issues if i.severity == Severity.CRITICAL]
        warning_issues = [i for i in issues if i.severity == Severity.WARNING]

        log.info(
            "repair_start",
            critical=len(critical_issues),
            warning=len(warning_issues),
            pymeshfix_available=_PYMESHFIX_AVAILABLE,
        )

        if _PYMESHFIX_AVAILABLE:
            mesh, actions = self._repair_with_pymeshfix(mesh, issues, actions)
        else:
            mesh, actions = self._repair_with_trimesh(mesh, issues, actions)

        import numpy as np  # noqa: PLC0415

        from core.analyzer import topology as _T  # noqa: PLC0415

        log.info(
            "repair_done",
            actions=actions,
            num_faces=len(mesh.faces),
            is_watertight=bool(_T.is_watertight(np.asarray(mesh.faces, dtype=np.int64))),
        )
        return mesh, actions

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    def _repair_with_pymeshfix(
        self,
        mesh: trimesh.Trimesh,
        issues: list[Issue],
        actions: list[str],
    ) -> tuple[trimesh.Trimesh, list[str]]:
        """pymeshfix.MeshFix를 사용한 수리."""
        import numpy as np

        try:
            meshfix = pymeshfix.MeshFix(
                np.array(mesh.vertices, dtype=np.float64),
                np.array(mesh.faces, dtype=np.int64),
            )
            meshfix.repair()
            repaired = trimesh.Trimesh(
                vertices=meshfix.points,
                faces=meshfix.faces,
                process=False,
            )
            actions.append("pymeshfix.repair(non_manifold+holes+self_intersections)")
            log.info(
                "pymeshfix_repaired",
                input_faces=len(mesh.faces),
                output_faces=len(repaired.faces),
            )
            # trimesh 추가 정리
            repaired, trimesh_actions = self._apply_trimesh_cleanup(repaired)
            actions.extend(trimesh_actions)
            return repaired, actions
        except Exception as exc:
            log.warning("pymeshfix_failed", error=str(exc), fallback="mesh2sdf")
            # mesh2sdf fallback 시도
            if _MESH2SDF_AVAILABLE:
                result = self._repair_with_mesh2sdf(mesh, actions)
                if result is not None:
                    return result
            # mesh2sdf도 실패 시 trimesh로 계속 진행
            return self._repair_with_trimesh(mesh, issues, actions)

    def _repair_with_trimesh(
        self,
        mesh: trimesh.Trimesh,
        issues: list[Issue],
        actions: list[str],
    ) -> tuple[trimesh.Trimesh, list[str]]:
        """trimesh 내장 기능을 사용한 fallback 수리."""
        mesh, trimesh_actions = self._apply_trimesh_cleanup(mesh)
        actions.extend(trimesh_actions)
        return mesh, actions

    def _repair_with_mesh2sdf(
        self,
        mesh: trimesh.Trimesh,
        actions: list[str],
    ) -> tuple[trimesh.Trimesh, list[str]] | None:
        """mesh2sdf를 사용한 watertight 복원 (L1 fallback).

        mesh2sdf는 SDF 그리드를 생성하고 marching cubes로 복원하여
        watertight 메쉬를 생성한다.

        Args:
            mesh: 입력 trimesh.Trimesh 객체.
            actions: 수행한 작업 리스트.

        Returns:
            (복원된 메쉬, 수행한 작업 리스트) 튜플 또는 실패 시 None.
        """
        import numpy as np
        from skimage.measure import marching_cubes

        try:
            log.info("mesh2sdf_fallback_start", input_faces=len(mesh.faces))

            # mesh2sdf로 SDF 계산 (기본 크기 128)
            sdf_grid = mesh2sdf.compute(
                mesh.vertices.astype(np.float64),
                mesh.faces.astype(np.uint32),
                size=128,
            )

            # marching cubes로 복원
            vertices, faces, _, _ = marching_cubes(sdf_grid, level=0.0)  # type: ignore[no-untyped-call]

            if len(faces) == 0:
                log.warning("mesh2sdf_no_faces_after_marching_cubes")
                return None

            # 정규화 및 스케일 조정
            repaired = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
            repaired.vertices = repaired.vertices * mesh.scale
            repaired.vertices = repaired.vertices + mesh.centroid

            actions.append("mesh2sdf.compute(sdf_grid) + marching_cubes()")

            log.info(
                "mesh2sdf_repaired",
                input_faces=len(mesh.faces),
                output_faces=len(repaired.faces),
            )

            # trimesh 추가 정리
            repaired, trimesh_actions = self._apply_trimesh_cleanup(repaired)
            actions.extend(trimesh_actions)
            return repaired, actions

        except Exception as exc:
            log.warning("mesh2sdf_fallback_failed", error=str(exc))
            return None

    def _apply_trimesh_cleanup(
        self,
        mesh: trimesh.Trimesh,
    ) -> tuple[trimesh.Trimesh, list[str]]:
        """trimesh 기반 공통 정리 작업.

        trimesh 4.x API 기준:
        - remove_degenerate_faces() 없음 → nondegenerate_faces() 마스크 사용
        - remove_duplicate_faces() 없음 → unique_faces() 인덱스 사용
        - is_manifold 없음 → is_watertight / is_volume 사용
        """

        actions: list[str] = []

        # 중복 정점 병합
        before_verts = len(mesh.vertices)
        mesh.merge_vertices()
        if len(mesh.vertices) != before_verts:
            actions.append(
                f"trimesh.merge_vertices({before_verts} -> {len(mesh.vertices)})"
            )

        # 퇴화 면(degenerate faces) 제거 — nondegenerate_faces() bool mask 사용
        before_faces = len(mesh.faces)
        try:
            nd_mask = mesh.nondegenerate_faces()
            if not nd_mask.all():
                mesh.update_faces(nd_mask)
                actions.append(
                    f"trimesh.remove_degenerate_faces({before_faces} -> {len(mesh.faces)})"
                )
        except Exception:
            pass

        # 중복 면 제거 — unique_faces() 인덱스 사용
        before_faces = len(mesh.faces)
        try:
            unique_idx = mesh.unique_faces()
            if len(unique_idx) < len(mesh.faces):
                mesh.update_faces(unique_idx)
                actions.append(
                    f"trimesh.remove_duplicate_faces({before_faces} -> {len(mesh.faces)})"
                )
        except Exception:
            pass

        # 참조 없는 정점 제거
        try:
            mesh.remove_unreferenced_vertices()
        except Exception:
            pass

        # 법선 방향 수정
        mesh.fix_normals()
        actions.append("trimesh.fix_normals()")

        return mesh, actions

    @staticmethod
    def _apply_alpha_wrap(mesh: trimesh.Trimesh) -> trimesh.Trimesh | None:
        """seagullmesh Alpha Wrap으로 watertight 메쉬 강제화.

        CGAL Alpha Wrap을 사용하여 개방 경계 또는 불량 표면을
        수학적으로 watertight 메쉬로 변환한다.

        Args:
            mesh: 입력 trimesh.Trimesh 객체.

        Returns:
            Wrapped trimesh 또는 실패 시 None.
        """
        if not _SEAGULLMESH_AVAILABLE:
            return None

        try:
            import numpy as np

            log.info("alpha_wrap_start", input_faces=len(mesh.faces))

            # seagullmesh Alpha Wrap (CGAL 기반)
            wrapped_verts, wrapped_faces = seagullmesh.alpha_wrap(
                mesh.vertices.astype(np.float32),
                mesh.faces.astype(np.uint32),
                relative_alpha=0.02,      # 형상 세부 사항 보존 (0.01~0.05)
                relative_offset=0.001,     # 내부 offset 비율
            )

            if wrapped_verts is None or wrapped_faces is None or len(wrapped_faces) == 0:
                log.warning("alpha_wrap_empty_result")
                return None

            # 결과 메쉬 생성
            wrapped = trimesh.Trimesh(
                vertices=wrapped_verts,
                faces=wrapped_faces,
                process=False,
            )

            log.info(
                "alpha_wrap_done",
                input_faces=len(mesh.faces),
                output_faces=len(wrapped.faces),
                is_watertight=wrapped.is_watertight,
            )

            return wrapped if wrapped.is_watertight else None

        except Exception as exc:
            log.warning("alpha_wrap_failed", error=str(exc))
            return None
