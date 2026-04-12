"""PyVista 3D 메시 뷰어 — Qt 통합 (이미지 기반)."""
from __future__ import annotations

from pathlib import Path
import tempfile

try:
    import pyvista as pv
    PYVISTA_AVAILABLE = True
except ImportError:
    PYVISTA_AVAILABLE = False

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class MeshViewerWidget(QWidget):
    """PyVista 기반 3D 메시 뷰어 (오프스크린 렌더링)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """초기화."""
        super().__init__(parent)
        self._label: QLabel | None = None
        self._current_mesh: object | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        """UI 초기화."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet(
            "QLabel { background-color: #1e1e1e; border-radius: 4px; padding: 5px; }"
        )
        self._label.setMinimumSize(200, 200)

        # 초기 메시지
        self._set_placeholder_image("3D 메시 뷰어\n\n파일을 선택하면 기하학이 표시됩니다")

        layout.addWidget(self._label)
        self.setLayout(layout)

    def _set_placeholder_image(self, text: str) -> None:
        """플레이스홀더 이미지 설정."""
        if self._label is None:
            return

        pixmap = QPixmap(400, 300)
        pixmap.fill(Qt.black)

        from PySide6.QtGui import QPainter, QFont
        painter = QPainter(pixmap)
        painter.setPen(Qt.white)
        font = QFont()
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
        painter.end()

        self._label.setPixmap(pixmap.scaledToWidth(400, Qt.SmoothTransformation))

    def load_mesh(self, mesh_path: str | Path) -> bool:
        """메시 파일 로드 및 표시.

        Args:
            mesh_path: 메시 파일 경로.

        Returns:
            성공 여부.
        """
        if not PYVISTA_AVAILABLE:
            self._set_placeholder_image("❌ PyVista 미설치")
            return False

        try:
            mesh_path = Path(mesh_path)
            if not mesh_path.exists():
                self._set_placeholder_image(f"❌ 파일 없음:\n{mesh_path.name}")
                return False

            # 메시 로드
            mesh = pv.read(str(mesh_path))
            if mesh is None:
                self._set_placeholder_image(f"❌ 로드 실패:\n{mesh_path.name}")
                return False

            self._current_mesh = mesh

            # 오프스크린 렌더링
            plotter = pv.Plotter(
                off_screen=True,
                window_size=(400, 300),
                theme=pv.themes.DarkTheme()
            )
            plotter.background_color = "#1e1e1e"

            # 메시 추가
            plotter.add_mesh(
                mesh,
                color="#00aa99",
                opacity=0.8,
                show_edges=True,
                edge_color="white",
                line_width=1.0,
            )
            plotter.view_isometric()

            # 이미지로 렌더링
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                plotter.screenshot(tmp.name)
                plotter.close()

                # QPixmap으로 로드
                pixmap = QPixmap(tmp.name)
                if not pixmap.isNull():
                    self._label.setPixmap(pixmap)
                    Path(tmp.name).unlink()  # 임시 파일 삭제
                    return True

            return False

        except Exception as e:  # noqa: BLE001
            self._set_placeholder_image(f"❌ 오류:\n{str(e)[:30]}")
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

            # 먼저 STL 파일 검색
            stl_files = list(case_dir.glob("**/*.stl"))
            if stl_files:
                # 가장 최신 STL 파일 사용
                latest_stl = max(stl_files, key=lambda p: p.stat().st_mtime)
                return self.load_mesh(latest_stl)

            # polyMesh 정보 표시
            polymesh_dir = case_dir / "constant" / "polyMesh"
            if polymesh_dir.exists():
                self._set_placeholder_image(
                    "✅ OpenFOAM\nmesh 생성됨\n\n(3D 미리보기 미지원)"
                )
                return True

            return False

        except Exception as e:  # noqa: BLE001
            self._set_placeholder_image(f"❌ 오류:\n{str(e)[:30]}")
            return False

    def clear(self) -> None:
        """뷰어 초기화."""
        self._current_mesh = None
        self._set_placeholder_image("3D 메시 뷰어\n\n파일을 선택하면 기하학이 표시됩니다")
