"""메쉬 시각화 유틸리티.

환경에 따라 polyscope(개발 환경) 또는 k3d(Jupyter) 를 사용한다.
각 라이브러리 import 실패 시 gracefully skip한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.utils.logging import get_logger

log = get_logger(__name__)

# polyscope import 시도
try:
    import polyscope as _ps

    _POLYSCOPE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _ps = None  # type: ignore[assignment]
    _POLYSCOPE_AVAILABLE = False

# k3d import 시도
try:
    import k3d as _k3d

    _K3D_AVAILABLE = True
except ImportError:  # pragma: no cover
    _k3d = None  # type: ignore[assignment]
    _K3D_AVAILABLE = False


def _is_jupyter() -> bool:
    """현재 Jupyter 노트북 환경 여부를 반환한다."""
    try:
        from IPython import get_ipython  # noqa: PLC0415

        shell = get_ipython()
        if shell is None:
            return False
        return "ZMQInteractiveShell" in type(shell).__name__
    except ImportError:
        return False


class MeshVisualizer:
    """메쉬 시각화 클래스.

    환경을 자동 감지하여 Jupyter에서는 k3d, 그 외에는 polyscope를 사용한다.
    """

    def show(
        self,
        vertices: Any,
        faces: Any,
        name: str = "mesh",
    ) -> Any:
        """환경에 따라 적절한 시각화 백엔드를 선택한다.

        Parameters
        ----------
        vertices:
            (N, 3) 형태의 꼭짓점 배열.
        faces:
            (M, 3) 형태의 삼각형 인덱스 배열.
        name:
            메쉬 이름.

        Returns
        -------
        Any
            polyscope 뷰어 또는 k3d Plot 객체. 사용 불가 시 None.
        """
        if _is_jupyter():
            return self.show_k3d(vertices, faces, name=name)
        return self.show_polyscope(vertices, faces, name=name)

    def show_polyscope(
        self,
        vertices: Any,
        faces: Any,
        name: str = "mesh",
    ) -> Any:
        """polyscope로 3D 대화형 뷰를 표시한다 (개발 환경).

        polyscope가 설치되지 않았거나 headless 환경에서는 skip한다.

        Parameters
        ----------
        vertices:
            (N, 3) 형태의 꼭짓점 배열.
        faces:
            (M, 3) 형태의 삼각형 인덱스 배열.
        name:
            polyscope 구조체 이름.

        Returns
        -------
        Any
            polyscope SurfaceMesh 구조체 또는 None.
        """
        if not _POLYSCOPE_AVAILABLE or _ps is None:
            log.warning("polyscope_not_available_skip")
            return None

        try:
            _ps.init()
            ps_mesh = _ps.register_surface_mesh(name, vertices, faces)
            _ps.show()
            log.info("polyscope_show_done", name=name)
            return ps_mesh
        except Exception as exc:  # noqa: BLE001
            log.warning("polyscope_show_failed", error=str(exc))
            return None

    def show_k3d(
        self,
        vertices: Any,
        faces: Any,
        name: str = "mesh",
    ) -> Any:
        """k3d로 Jupyter WebGL 뷰를 표시한다.

        k3d가 설치되지 않았거나 Jupyter 환경이 아니면 skip한다.

        Parameters
        ----------
        vertices:
            (N, 3) float32 꼭짓점 배열.
        faces:
            (M, 3) uint32 삼각형 인덱스 배열.
        name:
            plot 제목.

        Returns
        -------
        Any
            k3d Plot 객체 또는 None.
        """
        if not _K3D_AVAILABLE or _k3d is None:
            log.warning("k3d_not_available_skip")
            return None

        try:
            import numpy as np  # noqa: PLC0415

            v = np.asarray(vertices, dtype=np.float32)
            f = np.asarray(faces, dtype=np.uint32)

            plot = _k3d.plot(name=name)
            mesh_obj = _k3d.mesh(v, f)
            plot += mesh_obj
            plot.display()
            log.info("k3d_show_done", name=name)
            return plot
        except Exception as exc:  # noqa: BLE001
            log.warning("k3d_show_failed", error=str(exc))
            return None

    def save_screenshot(
        self,
        vertices: Any,
        faces: Any,
        path: Path | str,
        name: str = "mesh",
    ) -> bool:
        """헤드리스 스크린샷을 저장한다.

        polyscope의 headless 렌더링을 사용한다.
        실패 시 False를 반환하고 예외를 발생시키지 않는다.

        Parameters
        ----------
        vertices:
            (N, 3) 꼭짓점 배열.
        faces:
            (M, 3) 삼각형 인덱스 배열.
        path:
            저장할 이미지 파일 경로 (.png).
        name:
            polyscope 구조체 이름.

        Returns
        -------
        bool
            저장 성공 여부.
        """
        if not _POLYSCOPE_AVAILABLE or _ps is None:
            log.warning("polyscope_not_available_screenshot_skip")
            return False

        try:
            _ps.init()
            _ps.register_surface_mesh(name, vertices, faces)
            _ps.screenshot(str(path))
            log.info("screenshot_saved", path=str(path))
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("screenshot_failed", error=str(exc))
            return False
