"""PyVista 3D 메시 뷰어 — Qt 통합."""
from __future__ import annotations

from pathlib import Path

try:
    import pyvista as pv
    PYVISTA_AVAILABLE = True
except ImportError:
    PYVISTA_AVAILABLE = False

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class MeshViewerWidget(QWidget):
    """PyVista 기반 3D 메시 뷰어 (간단한 버전).

    OpenFOAM polyMesh를 PyVista로 시각화한다.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """초기화.

        Args:
            parent: 부모 위젯.
        """
        super().__init__(parent)
        self._plotter: object | None = None
        self._mesh: object | None = None
        self._label: QLabel | None = None
        self._mesh_loaded = False
        self._init_ui()

    def _init_ui(self) -> None:
        """UI 초기화."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # 플레이스홀더 라벨
        self._label = QLabel("📊 PyVista 3D 메시 뷰어\n\n메시를 로드하면 여기에 표시됩니다.\n")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet(
            "QLabel { background-color: #2a2a2a; color: #ffffff; "
            "border-radius: 8px; padding: 20px; font-size: 14px; }"
        )
        layout.addWidget(self._label)

        self.setLayout(layout)

        # PyVista Plotter 지연 생성 (필요할 때만)
        if PYVISTA_AVAILABLE:
            try:
                self._init_plotter()
            except Exception as e:  # noqa: BLE001
                print(f"[경고] PyVista Plotter 초기화 실패: {e}")

    def _init_plotter(self) -> None:
        """PyVista Plotter 초기화 (메시 로드 시 호출)."""
        if not PYVISTA_AVAILABLE or self._plotter is not None:
            return

        try:
            # 간단한 Plotter 생성
            self._plotter = pv.Plotter(off_screen=True, theme=pv.themes.DarkTheme())
            if self._plotter is not None:
                self._plotter.background_color = "#1e1e1e"
        except Exception as e:  # noqa: BLE001
            print(f"[경고] PyVista Plotter 생성 실패: {e}")
            self._plotter = None

    def load_mesh(self, mesh_path: str | Path) -> bool:
        """메시 파일 로드 및 표시.

        Args:
            mesh_path: 메시 파일 경로 (STL, VTK, etc.)

        Returns:
            성공 여부.
        """
        if not PYVISTA_AVAILABLE:
            self._label.setText("❌ PyVista가 설치되지 않았습니다.")
            return False

        try:
            mesh_path = Path(mesh_path)
            if not mesh_path.exists():
                self._label.setText(f"❌ 파일을 찾을 수 없습니다:\n{mesh_path}")
                return False

            # 메시 로드
            mesh = pv.read(str(mesh_path))
            if mesh is None:
                self._label.setText(f"❌ 메시 로드 실패:\n{mesh_path}")
                return False

            self._mesh = mesh
            self._mesh_loaded = True

            # 정보 표시
            n_cells = mesh.n_cells
            n_points = mesh.n_points
            bounds = mesh.bounds

            info_text = (
                f"✅ 메시 로드 성공\n\n"
                f"📄 파일: {mesh_path.name}\n"
                f"📊 셀 수: {n_cells:,}\n"
                f"📍 점 수: {n_points:,}\n"
                f"📏 Bounds: "
                f"X:[{bounds[0]:.2f}, {bounds[1]:.2f}] "
                f"Y:[{bounds[2]:.2f}, {bounds[3]:.2f}] "
                f"Z:[{bounds[4]:.2f}, {bounds[5]:.2f}]"
            )
            self._label.setText(info_text)
            self._label.setStyleSheet(
                "QLabel { background-color: #1a3a1a; color: #00ff00; "
                "border-radius: 8px; padding: 15px; font-family: monospace; "
                "font-size: 12px; }"
            )

            # PyVista 렌더링 시도 (오프스크린)
            try:
                if self._plotter is None:
                    self._init_plotter()

                if self._plotter is not None:
                    self._plotter.clear()
                    self._plotter.add_mesh(
                        mesh,
                        color="#00aa99",
                        opacity=0.8,
                        show_edges=True,
                        edge_color="white",
                        line_width=1.0,
                    )
                    self._plotter.view_isometric()
            except Exception as e:  # noqa: BLE001
                print(f"[경고] PyVista 렌더링 실패: {e}")

            return True

        except Exception as e:  # noqa: BLE001
            self._label.setText(f"❌ 메시 로드 오류:\n{e}")
            print(f"[오류] 메시 로드 실패: {e}")
            return False

    def load_polymesh(self, case_dir: str | Path) -> bool:
        """OpenFOAM polyMesh 로드.

        Args:
            case_dir: OpenFOAM case 디렉터리.

        Returns:
            성공 여부.
        """
        if not PYVISTA_AVAILABLE:
            self._label.setText("❌ PyVista가 설치되지 않았습니다.")
            return False

        try:
            case_dir = Path(case_dir)
            polymesh_dir = case_dir / "constant" / "polyMesh"

            if not polymesh_dir.exists():
                # STL 파일 검색
                stl_files = list(case_dir.glob("**/*.stl"))
                if stl_files:
                    return self.load_mesh(stl_files[0])

                self._label.setText("❌ polyMesh 또는 STL 파일을 찾을 수 없습니다.")
                return False

            # polyMesh 정보 표시
            points_file = polymesh_dir / "points"
            faces_file = polymesh_dir / "faces"

            if points_file.exists() and faces_file.exists():
                info_text = (
                    f"✅ OpenFOAM polyMesh 발견\n\n"
                    f"📁 경로: {polymesh_dir}\n"
                    f"📄 Points: {points_file.name}\n"
                    f"📄 Faces: {faces_file.name}\n\n"
                    f"💡 파일 탐색기에서 확인하세요."
                )
                self._label.setText(info_text)
                self._label.setStyleSheet(
                    "QLabel { background-color: #1a2a3a; color: #00aaff; "
                    "border-radius: 8px; padding: 15px; font-size: 12px; }"
                )
                return True

            return False

        except Exception as e:  # noqa: BLE001
            self._label.setText(f"❌ polyMesh 로드 오류:\n{e}")
            print(f"[오류] polyMesh 로드 실패: {e}")
            return False

    def clear(self) -> None:
        """뷰어 초기화."""
        self._mesh = None
        self._mesh_loaded = False
        self._label.setText("📊 PyVista 3D 메시 뷰어\n\n메시를 로드하면 여기에 표시됩니다.\n")
        self._label.setStyleSheet(
            "QLabel { background-color: #2a2a2a; color: #ffffff; "
            "border-radius: 8px; padding: 20px; font-size: 14px; }"
        )

    def set_wireframe(self, enabled: bool) -> None:
        """와이어프레임 모드 토글 (플레이스홀더).

        Args:
            enabled: 활성화 여부.
        """
        if not self._mesh_loaded:
            return
        # 실제 와이어프레임 토글은 나중에 구현 가능

    def reset_view(self) -> None:
        """뷰 리셋 (플레이스홀더)."""
        if not self._mesh_loaded:
            return
        # 실제 뷰 리셋은 나중에 구현 가능

    def export_screenshot(self, path: str | Path) -> bool:
        """스크린샷 저장 (플레이스홀더).

        Args:
            path: 저장 경로.

        Returns:
            성공 여부.
        """
        if not self._mesh_loaded or self._plotter is None:
            return False

        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._plotter.screenshot(str(path))
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[오류] 스크린샷 저장 실패: {e}")
            return False
