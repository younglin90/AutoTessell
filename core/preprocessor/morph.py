"""메쉬 모핑 모듈 (선택적 형상 최적화 기능).

PyGeM RBF 기반 메쉬 변형을 수행한다.
주로 형상 최적화 루프에서 제어점 기반 메쉬 변형에 사용.
PyGeM이 미설치되면 NotImplementedError를 발생시킨다.
"""

from __future__ import annotations

import numpy as np
import trimesh

from core.utils.logging import get_logger

log = get_logger(__name__)

try:
    # PyGeM: https://github.com/PyGeM/PyGeM
    # RBF 기반 변형 클래스 임포트
    from pygem.rbf import RBFInterpolation  # noqa: F401

    _PYGEM_AVAILABLE = True
except (ImportError, AttributeError):
    _PYGEM_AVAILABLE = False
    log.debug("pygem_unavailable", msg="PyGeM 미설치 또는 호환 불가 — RBF 모핑 비활성화")


class MeshMorpher:
    """RBF 기반 메쉬 모핑기.

    제어점(control points)의 변위 before/after를 기반으로
    전체 메쉬를 Radial Basis Function 보간으로 변형한다.
    """

    def rbf_morph(
        self,
        mesh: trimesh.Trimesh,
        control_points_before: np.ndarray,
        control_points_after: np.ndarray,
    ) -> trimesh.Trimesh:
        """RBF 기반 메쉬 변형 수행.

        Args:
            mesh: 입력 trimesh.Trimesh 객체.
            control_points_before: (N, 3) 변형 전 제어점 위치.
            control_points_after: (N, 3) 변형 후 제어점 위치.

        Returns:
            변형된 trimesh.Trimesh (PyGeM 미설치 시 원본).

        Raises:
            NotImplementedError: PyGeM이 설치되지 않았을 때.
        """
        if not _PYGEM_AVAILABLE:
            raise NotImplementedError(
                "PyGeM이 설치되지 않았습니다. "
                "RBF 모핑이 필요하면 설치하세요: pip install pygem"
            )

        # 입력 검증
        control_points_before = np.asarray(control_points_before, dtype=np.float64)
        control_points_after = np.asarray(control_points_after, dtype=np.float64)

        if control_points_before.shape != control_points_after.shape:
            raise ValueError(
                f"control_points_before {control_points_before.shape} "
                f"!= control_points_after {control_points_after.shape}"
            )

        if control_points_before.shape[1] != 3:
            raise ValueError(
                f"제어점은 (N, 3) 형태여야 합니다. 받은 형태: {control_points_before.shape}"
            )

        try:
            # RBFInterpolation 객체 생성 및 학습
            rbf = RBFInterpolation()

            # 제어점 설정: x_0 (변형 전), x (변형 후)
            rbf.original_control_points = control_points_before
            rbf.deformed_control_points = control_points_after

            # 메쉬 정점에 RBF 변형 적용
            vertices = np.asarray(mesh.vertices, dtype=np.float64)
            deformed_vertices = rbf(vertices)

            # 변형된 메쉬 생성
            result = trimesh.Trimesh(
                vertices=deformed_vertices,
                faces=mesh.faces,
                process=False,
            )

            log.info(
                "rbf_morph_done",
                num_control_points=len(control_points_before),
                num_vertices=len(vertices),
            )

            return result

        except Exception as exc:
            log.warning("rbf_morph_failed", error=str(exc))
            raise

    def rbf_morph_safe(
        self,
        mesh: trimesh.Trimesh,
        control_points_before: np.ndarray,
        control_points_after: np.ndarray,
    ) -> tuple[trimesh.Trimesh, bool]:
        """RBF 모핑 안전 래퍼.

        실패 시 예외 대신 (원본_메쉬, False)를 반환한다.

        Args:
            mesh: 입력 trimesh.Trimesh 객체.
            control_points_before: (N, 3) 변형 전 제어점.
            control_points_after: (N, 3) 변형 후 제어점.

        Returns:
            (변형된_메쉬_또는_원본, 성공_여부) 튜플.
        """
        try:
            morphed = self.rbf_morph(mesh, control_points_before, control_points_after)
            return morphed, True
        except NotImplementedError:
            log.info(
                "rbf_morph_safe_pygem_unavailable",
                msg="PyGeM 미설치 — 원본 반환",
            )
            return mesh, False
        except Exception as exc:
            log.warning(
                "rbf_morph_safe_failed",
                error=str(exc),
                fallback="return_original_mesh",
            )
            return mesh, False
