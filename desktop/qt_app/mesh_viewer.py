"""PyVista 3D 메시 뷰어 — Qt 통합 (비동기 렌더링)."""
from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import gc

try:
    import pyvista as pv
    # 오프스크린 렌더링 자동 초기화
    pv.OFF_SCREEN = True
    # Xvfb 자동 시작 (무음)
    try:
        pv.start_xvfb(suppress_messages=True)
    except Exception:
        pass  # Xvfb 이미 실행 중이거나 사용 불가능
    PYVISTA_AVAILABLE = True
except ImportError:
    PYVISTA_AVAILABLE = False

from PySide6.QtCore import Qt, QObject, Signal, QThread
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class RenderWorker(QObject):
    """PyVista 렌더링 워커 (스레드 안전)."""

    render_finished = Signal(str)  # 이미지 경로
    render_error = Signal(str)     # 오류 메시지

    def render_mesh(self, mesh_path: str | Path, window_size: tuple[int, int] = (400, 300)) -> None:
        """메시를 렌더링하여 PNG로 저장.

        Args:
            mesh_path: 메시 파일 경로
            window_size: 렌더링 윈도우 크기
        """
        try:
            mesh_path = Path(mesh_path)
            if not mesh_path.exists():
                self.render_error.emit(f"파일 없음: {mesh_path.name}")
                return

            # 메시 로드
            mesh = pv.read(str(mesh_path))
            if mesh is None:
                self.render_error.emit(f"로드 실패: {mesh_path.name}")
                return

            # 대용량 메시 간단화 (decimation)
            num_cells = mesh.n_cells if hasattr(mesh, 'n_cells') else 0
            if num_cells > 100_000:
                try:
                    # 면 수를 50% 감소
                    mesh = mesh.decimate(target_reduction=0.5)
                    print(f"[메시 간단화] {num_cells} → {mesh.n_cells} cells")
                except Exception as e:
                    print(f"[간단화 실패] {e}")

            # 오프스크린 렌더링
            plotter = pv.Plotter(
                off_screen=True,
                window_size=window_size,
                theme=pv.themes.DarkTheme()
            )
            plotter.background_color = "#1e1e1e"

            # 메시 추가
            plotter.add_mesh(
                mesh,
                color="#00aa99",
                opacity=0.9,
                show_edges=False,  # 엣지 제거 (성능 개선)
            )
            plotter.view_isometric()

            # 이미지로 렌더링
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                screenshot = plotter.screenshot(tmp.name, transparent_background=False)
                plotter.close()

                # 메모리 정리
                del mesh
                del plotter
                gc.collect()

                if screenshot is not None:
                    self.render_finished.emit(tmp.name)
                else:
                    self.render_error.emit("렌더링 실패")

        except Exception as e:  # noqa: BLE001
            self.render_error.emit(str(e)[:60])
            print(f"[렌더링 워커 오류] {e}")
            import traceback
            traceback.print_exc()


class MeshViewerWidget(QWidget):
    """PyVista 기반 3D 메시 뷰어 (비동기 렌더링)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """초기화."""
        super().__init__(parent)
        self._label: QLabel | None = None
        self._current_mesh: object | None = None
        self._render_thread: threading.Thread | None = None
        self._render_worker: RenderWorker | None = None
        self._temp_files: list[Path] = []

        try:
            self._init_ui()
        except Exception as e:
            print(f"[경고] UI 초기화 실패: {e}")
            # UI 초기화 실패해도 렌더링은 계속 가능

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
        """메시 파일 로드 및 표시 (비동기).

        Args:
            mesh_path: 메시 파일 경로.

        Returns:
            성공 여부.
        """
        if not PYVISTA_AVAILABLE:
            self._set_placeholder_image("❌ PyVista 미설치")
            return False

        # 기존 스레드 대기
        if self._render_thread is not None and isinstance(self._render_thread, QThread):
            if self._render_thread.isRunning():
                self._set_placeholder_image("⏳ 렌더링 중...")
                return False
        elif self._render_thread is not None and hasattr(self._render_thread, 'is_alive'):
            if self._render_thread.is_alive():
                self._set_placeholder_image("⏳ 렌더링 중...")
                return False

        try:
            # 플레이스홀더 표시
            self._set_placeholder_image("⏳ 렌더링 중...\n(대용량 메시는 시간이 걸릴 수 있습니다)")

            # 렌더링 워커 생성
            self._render_worker = RenderWorker()
            self._render_worker.render_finished.connect(self._on_render_finished)
            self._render_worker.render_error.connect(self._on_render_error)

            # QThread 사용 (더 안전함)
            self._render_thread = QThread()
            self._render_worker.moveToThread(self._render_thread)

            # 스레드 시작 시 렌더링 수행
            self._render_thread.started.connect(
                lambda: self._render_worker.render_mesh(mesh_path)
            )

            # 렌더링 완료 시 스레드 종료
            self._render_worker.render_finished.connect(self._render_thread.quit)
            self._render_worker.render_error.connect(self._render_thread.quit)

            self._render_thread.start()
            return True

        except Exception as e:
            self._set_placeholder_image(f"❌ 오류:\n{str(e)[:30]}")
            print(f"[로드 오류] {e}")
            import traceback
            traceback.print_exc()
            return False

    def _on_render_finished(self, image_path: str) -> None:
        """렌더링 완료 콜백."""
        try:
            image_path = Path(image_path)
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                self._label.setPixmap(pixmap)
                self._temp_files.append(image_path)
                # 이전 임시 파일 정리
                if len(self._temp_files) > 3:
                    old_file = self._temp_files.pop(0)
                    try:
                        old_file.unlink()
                    except Exception:
                        pass
            else:
                self._set_placeholder_image("❌ 렌더링 실패")
        except Exception as e:
            self._set_placeholder_image(f"❌ 오류:\n{str(e)[:30]}")
            print(f"[렌더링 완료 오류] {e}")

    def _on_render_error(self, error_msg: str) -> None:
        """렌더링 오류 콜백."""
        self._set_placeholder_image(f"❌ 오류:\n{error_msg}")
        print(f"[렌더링 오류] {error_msg}")

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
