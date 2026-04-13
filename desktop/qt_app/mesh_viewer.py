"""PyVista 3D 메시 뷰어 — Qt 통합 (비동기 렌더링).

개선 사항:
- 메시 정보 표시 (정점, 면, 스케일, 파일명)
- 다양한 카메라 뷰 (isometric, front, top, side)
- 향상된 라이팅 (2개 라이트, 고명도)
- 렌더링 옵션 (edge 토글, 투명도)
- 상세한 진행 상태 메시지
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import gc
from typing import Optional
import logging

log = logging.getLogger(__name__)

try:
    import pyvista as pv
    import numpy as np
    import os

    # 오프스크린 렌더링 자동 초기화
    pv.OFF_SCREEN = True

    # WSL 또는 헤드리스 환경 감지
    has_display = os.environ.get("DISPLAY") is not None
    is_wsl = "wsl" in os.environ.get("PATH", "").lower() or os.path.exists("/proc/version") and "microsoft" in open("/proc/version").read().lower()

    # Xvfb 시도 (X11이 없으면 OSMesa로 자동 전환)
    if not is_wsl or has_display:
        try:
            try:
                pv.start_xvfb(suppress_messages=True)
            except TypeError:
                pv.start_xvfb()
        except Exception as e:
            log.debug(f"Xvfb 초기화 실패 (OSMesa 사용): {e}")
            # OSMesa로 자동 전환 (PyVista 0.43+)
            try:
                os.environ["PYOPENGL_PLATFORM"] = "osmesa"
            except Exception:
                pass
    else:
        # WSL 환경: OSMesa 강제 사용
        log.info("WSL 환경 감지 - OSMesa 사용")
        try:
            os.environ["PYOPENGL_PLATFORM"] = "osmesa"
        except Exception:
            pass

    PYVISTA_AVAILABLE = True
except ImportError:
    PYVISTA_AVAILABLE = False
except Exception as e:
    log.warning(f"PyVista 초기화 부분 실패: {e}")
    PYVISTA_AVAILABLE = False

from PySide6.QtCore import Qt, QObject, Signal, QThread
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class RenderWorker(QObject):
    """PyVista 렌더링 워커 (스레드 안전).

    개선된 라이팅, 카메라 컨트롤, 메시 정보 출력.
    """

    render_finished = Signal(str, dict)  # (이미지 경로, 메시 정보)
    render_error = Signal(str)           # 오류 메시지

    def render_mesh(
        self,
        mesh_path: str | Path,
        window_size: tuple[int, int] = (400, 300),
        camera_view: str = "isometric",
        show_edges: bool = False,
        opacity: float = 0.95,
    ) -> None:
        """메시를 렌더링하여 PNG로 저장.

        Args:
            mesh_path: 메시 파일 경로
            window_size: 렌더링 윈도우 크기 (width, height)
            camera_view: 카메라 뷰 ('isometric', 'front', 'top', 'side', 'auto')
            show_edges: 엣지 표시 여부
            opacity: 메시 투명도 (0.0~1.0)
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

            # 메시 정보 수집
            num_vertices = mesh.n_points if hasattr(mesh, 'n_points') else 0
            num_cells = mesh.n_cells if hasattr(mesh, 'n_cells') else 0

            # 대용량 메시 간단화 (decimation)
            decimated = False
            if num_cells > 100_000:
                try:
                    # 면 수를 50% 감소
                    mesh = mesh.decimate(target_reduction=0.5)
                    decimated = True
                    print(f"[메시 간단화] {num_cells} → {mesh.n_cells} cells")
                except Exception as e:
                    print(f"[간단화 실패] {e}")

            # 스케일 정보
            bounds = mesh.bounds
            scale = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4])

            # 오프스크린 렌더링 (향상된 테마)
            plotter = pv.Plotter(
                off_screen=True,
                window_size=window_size,
                theme=pv.themes.DarkTheme()
            )
            plotter.background_color = "#0d1117"  # GitHub dark

            # 향상된 라이팅: 2개의 light 추가
            plotter.add_light(pv.Light(position=(1, 1, 1), intensity=0.8, color="white"))
            plotter.add_light(pv.Light(position=(-1, -1, 0.5), intensity=0.4, color="lightblue"))

            # 메시 추가 (향상된 색상)
            plotter.add_mesh(
                mesh,
                color="#00d9ff",      # 시안 (하이컨트라스트)
                opacity=opacity,
                show_edges=show_edges,
                edge_color="#ffffff" if show_edges else None,
                smooth_shading=True,  # 부드러운 음영
            )

            # 카메라 뷰 설정
            if camera_view == "front":
                plotter.view_xy()
            elif camera_view == "top":
                plotter.view_xy(negative=True)
            elif camera_view == "side":
                plotter.view_xz()
            elif camera_view == "auto":
                plotter.reset_camera()
                plotter.camera.zoom(1.0)
            else:  # isometric (기본값)
                plotter.view_isometric()

            # 축(axes) 추가
            plotter.add_axes(
                xlabel="X", ylabel="Y", zlabel="Z",
                line_width=2,
                color="white"
            )

            # 이미지로 렌더링
            try:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    log.info(f"[PyVista 렌더링 시작] {tmp.name}")
                    screenshot = plotter.screenshot(tmp.name, transparent_background=False)
                    log.info(f"[PyVista 렌더링 완료] size={screenshot.shape if screenshot is not None else None}")

                    # 메모리 정리
                    try:
                        plotter.close()
                    except Exception as e:
                        log.warning(f"[Plotter 종료 오류] {e}")

                    del mesh
                    del plotter
                    gc.collect()

                    if screenshot is not None:
                        # 메시 정보 반환
                        mesh_info = {
                            "filename": mesh_path.name,
                            "vertices": num_vertices,
                            "cells": num_cells,
                            "scale": round(scale, 4),
                            "decimated": decimated,
                        }
                        log.info(f"[렌더링 성공] {mesh_path.name} → {tmp.name}")
                        self.render_finished.emit(tmp.name, mesh_info)
                    else:
                        log.error("[PyVista 렌더링] screenshot is None")
                        self.render_error.emit("렌더링 실패: screenshot is None")
            except Exception as render_exc:
                log.error(f"[렌더링 단계 오류] {render_exc}")
                self.render_error.emit(f"렌더링 오류: {str(render_exc)[:80]}")
                import traceback
                traceback.print_exc()

        except Exception as e:  # noqa: BLE001
            error_msg = f"[RenderWorker 최상위 오류] {str(e)[:100]}"
            log.error(error_msg)
            self.render_error.emit(error_msg)
            print(error_msg)
            import traceback
            traceback.print_exc()


class MeshViewerWidget(QWidget):
    """PyVista 기반 3D 메시 뷰어 (비동기 렌더링).

    개선된 기능:
    - 메시 정보 표시 (정점, 면, 스케일)
    - 다양한 카메라 뷰
    - 렌더링 옵션 (edge, opacity)
    - 상세한 상태 메시지
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """초기화."""
        super().__init__(parent)
        self._label: Optional[QLabel] = None
        self._info_label: Optional[QLabel] = None
        self._current_mesh: object | None = None
        self._render_thread: Optional[QThread] = None
        self._render_worker: Optional[RenderWorker] = None
        self._temp_files: list[Path] = []
        self._mesh_info: dict = {}
        self._camera_view: str = "isometric"
        self._show_edges: bool = False
        self._opacity: float = 0.95

        try:
            self._init_ui()
        except Exception as e:
            print(f"[경고] UI 초기화 실패: {e}")
            # UI 초기화 실패해도 렌더링은 계속 가능

    def _init_ui(self) -> None:
        """UI 초기화."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        # 3D 뷰어 라벨
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet(
            "QLabel { background-color: #0d1117; border-radius: 6px; padding: 5px; border: 1px solid #30363d; }"
        )
        self._label.setMinimumSize(300, 250)

        # 초기 메시지
        self._set_placeholder_image("📊 3D 메시 뷰어\n\n파일을 선택하면 기하학이 표시됩니다")

        layout.addWidget(self._label, stretch=1)

        # 메시 정보 라벨 (하단)
        self._info_label = QLabel()
        self._info_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._info_label.setStyleSheet(
            "QLabel { "
            "  background-color: #161b22; "
            "  border: 1px solid #30363d; "
            "  border-radius: 4px; "
            "  padding: 8px; "
            "  font-family: 'Courier New', monospace; "
            "  font-size: 10px; "
            "  color: #c9d1d9; "
            "}"
        )
        self._info_label.setMaximumHeight(80)
        self._info_label.setText("대기 중...")

        layout.addWidget(self._info_label)
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

    def load_mesh(
        self,
        mesh_path: str | Path,
        camera_view: str = "isometric",
        show_edges: bool = False,
        opacity: float = 0.95,
    ) -> bool:
        """메시 파일 로드 및 표시 (비동기).

        Args:
            mesh_path: 메시 파일 경로.
            camera_view: 카메라 뷰 ('isometric', 'front', 'top', 'side', 'auto').
            show_edges: 엣지 표시 여부.
            opacity: 메시 투명도 (0.0~1.0).

        Returns:
            성공 여부.
        """
        if not PYVISTA_AVAILABLE:
            self._set_placeholder_image("❌ PyVista 미설치")
            if self._info_label:
                self._info_label.setText("❌ PyVista 미설치 — pip install pyvista")
            return False

        # 기존 스레드 종료 대기
        if self._render_thread is not None:
            try:
                if isinstance(self._render_thread, QThread):
                    if self._render_thread.isRunning():
                        self._render_thread.quit()
                        self._render_thread.wait(timeout=2000)
            except Exception:
                pass

        # 새 렌더링 시작 전 기다림
        self._set_placeholder_image("⏳ 파일 분석 중...\n(대용량 메시는 시간이 걸릴 수 있습니다)")
        if self._info_label:
            self._info_label.setText("⏳ 메시 로딩 중...")

        try:
            # 설정 저장
            self._camera_view = camera_view
            self._show_edges = show_edges
            self._opacity = opacity

            # 플레이스홀더 표시
            self._set_placeholder_image("⏳ 파일 분석 중...\n(대용량 메시는 시간이 걸릴 수 있습니다)")
            if self._info_label:
                self._info_label.setText("⏳ 메시 로딩 중...")

            # 렌더링 워커 생성
            self._render_worker = RenderWorker()
            self._render_worker.render_finished.connect(self._on_render_finished)
            self._render_worker.render_error.connect(self._on_render_error)

            # QThread 사용 (더 안전함)
            self._render_thread = QThread()
            self._render_worker.moveToThread(self._render_thread)

            # 스레드 시작 시 렌더링 수행
            self._render_thread.started.connect(
                lambda: self._render_worker.render_mesh(
                    mesh_path,
                    camera_view=camera_view,
                    show_edges=show_edges,
                    opacity=opacity,
                )
            )

            # 렌더링 완료 시 스레드 종료
            self._render_worker.render_finished.connect(self._render_thread.quit)
            self._render_worker.render_error.connect(self._render_thread.quit)

            self._render_thread.start()
            return True

        except Exception as e:
            self._set_placeholder_image(f"❌ 오류:\n{str(e)[:40]}")
            if self._info_label:
                self._info_label.setText(f"❌ 오류: {str(e)[:100]}")
            print(f"[로드 오류] {e}")
            import traceback
            traceback.print_exc()
            return False

    def _on_render_finished(self, image_path: str, mesh_info: dict) -> None:
        """렌더링 완료 콜백."""
        try:
            image_path = Path(image_path)
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                self._label.setPixmap(pixmap)
                self._temp_files.append(image_path)
                self._mesh_info = mesh_info

                # 메시 정보 표시
                if self._info_label:
                    filename = mesh_info.get("filename", "unknown")
                    vertices = mesh_info.get("vertices", 0)
                    cells = mesh_info.get("cells", 0)
                    scale = mesh_info.get("scale", 0)
                    decimated = mesh_info.get("decimated", False)

                    info_text = (
                        f"📄 {filename} | "
                        f"📍 {vertices:,} vertices | "
                        f"▭ {cells:,} cells | "
                        f"📏 scale={scale}"
                    )
                    if decimated:
                        info_text += " [decimated]"

                    self._info_label.setText(info_text)

                # 이전 임시 파일 정리
                if len(self._temp_files) > 3:
                    old_file = self._temp_files.pop(0)
                    try:
                        old_file.unlink()
                    except Exception:
                        pass
            else:
                self._set_placeholder_image("❌ 렌더링 실패")
                if self._info_label:
                    self._info_label.setText("❌ 이미지 로드 실패")
        except Exception as e:
            self._set_placeholder_image(f"❌ 오류:\n{str(e)[:40]}")
            if self._info_label:
                self._info_label.setText(f"❌ 오류: {str(e)[:100]}")
            print(f"[렌더링 완료 오류] {e}")

    def _on_render_error(self, error_msg: str) -> None:
        """렌더링 오류 콜백."""
        self._set_placeholder_image(f"❌ 오류:\n{error_msg[:50]}")
        if self._info_label:
            self._info_label.setText(f"❌ 렌더링 오류: {error_msg[:100]}")
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
        self._mesh_info = {}
        self._set_placeholder_image("📊 3D 메시 뷰어\n\n파일을 선택하면 기하학이 표시됩니다")
        if self._info_label:
            self._info_label.setText("대기 중...")

    def set_camera_view(self, view: str) -> None:
        """카메라 뷰 변경.

        Args:
            view: 'isometric', 'front', 'top', 'side', 'auto'
        """
        if view in ("isometric", "front", "top", "side", "auto"):
            self._camera_view = view

    def set_show_edges(self, show: bool) -> None:
        """엣지 표시 여부 변경."""
        self._show_edges = show

    def set_opacity(self, opacity: float) -> None:
        """투명도 변경.

        Args:
            opacity: 0.0~1.0
        """
        self._opacity = max(0.0, min(1.0, opacity))
