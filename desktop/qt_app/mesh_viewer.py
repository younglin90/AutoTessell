"""PyVista 3D 메시 뷰어 — Qt 통합."""
from __future__ import annotations

from pathlib import Path

import pyvista as pv
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget


class MeshViewerWidget(QWidget):
    """PyVista 기반 3D 메시 뷰어.

    OpenFOAM polyMesh를 PyVista로 시각화한다.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """초기화.

        Args:
            parent: 부모 위젯.
        """
        super().__init__(parent)
        self._plotter: pv.Plotter | None = None
        self._canvas: QWidget | None = None
        self._mesh: pv.PolyData | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        """UI 초기화."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # PyVista Plotter 생성
        self._plotter = pv.Plotter(notebook=False, theme=pv.themes.DarkTheme())
        self._plotter.background_color = "#1e1e1e"

        # Qt Canvas 추출
        self._canvas = self._plotter.iren.get_render_window().GetNativeWindow()
        if hasattr(self._plotter, "iren"):
            # PySide6 호환성
            try:
                from pyvista.plotting.qt import QtInteractor
                # 기존 plotter에서 canvas 추출
                self._canvas = self._plotter.iren
            except ImportError:
                pass

        # Canvas를 layout에 추가
        if self._canvas is not None:
            layout.addWidget(self._canvas)

        self.setLayout(layout)

    def load_mesh(self, mesh_path: str | Path) -> bool:
        """메시 파일 로드 및 표시.

        Args:
            mesh_path: 메시 파일 경로 (STL, VTK, etc.)

        Returns:
            성공 여부.
        """
        try:
            mesh_path = Path(mesh_path)
            if not mesh_path.exists():
                return False

            # 파일 확장자에 따라 적절히 로드
            ext = mesh_path.suffix.lower()

            if ext == ".stl":
                self._mesh = pv.read(str(mesh_path))
            elif ext in {".vtu", ".vtk"}:
                self._mesh = pv.read(str(mesh_path))
            elif ext == ".vti":  # Structured grid
                self._mesh = pv.read(str(mesh_path))
            else:
                # 기본 로더 사용
                self._mesh = pv.read(str(mesh_path))

            if self._mesh is None:
                return False

            # 뷰어에 메시 추가
            self._display_mesh()
            return True

        except Exception as e:  # noqa: BLE001
            print(f"[오류] 메시 로드 실패: {e}")
            return False

    def load_polymesh(self, case_dir: str | Path) -> bool:
        """OpenFOAM polyMesh 로드.

        Args:
            case_dir: OpenFOAM case 디렉터리.

        Returns:
            성공 여부.
        """
        try:
            case_dir = Path(case_dir)
            polymesh_dir = case_dir / "constant" / "polyMesh"

            if not polymesh_dir.exists():
                return False

            # points 파일 읽기
            points_file = polymesh_dir / "points"
            faces_file = polymesh_dir / "faces"

            if not (points_file.exists() and faces_file.exists()):
                return False

            # OpenFOAM 형식 파서 (간단한 버전)
            # 실제로는 fluidfoam 라이브러리를 사용할 수 있음
            try:
                from fluidfoam import OpenFoamCase
                case = OpenFoamCase(str(case_dir))
                # polyMesh를 VTK로 변환 (구현 필요)
                # 여기서는 간단히 STL 검색
                stl_files = list(polymesh_dir.parent.glob("*.stl"))
                if stl_files:
                    return self.load_mesh(stl_files[0])
            except ImportError:
                pass

            # Fallback: constant/geometry.stl 확인
            geom_stl = case_dir / "constant" / "geometry.stl"
            if geom_stl.exists():
                return self.load_mesh(geom_stl)

            return False

        except Exception as e:  # noqa: BLE001
            print(f"[오류] polyMesh 로드 실패: {e}")
            return False

    def _display_mesh(self) -> None:
        """메시를 뷰어에 표시."""
        if self._mesh is None or self._plotter is None:
            return

        try:
            # 기존 actor 제거
            self._plotter.clear()

            # 메시 추가
            self._plotter.add_mesh(
                self._mesh,
                color="#00aa99",
                opacity=0.8,
                show_edges=True,
                edge_color="white",
                edge_width=0.5,
            )

            # 카메라 설정
            self._plotter.view_isometric()
            self._plotter.camera.reset_clipping_range()

            # Render
            self._plotter.render()

        except Exception as e:  # noqa: BLE001
            print(f"[오류] 메시 표시 실패: {e}")

    def clear(self) -> None:
        """뷰어 초기화."""
        if self._plotter is not None:
            self._plotter.clear()
        self._mesh = None

    def set_wireframe(self, enabled: bool) -> None:
        """와이어프레임 모드 토글.

        Args:
            enabled: 활성화 여부.
        """
        if self._mesh is None or self._plotter is None:
            return

        try:
            self._plotter.clear()
            if enabled:
                self._plotter.add_mesh(
                    self._mesh,
                    style="wireframe",
                    color="white",
                    line_width=1.0,
                )
            else:
                self._display_mesh()
            self._plotter.render()
        except Exception as e:  # noqa: BLE001
            print(f"[오류] 와이어프레임 설정 실패: {e}")

    def reset_view(self) -> None:
        """뷰 리셋."""
        if self._plotter is not None:
            self._plotter.view_isometric()
            self._plotter.camera.reset_clipping_range()
            self._plotter.render()

    def export_screenshot(self, path: str | Path) -> bool:
        """스크린샷 저장.

        Args:
            path: 저장 경로.

        Returns:
            성공 여부.
        """
        try:
            if self._plotter is None:
                return False

            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)

            self._plotter.screenshot(str(path))
            return True

        except Exception as e:  # noqa: BLE001
            print(f"[오류] 스크린샷 저장 실패: {e}")
            return False
