"""표면 메쉬 수리 모듈 (L1 단계).

pymeshfix가 설치된 경우 우선 사용하고,
없을 경우 trimesh 기반 fallback으로 수리한다.
L1 수리 완료 후 gate 검사(watertight + manifold)를 수행한다.
"""

from __future__ import annotations

import time

import trimesh

from typing import Any

from core.schemas import Issue, Severity
from core.utils.logging import get_logger

log = get_logger(__name__)

try:
    import pymeshfix
    _PYMESHFIX_AVAILABLE = True
except ImportError:
    _PYMESHFIX_AVAILABLE = False
    log.info("pymeshfix_unavailable", msg="pymeshfix 미설치 — trimesh fallback 사용")


def gate_check(mesh: trimesh.Trimesh) -> bool:
    """Gate 검사: watertight + manifold 여부 확인.

    trimesh 4.x에서는 is_manifold 속성이 없으므로
    is_watertight + is_volume 조합으로 확인한다.

    Args:
        mesh: 검사할 trimesh.Trimesh 객체.

    Returns:
        watertight이고 manifold이면 True.
    """
    if not mesh.is_watertight:
        return False
    # is_volume: watertight + consistent winding + positive volume
    is_manifold = getattr(mesh, "is_manifold", None)
    if is_manifold is not None:
        return bool(is_manifold)
    # trimesh 4.x fallback
    return bool(getattr(mesh, "is_volume", mesh.is_winding_consistent))


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

        if not actions:
            method = "skipped"
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

        log.info(
            "repair_done",
            actions=actions,
            num_faces=len(mesh.faces),
            is_watertight=mesh.is_watertight,
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
                np.array(mesh.faces, dtype=np.int32),
            )
            meshfix.repair()
            repaired = trimesh.Trimesh(
                vertices=meshfix.v,
                faces=meshfix.f,
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
            log.warning("pymeshfix_failed", error=str(exc), fallback="trimesh")
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
