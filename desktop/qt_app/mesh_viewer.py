"""PyVista 3D 인터랙티브 메시 뷰어 — pyvistaqt QtInteractor 기반.

마우스 인터랙션:
- 왼쪽 클릭 드래그: 회전
- 오른쪽 클릭 드래그 / 스크롤: 줌
- 가운데 클릭 드래그: 팬
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
import logging
import gc

log = logging.getLogger(__name__)

try:
    import pyvista as pv
    import numpy as np
    import os

    pv.OFF_SCREEN = False  # 인터랙티브 모드에서는 오프스크린 끔
    PYVISTA_AVAILABLE = True
except ImportError:
    PYVISTA_AVAILABLE = False
    log.warning("pyvista 미설치 — 3D 뷰어 비활성화")
except Exception as e:
    PYVISTA_AVAILABLE = False
    log.warning(f"pyvista 초기화 실패: {e}")


# ---------------------------------------------------------------------------
# 멀티포맷 로더 — pv.read()가 지원하지 않는 포맷 전처리
# ---------------------------------------------------------------------------
_CAD_EXTS   = {".step", ".stp", ".iges", ".igs", ".brep"}
_PC_EXTS    = {".las", ".laz"}
_TM_EXTS    = {".off", ".3mf"}          # trimesh 경유
_MESHIO_EXTS = {".msh"}                  # meshio → VTU


def _pv_read_any(path: Path) -> "pv.DataSet":
    """포맷을 자동 감지해 PyVista 메시를 반환.

    지원 포맷:
    - pv.read() 직접: STL, OBJ, PLY, VTK, VTU, VTP 등
    - CAD (STEP/IGES/BREP): cadquery → STL temp
    - 포인트클라우드 (LAS/LAZ): laspy → pv.PolyData
    - OFF / 3MF: trimesh → STL temp
    - MSH (Gmsh): meshio → VTU temp
    """
    ext = path.suffix.lower()

    if ext in _CAD_EXTS:
        return _read_cad(path)
    if ext in _PC_EXTS:
        return _read_las(path)
    if ext in _TM_EXTS:
        return _read_trimesh(path)
    if ext in _MESHIO_EXTS:
        return _read_meshio(path)
    # 기본: pv.read() 시도 (OBJ, PLY, VTK, VTU, STL 등)
    return pv.read(str(path))


def _read_cad(path: Path) -> "pv.DataSet":
    """STEP / IGES / BREP → tessellate → PyVista.

    STEP/BREP: cadquery 우선 → gmsh fallback
    IGES: gmsh 우선 → cadquery fallback
    """
    import tempfile

    suffix = path.suffix.lower()

    def _try_cadquery() -> "pv.DataSet | None":
        try:
            import cadquery as cq
            if suffix in (".step", ".stp"):
                shape = cq.importers.importStep(str(path))
            elif suffix in (".iges", ".igs"):
                # cadquery는 실제로 IGES를 제대로 지원하지 않으므로 importStep 시도
                shape = cq.importers.importStep(str(path))
            elif suffix == ".brep":
                from cadquery import Shape as _Shape
                shape = _Shape.importBrep(str(path))
            else:
                return None
            with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
                cq.exporters.export(shape, tmp.name)
                return pv.read(tmp.name)
        except Exception as e_cq:
            log.debug(f"cadquery 로드 실패: {e_cq}")
            return None

    def _try_gmsh() -> "pv.DataSet | None":
        try:
            import gmsh
            gmsh.initialize()
            gmsh.option.setNumber("General.Verbosity", 0)
            gmsh.model.occ.importShapes(str(path))
            gmsh.model.occ.synchronize()
            gmsh.model.mesh.generate(2)
            with tempfile.NamedTemporaryFile(suffix=".msh", delete=False) as tmp:
                tmp_msh = tmp.name
            gmsh.write(tmp_msh)
            gmsh.finalize()
            return _read_meshio(Path(tmp_msh))
        except Exception as e_gmsh:
            log.debug(f"gmsh 로드 실패: {e_gmsh}")
            return None

    # IGES는 gmsh 우선, 나머지(STEP/BREP)는 cadquery 우선
    if suffix in (".iges", ".igs"):
        result = _try_gmsh() or _try_cadquery()
    else:
        result = _try_cadquery() or _try_gmsh()

    if result is not None:
        return result

    raise ValueError(f"CAD 파일 로드 실패 (cadquery/gmsh 모두 실패): {path.name}")


def _read_las(path: Path) -> "pv.DataSet":
    """LAS / LAZ 포인트클라우드 → pv.PolyData."""
    import laspy
    las = laspy.read(str(path))
    pts = np.column_stack([
        np.asarray(las.x, dtype=float),
        np.asarray(las.y, dtype=float),
        np.asarray(las.z, dtype=float),
    ])
    cloud = pv.PolyData(pts)
    return cloud


def _read_trimesh(path: Path) -> "pv.DataSet":
    """OFF / 3MF → trimesh → STL temp → pv.read()."""
    import tempfile
    import trimesh
    mesh = trimesh.load(str(path), force="mesh")
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
        mesh.export(tmp.name)
        return pv.read(tmp.name)


def _read_meshio(path: Path) -> "pv.DataSet":
    """MSH (Gmsh) / 기타 meshio 지원 포맷 → VTU temp → pv.read()."""
    import meshio
    import tempfile
    mio = meshio.read(str(path))
    with tempfile.NamedTemporaryFile(suffix=".vtu", delete=False) as tmp:
        tmp_path = tmp.name
    meshio.write(tmp_path, mio)
    result = pv.read(tmp_path)
    try:
        Path(tmp_path).unlink()
    except Exception:
        pass
    return result


# VTK 볼륨 셀 타입 ID (tet=10, hex=12, wedge=13, pyramid=14, hex20=25 등)
_VOLUME_CELL_TYPES = {10, 12, 13, 14, 25, 26, 27, 28, 29, 42}


def _mesh_element_label(mesh: object) -> tuple[str, str]:
    """메시 종류에 따라 (face_label, cell_label) 반환.

    surface mesh (STL 등): faces=삼각형/사각형, cells=0
    volume mesh (polyMesh, VTU 등): faces=경계면, cells=tet/hex

    Returns:
        (face_str, cell_str) — 빈 문자열이면 표시 안 함
    """
    n_pts = getattr(mesh, "n_points", 0)
    n_cells = getattr(mesh, "n_cells", 0)
    try:
        cell_types = set(getattr(mesh, "celltypes", []))
        is_volume = bool(cell_types & _VOLUME_CELL_TYPES)
    except Exception:
        is_volume = False

    if is_volume:
        # 볼륨 메시: n_cells = 볼륨 셀 개수
        return ("", f"▭ {n_cells:,} cells")
    else:
        # 표면 메시: n_cells = 삼각형(face) 개수
        return (f"△ {n_cells:,} faces", "")

try:
    from pyvistaqt import QtInteractor
    PYVISTAQT_AVAILABLE = True
except ImportError:
    PYVISTAQT_AVAILABLE = False
    log.warning("pyvistaqt 미설치 — pip install pyvistaqt")
except Exception as e:
    PYVISTAQT_AVAILABLE = False
    log.warning(f"pyvistaqt 초기화 실패: {e}")

try:
    from PySide6.QtCore import Qt, QObject, Signal, QThread
    from PySide6.QtGui import QPixmap, QFont, QColor
    from PySide6.QtWidgets import (
        QCheckBox,
        QHBoxLayout,
        QLabel,
        QMenu,
        QPushButton,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
    PYSIDE6_AVAILABLE = True
except Exception:
    PYSIDE6_AVAILABLE = False
    log.warning("PySide6 미설치 또는 초기화 실패 — Qt 뷰어 비활성화")
    # Dummy base classes so class definitions don't fail at import time
    class QObject:  # type: ignore[no-redef]
        pass
    class QWidget(QObject):  # type: ignore[no-redef]
        pass
    class QThread(QObject):  # type: ignore[no-redef]
        pass
    def Signal(*args, **kwargs):  # type: ignore[no-redef]
        return None
    Qt = None  # type: ignore[assignment]
    QPixmap = None  # type: ignore[assignment]
    QFont = None  # type: ignore[assignment]
    QColor = None  # type: ignore[assignment]
    QCheckBox = None  # type: ignore[assignment]
    QHBoxLayout = None  # type: ignore[assignment]
    QLabel = None  # type: ignore[assignment]
    QPushButton = None  # type: ignore[assignment]
    QVBoxLayout = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Static fallback (PNG rendering via background thread)
# ---------------------------------------------------------------------------

class RenderWorker(QObject):
    """PyVista 오프스크린 렌더링 워커 (폴백용)."""

    render_finished = Signal(str, dict)
    render_error = Signal(str)

    def render_mesh(
        self,
        mesh_path: str | Path,
        window_size: tuple[int, int] = (800, 600),
        camera_view: str = "isometric",
        show_edges: bool = True,
        show_points: bool = False,
        opacity: float = 0.95,
    ) -> None:
        """메시를 렌더링하여 PNG로 저장 (폴백)."""
        import tempfile

        try:
            mesh_path = Path(mesh_path)
            if not mesh_path.exists():
                self.render_error.emit(f"파일 없음: {mesh_path.name}")
                return

            mesh = _pv_read_any(mesh_path)
            if mesh is None:
                self.render_error.emit(f"로드 실패: {mesh_path.name}")
                return

            num_vertices = getattr(mesh, "n_points", 0)
            num_cells = getattr(mesh, "n_cells", 0)
            # cell type 분류: surface면 faces, volume이면 cells
            try:
                _ctypes = set(getattr(mesh, "celltypes", []))
                _is_volume = bool(_ctypes & _VOLUME_CELL_TYPES)
            except Exception:
                _is_volume = False
            decimated = False

            if num_cells > 100_000:
                try:
                    mesh = mesh.decimate(target_reduction=0.5)
                    decimated = True
                except Exception:
                    pass

            bounds = mesh.bounds
            scale = max(
                bounds[1] - bounds[0],
                bounds[3] - bounds[2],
                bounds[5] - bounds[4],
            )

            plotter = pv.Plotter(
                off_screen=True,
                window_size=window_size,
                theme=pv.themes.DarkTheme(),
            )
            plotter.background_color = "#0d1117"
            plotter.add_light(pv.Light(position=(1, 1, 1), intensity=0.8, color="white"))
            plotter.add_light(pv.Light(position=(-1, -1, 0.5), intensity=0.4, color="lightblue"))

            plotter.add_mesh(
                mesh,
                color="#00d9ff",
                opacity=opacity,
                show_edges=show_edges,
                edge_color="#ffffff" if show_edges else None,
                smooth_shading=True,
            )

            if show_points:
                plotter.add_points(
                    mesh.points,
                    color="yellow",
                    point_size=6,
                    render_points_as_spheres=True,
                )

            if camera_view == "front":
                plotter.view_xy()
            elif camera_view == "top":
                plotter.view_xy(negative=True)
            elif camera_view == "side":
                plotter.view_xz()
            else:
                plotter.view_isometric()

            plotter.add_axes(xlabel="X", ylabel="Y", zlabel="Z", line_width=2, color="white")

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                screenshot = plotter.screenshot(tmp.name, transparent_background=False)
                try:
                    plotter.close()
                except Exception:
                    pass
                del mesh
                del plotter
                gc.collect()

                if screenshot is not None:
                    mesh_info = {
                        "filename": mesh_path.name,
                        "vertices": num_vertices,
                        "cells": num_cells,
                        "is_volume": _is_volume,
                        "scale": round(scale, 4),
                        "decimated": decimated,
                    }
                    self.render_finished.emit(tmp.name, mesh_info)
                else:
                    self.render_error.emit("렌더링 실패: screenshot is None")

        except Exception as e:
            self.render_error.emit(f"렌더링 오류: {str(e)[:80]}")
            import traceback
            traceback.print_exc()


class StaticMeshViewer(QWidget):
    """폴백용 정적 PNG 뷰어 (pyvistaqt 미설치 시)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet(
            "QLabel { background-color: #0d1117; border-radius: 6px; padding: 5px; }"
        )
        self._label.setMinimumSize(400, 300)
        self._info_label = QLabel("대기 중...")
        self._info_label.setStyleSheet(
            "QLabel { background-color: #161b22; border: 1px solid #30363d; "
            "border-radius: 4px; padding: 8px; font-size: 10px; color: #c9d1d9; }"
        )
        self._render_thread: Optional[QThread] = None
        self._render_worker: Optional[RenderWorker] = None
        self._temp_files: list[Path] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label, stretch=1)
        layout.addWidget(self._info_label)
        self._set_placeholder("📊 3D 뷰어\n\n파일을 선택하세요")

    def _set_placeholder(self, text: str) -> None:
        pixmap = QPixmap(400, 300)
        pixmap.fill(Qt.black)
        from PySide6.QtGui import QPainter
        painter = QPainter(pixmap)
        painter.setPen(Qt.white)
        f = QFont()
        f.setPointSize(12)
        painter.setFont(f)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
        painter.end()
        self._label.setPixmap(pixmap)

    def load_mesh(self, path: str | Path, **kwargs: object) -> bool:
        if not PYVISTA_AVAILABLE:
            self._set_placeholder("❌ PyVista 미설치")
            return False

        if self._render_thread is not None and isinstance(self._render_thread, QThread):
            if self._render_thread.isRunning():
                # 이전 워커 시그널 먼저 해제 — stale 콜백 방지
                if self._render_worker is not None:
                    try:
                        self._render_worker.render_finished.disconnect()
                        self._render_worker.render_error.disconnect()
                    except Exception:
                        pass
                self._render_thread.quit()
                self._render_thread.wait(2000)

        self._set_placeholder("⏳ 렌더링 중...")
        self._info_label.setText("⏳ 메시 로딩 중...")

        self._render_worker = RenderWorker()
        self._render_thread = QThread()
        self._render_worker.moveToThread(self._render_thread)
        self._render_worker.render_finished.connect(self._on_done)
        self._render_worker.render_error.connect(self._on_error)
        self._render_worker.render_finished.connect(self._render_thread.quit)
        self._render_worker.render_error.connect(self._render_thread.quit)

        show_edges = bool(kwargs.get("show_edges", True))
        show_points = bool(kwargs.get("show_points", False))
        camera_view = str(kwargs.get("camera_view", "isometric"))
        opacity = float(kwargs.get("opacity", 0.95))

        self._render_thread.started.connect(
            lambda: self._render_worker.render_mesh(
                path,
                show_edges=show_edges,
                show_points=show_points,
                camera_view=camera_view,
                opacity=opacity,
            )
        )
        self._render_thread.start()
        return True

    def _on_done(self, image_path: str, mesh_info: dict) -> None:
        from PySide6.QtGui import QPixmap as QP
        p = Path(image_path)
        px = QP(str(p))
        if not px.isNull():
            self._label.setPixmap(px.scaled(
                self._label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
            self._temp_files.append(p)
            v = mesh_info.get("vertices", 0)
            c = mesh_info.get("cells", 0)
            s = mesh_info.get("scale", 0)
            fn = mesh_info.get("filename", "")
            d = " [decimated]" if mesh_info.get("decimated") else ""
            is_vol = mesh_info.get("is_volume", False)
            elem_str = f"▭ {c:,} cells" if is_vol else f"△ {c:,} faces"
            self._info_label.setText(
                f"📄 {fn} | 📍 {v:,} pts | {elem_str} | 📏 scale={s}{d}"
            )
            if len(self._temp_files) > 3:
                try:
                    self._temp_files.pop(0).unlink()
                except Exception:
                    pass

    def _on_error(self, msg: str) -> None:
        self._set_placeholder(f"❌ 오류:\n{msg[:50]}")
        self._info_label.setText(f"❌ {msg[:80]}")

    def load_polymesh(self, case_dir: str | Path) -> bool:
        case_dir = Path(case_dir)
        # VTU/VTK 우선
        for pattern in ("**/*.vtu", "**/*.vtk"):
            files = list(case_dir.glob(pattern))
            if files:
                return self.load_mesh(max(files, key=lambda p: p.stat().st_mtime))
        # MSH
        msh_files = list(case_dir.glob("**/*.msh"))
        if msh_files:
            try:
                import meshio, tempfile
                mio = meshio.read(str(max(msh_files, key=lambda p: p.stat().st_mtime)))
                with tempfile.NamedTemporaryFile(suffix=".vtu", delete=False) as tmp:
                    tmp_path = tmp.name
                meshio.write(tmp_path, mio)
                result = self.load_mesh(tmp_path)
                try:
                    Path(tmp_path).unlink()
                except Exception:
                    pass
                return result
            except Exception as e:
                log.warning(f"MSH 폴백 로드 실패: {e}")
        # polyMesh
        if (case_dir / "constant" / "polyMesh").exists():
            self._set_placeholder("✅ OpenFOAM polyMesh 생성됨\n(정적 뷰어 미지원)")
            return True
        # STL (preprocessed 제외)
        stl_files = [p for p in case_dir.glob("**/*.stl") if "preprocessed" not in p.name.lower()]
        if stl_files:
            return self.load_mesh(max(stl_files, key=lambda p: p.stat().st_mtime))
        return False

    def clear(self) -> None:
        self._set_placeholder("📊 3D 뷰어\n\n파일을 선택하세요")
        self._info_label.setText("대기 중...")


# ---------------------------------------------------------------------------
# Interactive viewer (pyvistaqt QtInteractor)
# ---------------------------------------------------------------------------

class InteractiveMeshViewer(QWidget):
    """pyvistaqt 기반 인터랙티브 3D 뷰어.

    마우스 조작:
    - 왼쪽 드래그: 회전
    - 오른쪽 드래그 / 스크롤 휠: 줌
    - 가운데 드래그: 팬
    """

    if PYSIDE6_AVAILABLE:
        mesh_ready = Signal(object)  # 메시 로드 완료 후 PyVista mesh 객체 전달

    # ------------------------------------------------------------------
    # 내부 백그라운드 로더 스레드
    # ------------------------------------------------------------------

    if PYSIDE6_AVAILABLE:
        class _MeshLoaderThread(QThread):
            """메시 파일을 백그라운드 스레드에서 로드한다.

            CAD 파일(STEP/IGES)은 cadquery/gmsh 테셀레이션에 수 초가 걸리므로
            Qt 메인 스레드를 블로킹하지 않기 위해 QThread를 사용한다.
            """
            mesh_loaded = Signal(object, str, bool, bool, float)  # mesh, camera_view, show_edges, show_points, opacity
            load_error = Signal(str)

            def __init__(
                self,
                path: Path,
                camera_view: str,
                show_edges: bool,
                show_points: bool,
                opacity: float,
                parent=None,
            ) -> None:
                super().__init__(parent)
                self._path = path
                self._camera_view = camera_view
                self._show_edges = show_edges
                self._show_points = show_points
                self._opacity = opacity

            def run(self) -> None:
                try:
                    mesh = _pv_read_any(self._path)
                    self.mesh_loaded.emit(
                        mesh,
                        self._camera_view,
                        self._show_edges,
                        self._show_points,
                        self._opacity,
                    )
                except Exception as e:
                    self.load_error.emit(str(e))
    else:
        # PySide6 없을 때 dummy (import 오류 방지)
        class _MeshLoaderThread:  # type: ignore[no-redef]
            pass

    # 품질 측정 메트릭: PyVista compute_cell_quality() quality_measure 값
    _QUALITY_METRICS: dict[str, tuple[str, str]] = {
        "aspect_ratio":      ("Aspect", "Aspect Ratio — 1에 가까울수록 좋음"),
        "skew":              ("Skewness", "Skewness — 0에 가까울수록 좋음"),
        "max_angle":         ("Non-ortho", "Max Angle (Non-orthogonality proxy) — 낮을수록 좋음"),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plotter: Optional[QtInteractor] = None
        self._current_mesh: object | None = None
        self._mesh_actor: object | None = None
        self._points_actor: object | None = None
        self._quality_metric: str = "aspect_ratio"
        self._show_edges: bool = True
        self._show_points: bool = False
        self._opacity: float = 0.95
        self._mesh_info: dict = {}
        self._slice_active: bool = False
        self._clip_active: bool = False
        self._loader_thread: Optional[QThread] = None
        self._loader_path: Optional[Path] = None

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 툴바
        toolbar = self._build_toolbar()
        layout.addWidget(toolbar)

        # QtInteractor (VTK 렌더 윈도우)
        try:
            self._plotter = QtInteractor(self)
            self._plotter.setMinimumSize(400, 300)
            self._plotter.background_color = "#0d1117"
            layout.addWidget(self._plotter, stretch=1)
        except Exception as e:
            log.error(f"QtInteractor 초기화 실패: {e}")
            fallback = QLabel(f"❌ QtInteractor 초기화 실패:\n{e}")
            fallback.setAlignment(Qt.AlignCenter)
            fallback.setStyleSheet("background: #0d1117; color: white;")
            layout.addWidget(fallback, stretch=1)

        # 정보 패널 (크게)
        self._info_label = QLabel("대기 중...")
        self._info_label.setStyleSheet(
            "QLabel { background-color: #161b22; border: 1px solid #30363d; "
            "border-radius: 4px; padding: 10px 14px; font-size: 14px; "
            "font-weight: 600; color: #e6edf3; "
            "font-family: 'Courier New', monospace; }"
        )
        self._info_label.setMinimumHeight(48)
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(
            "QWidget { background-color: #161b22; border-bottom: 1px solid #30363d; }"
        )
        h = QHBoxLayout(bar)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(6)

        def _btn(label: str, tip: str, fn) -> QPushButton:
            b = QPushButton(label)
            b.setToolTip(tip)
            b.setFixedHeight(26)
            b.setStyleSheet(
                "QPushButton { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; "
                "border-radius: 4px; padding: 0 8px; font-size: 11px; } "
                "QPushButton:hover { background: #30363d; } "
                "QPushButton:pressed { background: #388bfd; }"
            )
            b.clicked.connect(fn)
            return b

        # 카메라 뷰
        h.addWidget(QLabel("뷰:"))
        h.addWidget(_btn("ISO", "등각 뷰", self._view_iso))
        h.addWidget(_btn("앞", "정면 뷰 (XY)", self._view_front))
        h.addWidget(_btn("위", "상면 뷰 (XZ)", self._view_top))
        h.addWidget(_btn("측", "측면 뷰 (YZ)", self._view_side))
        h.addWidget(_btn("리셋", "카메라 리셋", self._reset_camera))

        h.addWidget(_separator())

        # 엣지 토글
        self._edge_btn = QPushButton("엣지 ON")
        self._edge_btn.setCheckable(True)
        self._edge_btn.setChecked(self._show_edges)
        self._edge_btn.setFixedHeight(26)
        self._edge_btn.setToolTip("셀 엣지 표시 토글")
        self._edge_btn.setStyleSheet(
            "QPushButton { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; "
            "border-radius: 4px; padding: 0 8px; font-size: 11px; } "
            "QPushButton:checked { background: #1f6feb; border-color: #388bfd; } "
            "QPushButton:hover { background: #30363d; }"
        )
        self._edge_btn.toggled.connect(self._toggle_edges)
        h.addWidget(self._edge_btn)

        # 버텍스 토글
        self._pts_btn = QPushButton("버텍스")
        self._pts_btn.setCheckable(True)
        self._pts_btn.setChecked(self._show_points)
        self._pts_btn.setFixedHeight(26)
        self._pts_btn.setToolTip("정점(vertex) 표시 토글")
        self._pts_btn.setStyleSheet(
            "QPushButton { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; "
            "border-radius: 4px; padding: 0 8px; font-size: 11px; } "
            "QPushButton:checked { background: #1f6feb; border-color: #388bfd; } "
            "QPushButton:hover { background: #30363d; }"
        )
        self._pts_btn.toggled.connect(self._toggle_points)
        h.addWidget(self._pts_btn)

        h.addWidget(_separator())

        # 슬라이스 (단면 보기)
        self._slice_btn = QPushButton("Slice")
        self._slice_btn.setCheckable(True)
        self._slice_btn.setFixedHeight(26)
        self._slice_btn.setToolTip("단면(Slice) 위젯 토글 — 드래그로 단면 위치 조절")
        self._slice_btn.setStyleSheet(
            "QPushButton { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; "
            "border-radius: 4px; padding: 0 8px; font-size: 11px; } "
            "QPushButton:checked { background: #388bfd; border-color: #58a6ff; color: white; } "
            "QPushButton:hover { background: #30363d; }"
        )
        self._slice_btn.toggled.connect(self._toggle_slice)
        h.addWidget(self._slice_btn)

        # 클립 (반쪽 잘라내기)
        self._clip_btn = QPushButton("Clip")
        self._clip_btn.setCheckable(True)
        self._clip_btn.setFixedHeight(26)
        self._clip_btn.setToolTip("클리핑 평면(Clip) 위젯 토글 — 메시를 잘라 내부 구조 확인")
        self._clip_btn.setStyleSheet(
            "QPushButton { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; "
            "border-radius: 4px; padding: 0 8px; font-size: 11px; } "
            "QPushButton:checked { background: #388bfd; border-color: #58a6ff; color: white; } "
            "QPushButton:hover { background: #30363d; }"
        )
        self._clip_btn.toggled.connect(self._toggle_clip)
        h.addWidget(self._clip_btn)

        h.addWidget(_separator())

        self._quality_btn = QToolButton()
        self._quality_btn.setText("품질: Aspect ▾")
        self._quality_btn.setCheckable(True)
        self._quality_btn.setFixedHeight(26)
        self._quality_btn.setToolTip("셀 품질 측정치 선택 후 클릭으로 색상화 — 빨강=나쁨, 초록=좋음")
        self._quality_btn.setEnabled(False)
        self._quality_btn.setStyleSheet(
            "QToolButton { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; "
            "border-radius: 4px; padding: 0 8px; font-size: 11px; } "
            "QToolButton:checked { background: #ff7b54; border-color: #ff9f7b; color: white; } "
            "QToolButton:hover { background: #30363d; } "
            "QToolButton:disabled { color: #5a6270; } "
            "QToolButton::menu-indicator { width: 0px; }"
        )
        # 드롭다운 메뉴 (메트릭 선택)
        _qmenu = QMenu(self._quality_btn)
        for _metric_key, (_label, _tip) in self._QUALITY_METRICS.items():
            _act = _qmenu.addAction(_label)
            _act.setToolTip(_tip)
            _act.setData(_metric_key)
        _qmenu.triggered.connect(self._on_quality_metric_selected)
        self._quality_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self._quality_btn.customContextMenuRequested.connect(
            lambda pos: _qmenu.exec(self._quality_btn.mapToGlobal(pos))
        )
        self._quality_btn.setPopupMode(QToolButton.MenuButtonPopup)  # type: ignore[attr-defined]
        self._quality_btn.setMenu(_qmenu)
        self._quality_btn.toggled.connect(self._toggle_quality_color)
        h.addWidget(self._quality_btn)

        h.addStretch()

        # 와이어프레임 토글
        self._wire_btn = QPushButton("와이어프레임")
        self._wire_btn.setCheckable(True)
        self._wire_btn.setFixedHeight(26)
        self._wire_btn.setToolTip("와이어프레임 모드 토글")
        self._wire_btn.setStyleSheet(
            "QPushButton { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; "
            "border-radius: 4px; padding: 0 8px; font-size: 11px; } "
            "QPushButton:checked { background: #1f6feb; border-color: #388bfd; } "
            "QPushButton:hover { background: #30363d; }"
        )
        self._wire_btn.toggled.connect(self._toggle_wireframe)
        h.addWidget(self._wire_btn)

        return bar

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def load_mesh(
        self,
        path: str | Path,
        camera_view: str = "isometric",
        show_edges: bool = True,
        show_points: bool = False,
        opacity: float = 0.95,
        **kwargs: object,
    ) -> bool:
        """메시 파일 로드 및 표시 (백그라운드 스레드 사용).

        CAD 파일(STEP/IGES)은 테셀레이션에 수 초가 걸리므로
        QThread로 비동기 로드하여 UI 프리즈를 방지한다.

        Args:
            path: 메시 파일 경로 (STL, OBJ, VTU, VTK, STEP, IGES 등)
            camera_view: 초기 카메라 뷰
            show_edges: 엣지 표시 여부
            show_points: 버텍스 표시 여부
            opacity: 투명도
        """
        if not PYVISTA_AVAILABLE or self._plotter is None:
            return False

        path = Path(path)
        if not path.exists():
            self._info_label.setText(f"❌ 파일 없음: {path.name}")
            return False

        # 이전 로더 스레드 정리
        if self._loader_thread is not None and isinstance(self._loader_thread, QThread):
            if self._loader_thread.isRunning():
                self._loader_thread.quit()
                self._loader_thread.wait(3000)
            self._loader_thread = None

        self._loader_path = path
        self._info_label.setText(f"⏳ {path.name} 로딩 중...")

        loader = self._MeshLoaderThread(
            path=path,
            camera_view=camera_view,
            show_edges=show_edges,
            show_points=show_points,
            opacity=opacity,
        )
        self._loader_thread = loader
        loader.mesh_loaded.connect(self._on_mesh_loaded)
        loader.load_error.connect(self._on_load_error)
        loader.start()
        return True

    def _on_mesh_loaded(
        self,
        mesh: object,
        camera_view: str,
        show_edges: bool,
        show_points: bool,
        opacity: float,
    ) -> None:
        """백그라운드 로더가 메시를 성공적으로 읽었을 때 호출 (메인 스레드)."""
        self._show_edges = show_edges
        self._show_points = show_points
        self._opacity = opacity
        self._current_mesh = mesh
        if hasattr(self, "_quality_btn"):
            self._quality_btn.setEnabled(True)

        # 버튼 상태 동기화
        self._edge_btn.setChecked(show_edges)
        self._pts_btn.setChecked(show_points)

        self._render_mesh(mesh, camera_view=camera_view)
        if self._loader_path is not None:
            self._update_info(self._loader_path, mesh)
        if hasattr(self, "mesh_ready"):
            self.mesh_ready.emit(mesh)

    def _on_load_error(self, error_msg: str) -> None:
        """백그라운드 로더에서 오류 발생 시 호출 (메인 스레드)."""
        self._info_label.setText(f"❌ 로드 실패: {error_msg[:80]}")
        log.error(f"mesh load error: {error_msg}")

    def load_polymesh(self, case_dir: str | Path) -> bool:
        """OpenFOAM case 디렉터리에서 메시 로드."""
        case_dir = Path(case_dir)

        # 1. OpenFOAM polyMesh 직접 읽기
        # pv.OpenFOAMReader는 케이스 디렉터리 안의 빈 .foam 파일을 입력으로 받음
        if (case_dir / "constant" / "polyMesh").exists():
            try:
                mesh = self._read_openfoam(case_dir)
                if mesh is not None:
                    self._current_mesh = mesh
                    self._render_mesh(mesh, camera_view="isometric")
                    pts = getattr(mesh, "n_points", 0)
                    face_str, cell_str = _mesh_element_label(mesh)
                    parts = ["✅ OpenFOAM polyMesh", f"📍 {pts:,} pts"]
                    if face_str:
                        parts.append(face_str)
                    if cell_str:
                        parts.append(cell_str)
                    self._info_label.setText(" | ".join(parts))
                    return True
            except Exception as e:
                log.warning(f"OpenFOAM 읽기 실패: {e}")

            # 읽기 실패해도 polyMesh 존재 확인됐으므로 텍스트로 표시
            if self._plotter:
                try:
                    self._plotter.clear()
                    self._plotter.background_color = "#0d1117"
                    self._plotter.add_text(
                        "✅ polyMesh 생성됨\n(3D 렌더링 불가)", font_size=14, color="white"
                    )
                except Exception:
                    pass
            self._info_label.setText("✅ OpenFOAM polyMesh 생성됨 (3D 렌더링 불가)")
            return True

        # 2. VTK/VTU 파일
        for pattern in ("**/*.vtu", "**/*.vtk"):
            vtk_files = list(case_dir.glob(pattern))
            if vtk_files:
                latest = max(vtk_files, key=lambda p: p.stat().st_mtime)
                return self.load_mesh(latest, show_edges=True)

        # 3. MSH (Gmsh) — meshio 경유 변환
        msh_files = list(case_dir.glob("**/*.msh"))
        if msh_files:
            latest = max(msh_files, key=lambda p: p.stat().st_mtime)
            return self._load_msh(latest)

        # 4. STL 폴백
        stl_files = [
            p for p in case_dir.glob("**/*.stl")
            if "preprocessed" not in p.name.lower()
        ]
        if stl_files:
            latest = max(stl_files, key=lambda p: p.stat().st_mtime)
            return self.load_mesh(latest, show_edges=True)

        return False

    def _read_openfoam(self, case_dir: Path) -> object | None:
        """OpenFOAM 케이스를 읽어 PyVista 메시 반환.

        pv.OpenFOAMReader는 케이스 디렉터리 내 빈 .foam 파일을 필요로 한다.
        실패 시 meshio 경유 변환을 시도한다.
        """
        # .foam 파일 생성 (없으면)
        foam_file = case_dir / f"{case_dir.name}.foam"
        if not foam_file.exists():
            try:
                foam_file.touch()
            except Exception:
                try:
                    foam_file = case_dir / "case.foam"
                    foam_file.touch()
                except Exception:
                    pass  # 쓰기 권한 없음 — OpenFOAMReader 시도만 진행

        try:
            reader = pv.OpenFOAMReader(str(foam_file))
            mesh = reader.read()

            # Block 0 = 내부 볼륨 셀(tet/hex), Block 1 = 경계 패치(PolyData)
            # combine()은 tet(타입10) + triangle(타입5)을 혼합해
            # 경계면을 이중 렌더링하고 z-fighting/음영 왜곡을 일으키므로 사용 안 함.
            if hasattr(mesh, "n_blocks") and mesh.n_blocks > 0:
                # Block 0: 볼륨 셀 → extract_surface()로 외곽 면 추출
                block0 = mesh.GetBlock(0)
                if block0 is not None and getattr(block0, "n_cells", 0) > 0:
                    try:
                        surface = block0.extract_surface()
                        if surface is not None and getattr(surface, "n_cells", 0) > 0:
                            return surface
                    except Exception:
                        return block0
                # Block 1: 경계 패치 MultiBlock → 첫 번째 PolyData 서브블록 반환
                if mesh.n_blocks > 1:
                    block1 = mesh.GetBlock(1)
                    if block1 is not None:
                        if hasattr(block1, "n_blocks"):
                            for j in range(block1.n_blocks):
                                sub = block1.GetBlock(j)
                                if sub is not None and getattr(sub, "n_cells", 0) > 0:
                                    return sub
                        elif getattr(block1, "n_cells", 0) > 0:
                            return block1
            if getattr(mesh, "n_cells", 0) > 0:
                return mesh
        except Exception as e:
            log.warning(f"pv.OpenFOAMReader 실패: {e}")

        # meshio 경유 폴백: boundary STL 또는 내부 mesh 추출
        try:
            import meshio
            import tempfile
            # polyMesh/points, faces 읽기 시도
            mio = meshio.read(str(case_dir), file_format="openfoam")
            with tempfile.NamedTemporaryFile(suffix=".vtu", delete=False) as tmp:
                tmp_path = tmp.name
            meshio.write(tmp_path, mio)
            result = pv.read(tmp_path)
            try:
                Path(tmp_path).unlink()
            except Exception:
                pass
            if getattr(result, "n_cells", 0) > 0:
                return result
        except Exception as e:
            log.warning(f"meshio OpenFOAM 읽기 실패: {e}")

        return None

    def _load_msh(self, msh_path: Path) -> bool:
        """MSH (Gmsh) 파일을 meshio 경유로 읽어 표시."""
        try:
            import meshio
            import tempfile
            mio = meshio.read(str(msh_path))
            # VTU로 변환 후 pyvista로 읽기
            with tempfile.NamedTemporaryFile(suffix=".vtu", delete=False) as tmp:
                tmp_path = tmp.name
            meshio.write(tmp_path, mio)
            result = self.load_mesh(tmp_path, show_edges=True)
            try:
                Path(tmp_path).unlink()
            except Exception:
                pass
            return result
        except Exception as e:
            log.warning(f"MSH 로드 실패: {e}")
            return False

    def clear(self) -> None:
        """뷰어 초기화."""
        self._current_mesh = None
        self._mesh_actor = None
        self._points_actor = None
        if hasattr(self, "_quality_btn"):
            self._quality_btn.setEnabled(False)
            self._quality_btn.setChecked(False)
        if self._plotter:
            try:
                self._plotter.clear()
            except Exception:
                pass
        self._info_label.setText("대기 중...")

    def set_show_edges(self, show: bool) -> None:
        self._show_edges = show
        self._edge_btn.setChecked(show)
        self._rerender()

    def set_show_points(self, show: bool) -> None:
        self._show_points = show
        self._pts_btn.setChecked(show)
        self._rerender()

    def set_opacity(self, opacity: float) -> None:
        self._opacity = max(0.0, min(1.0, opacity))
        self._rerender()

    # ------------------------------------------------------------------
    # 내부 렌더링
    # ------------------------------------------------------------------

    def _render_mesh(self, mesh: object, camera_view: str = "isometric") -> None:
        """메시를 플로터에 그림."""
        if self._plotter is None:
            return

        try:
            self._plotter.clear()
            self._plotter.background_color = "#0d1117"

            # 라이팅
            self._plotter.add_light(
                pv.Light(position=(1, 1, 1), intensity=0.8, color="white")
            )
            self._plotter.add_light(
                pv.Light(position=(-1, -1, 0.5), intensity=0.4, color="lightblue")
            )

            # 메시 추가
            self._mesh_actor = self._plotter.add_mesh(
                mesh,
                color="#00d9ff",
                opacity=self._opacity,
                show_edges=self._show_edges,
                edge_color="#ffffff" if self._show_edges else None,
                smooth_shading=True,
                name="main_mesh",
            )

            # 버텍스 표시
            if self._show_points and hasattr(mesh, "points"):
                self._points_actor = self._plotter.add_points(
                    mesh.points,
                    color="yellow",
                    point_size=6,
                    render_points_as_spheres=True,
                    name="mesh_points",
                )

            # 축
            self._plotter.add_axes(
                xlabel="X", ylabel="Y", zlabel="Z",
                line_width=2, color="white",
            )

            # 카메라 뷰
            self._apply_camera_view(camera_view)

        except Exception as e:
            log.error(f"_render_mesh 오류: {e}")
            import traceback
            traceback.print_exc()

    def _rerender(self) -> None:
        """현재 메시를 현재 설정으로 다시 그림."""
        if self._current_mesh is None or self._plotter is None:
            return
        self._render_mesh(self._current_mesh, camera_view="isometric")

    def _apply_camera_view(self, view: str) -> None:
        if self._plotter is None:
            return
        if view == "front":
            self._plotter.view_xy()
        elif view == "top":
            self._plotter.view_xz()
        elif view == "side":
            self._plotter.view_yz()
        else:
            self._plotter.view_isometric()
        self._plotter.reset_camera()

    def _update_info(self, path: Path, mesh: object) -> None:
        v = getattr(mesh, "n_points", 0)
        bounds = getattr(mesh, "bounds", [0, 1, 0, 1, 0, 1])
        scale = round(max(
            bounds[1] - bounds[0],
            bounds[3] - bounds[2],
            bounds[5] - bounds[4],
        ), 4)
        face_str, cell_str = _mesh_element_label(mesh)
        parts = [f"📄 {path.name}", f"📍 {v:,} pts"]
        if face_str:
            parts.append(face_str)
        if cell_str:
            parts.append(cell_str)
        parts.append(f"📏 scale={scale}")
        self._info_label.setText(" | ".join(parts))

    # ------------------------------------------------------------------
    # 뷰 버튼 핸들러
    # ------------------------------------------------------------------

    def _view_iso(self) -> None:
        if self._plotter:
            self._plotter.view_isometric()
            self._plotter.reset_camera()

    def _view_front(self) -> None:
        if self._plotter:
            self._plotter.view_xy()
            self._plotter.reset_camera()

    def _view_top(self) -> None:
        if self._plotter:
            self._plotter.view_xz()
            self._plotter.reset_camera()

    def _view_side(self) -> None:
        if self._plotter:
            self._plotter.view_yz()
            self._plotter.reset_camera()

    def _reset_camera(self) -> None:
        if self._plotter:
            self._plotter.reset_camera()

    def _toggle_edges(self, checked: bool) -> None:
        self._show_edges = checked
        self._edge_btn.setText("엣지 ON" if checked else "엣지 OFF")
        self._rerender()

    def _toggle_points(self, checked: bool) -> None:
        self._show_points = checked
        self._rerender()

    def _toggle_wireframe(self, checked: bool) -> None:
        if self._plotter is None or self._current_mesh is None:
            return
        try:
            self._plotter.clear()
            self._plotter.background_color = "#0d1117"
            style = "wireframe" if checked else "surface"
            self._plotter.add_mesh(
                self._current_mesh,
                color="#00d9ff",
                style=style,
                opacity=self._opacity,
                name="main_mesh",
            )
            self._plotter.add_axes(xlabel="X", ylabel="Y", zlabel="Z", color="white")
            self._plotter.reset_camera()
        except Exception as e:
            log.error(f"_toggle_wireframe 오류: {e}")

    def _toggle_slice(self, checked: bool) -> None:
        """단면(Slice) 위젯 토글."""
        if self._plotter is None or self._current_mesh is None:
            return
        self._slice_active = checked
        # Clip과 동시에 켤 수 없음
        if checked and self._clip_active:
            self._clip_btn.setChecked(False)

        try:
            self._plotter.clear()
            self._plotter.background_color = "#0d1117"
            self._plotter.add_axes(xlabel="X", ylabel="Y", zlabel="Z", color="white")

            if checked:
                # 인터랙티브 슬라이스 위젯 (드래그로 단면 이동)
                self._plotter.add_mesh_slice(
                    self._current_mesh,
                    normal="x",
                    color="#00d9ff",
                    show_edges=self._show_edges,
                    edge_color="#ffffff" if self._show_edges else None,
                )
            else:
                self._render_mesh(self._current_mesh)
        except Exception as e:
            log.error(f"_toggle_slice 오류: {e}")
            self._render_mesh(self._current_mesh)

    def _toggle_clip(self, checked: bool) -> None:
        """클리핑 평면(Clip) 위젯 토글."""
        if self._plotter is None or self._current_mesh is None:
            return
        self._clip_active = checked
        # Slice와 동시에 켤 수 없음
        if checked and self._slice_active:
            self._slice_btn.setChecked(False)

        try:
            self._plotter.clear()
            self._plotter.background_color = "#0d1117"
            self._plotter.add_axes(xlabel="X", ylabel="Y", zlabel="Z", color="white")

            if checked:
                # 인터랙티브 클리핑 평면 (드래그로 잘라내기)
                self._plotter.add_mesh_clip_plane(
                    self._current_mesh,
                    normal="x",
                    color="#00d9ff",
                    show_edges=self._show_edges,
                    edge_color="#ffffff" if self._show_edges else None,
                    opacity=self._opacity,
                )
            else:
                self._render_mesh(self._current_mesh)
        except Exception as e:
            log.error(f"_toggle_clip 오류: {e}")
            self._render_mesh(self._current_mesh)

    def _on_quality_metric_selected(self, action: object) -> None:
        """드롭다운에서 품질 메트릭 선택 시 호출."""
        metric_key = action.data()  # type: ignore[union-attr]
        if metric_key in self._QUALITY_METRICS:
            self._quality_metric = metric_key
            label = self._QUALITY_METRICS[metric_key][0]
            self._quality_btn.setText(f"품질: {label} ▾")
            # 이미 활성화돼 있으면 즉시 재렌더
            if self._quality_btn.isChecked():
                self._toggle_quality_color(True)

    def _toggle_quality_color(self, checked: bool) -> None:
        """선택된 메트릭 기반 셀 품질 색상화 토글."""
        if self._plotter is None or self._current_mesh is None:
            return
        try:
            self._plotter.clear()
            self._plotter.background_color = "#0d1117"
            self._plotter.add_axes(xlabel="X", ylabel="Y", zlabel="Z", color="white")

            if checked:
                try:
                    import numpy as _np
                    metric = self._quality_metric
                    metric_info = self._QUALITY_METRICS.get(metric, ("Quality", "Quality"))
                    qual = self._current_mesh.compute_cell_quality(  # type: ignore[union-attr]
                        quality_measure=metric
                    )
                    arr = qual.cell_data.get("CellQuality")
                    if arr is not None and len(arr) > 0:
                        clim_min = float(_np.percentile(arr, 5))
                        clim_max = float(_np.percentile(arr, 95))
                        if clim_min >= clim_max:
                            clim_max = clim_min + 1.0
                        self._plotter.add_mesh(
                            qual,
                            scalars="CellQuality",
                            cmap="RdYlGn_r",
                            clim=[clim_min, clim_max],
                            show_edges=self._show_edges,
                            edge_color="#333333" if self._show_edges else None,
                            opacity=self._opacity,
                            scalar_bar_args={
                                "title": metric_info[0],
                                "color": "white",
                                "fmt": "%.2f",
                            },
                            name="quality_mesh",
                        )
                        self._plotter.reset_camera()
                        return
                except Exception as e:
                    log.warning(f"품질 색상화 실패, 기본 렌더로 전환: {e}")
            self._render_mesh(self._current_mesh)
        except Exception as e:
            log.error(f"_toggle_quality_color 오류: {e}")
            self._render_mesh(self._current_mesh)

    def closeEvent(self, event: object) -> None:
        if self._plotter:
            try:
                self._plotter.close()
            except Exception:
                pass
        super().closeEvent(event)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 공개 위젯 (자동 선택)
# ---------------------------------------------------------------------------

def _separator() -> QWidget:
    sep = QWidget()
    sep.setFixedWidth(1)
    sep.setStyleSheet("background: #30363d;")
    return sep


class MeshViewerWidget(QWidget):
    """3D 메시 뷰어 위젯.

    pyvistaqt 설치 시: 인터랙티브 QtInteractor (마우스 회전/줌/팬)
    미설치 시: 정적 PNG 렌더링 폴백
    """

    # 메시 로드 완료 후 품질 통계 Signal
    mesh_stats_computed = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if PYVISTAQT_AVAILABLE and PYVISTA_AVAILABLE:
            self._viewer: InteractiveMeshViewer | StaticMeshViewer = InteractiveMeshViewer(self)
            log.info("인터랙티브 3D 뷰어 초기화 완료 (pyvistaqt)")
            # mesh_ready Signal로 통계 계산 연결 (monkey-patch 방지)
            if hasattr(self._viewer, "mesh_ready"):
                self._viewer.mesh_ready.connect(self._compute_and_emit_stats)
        else:
            self._viewer = StaticMeshViewer(self)
            log.warning("정적 PNG 폴백 뷰어 사용 중 (pyvistaqt 미설치)")

        layout.addWidget(self._viewer)

    def _compute_and_emit_stats(self, mesh: object) -> None:
        """PyVista compute_cell_quality()로 메시 품질 통계를 계산하고 Signal emit."""
        if not PYVISTA_AVAILABLE or mesh is None:
            return
        try:
            stats: dict = {}
            n_cells = getattr(mesh, "n_cells", 0)
            n_points = getattr(mesh, "n_points", 0)
            stats["n_cells"] = n_cells
            stats["n_points"] = n_points

            # 볼륨 셀 타입 확인
            try:
                cell_types = set(getattr(mesh, "celltypes", []))
                is_volume = bool(cell_types & _VOLUME_CELL_TYPES)
                stats["is_volume"] = is_volume

                # 셀 구성 (타입별 개수)
                hex_types = {12, 25, 29}  # VTK_HEXAHEDRON, VTK_QUADRATIC_HEX, VTK_TRIQUADRATIC_HEX
                tet_types = {10, 24}      # VTK_TETRA, VTK_QUADRATIC_TETRA
                prism_types = {13, 26}    # VTK_WEDGE / VTK_QUADRATIC_WEDGE
                poly_types = {42}         # VTK_POLYHEDRON

                if n_cells > 0 and hasattr(mesh, "celltypes"):
                    ct_arr = list(getattr(mesh, "celltypes", []))
                    n_hex = sum(1 for t in ct_arr if t in hex_types)
                    n_tet = sum(1 for t in ct_arr if t in tet_types)
                    n_prism = sum(1 for t in ct_arr if t in prism_types)
                    n_poly = sum(1 for t in ct_arr if t in poly_types)
                    total = max(n_cells, 1)
                    stats["hex_ratio"] = n_hex / total
                    stats["tet_ratio"] = n_tet / total
                    stats["prism_ratio"] = n_prism / total
                    stats["poly_ratio"] = n_poly / total
                    stats["n_hex"] = n_hex
                    stats["n_tet"] = n_tet
                    stats["n_prism"] = n_prism
                    stats["n_poly"] = n_poly
            except Exception:
                pass

            # 품질 메트릭 (볼륨 메시인 경우에만, 셀 수 제한)
            if n_cells > 0 and n_cells <= 500_000:
                try:
                    qual = mesh.compute_cell_quality(quality_measure="aspect_ratio")  # type: ignore[union-attr]
                    arr = qual.cell_data.get("CellQuality")
                    if arr is not None and len(arr) > 0:
                        import numpy as _np
                        arr = _np.asarray(arr, dtype=float)
                        arr = arr[_np.isfinite(arr)]
                        if len(arr) > 0:
                            stats["max_aspect_ratio"] = float(arr.max())
                            stats["mean_aspect_ratio"] = float(arr.mean())
                            stats["hist_aspect_ratio"] = arr.tolist()
                except Exception:
                    pass

                try:
                    skew = mesh.compute_cell_quality(quality_measure="skew")  # type: ignore[union-attr]
                    arr = skew.cell_data.get("CellQuality")
                    if arr is not None and len(arr) > 0:
                        import numpy as _np
                        arr = _np.asarray(arr, dtype=float)
                        arr = arr[_np.isfinite(arr)]
                        if len(arr) > 0:
                            stats["max_skewness"] = float(arr.max())
                            stats["mean_skewness"] = float(arr.mean())
                            stats["hist_skewness"] = arr.tolist()
                except Exception:
                    pass

            if stats:
                self.mesh_stats_computed.emit(stats)
                log.debug(f"메시 품질 통계 emit: {list(stats.keys())}")
        except Exception as e:
            log.debug(f"메시 품질 통계 계산 실패: {e}")

    # ------------------------------------------------------------------
    # 공개 API (main_window에서 호출)
    # ------------------------------------------------------------------

    def load_mesh(
        self,
        mesh_path: str | Path,
        camera_view: str = "isometric",
        show_edges: bool = True,
        show_points: bool = False,
        opacity: float = 0.95,
    ) -> bool:
        """메시 파일 로드."""
        return self._viewer.load_mesh(
            mesh_path,
            camera_view=camera_view,
            show_edges=show_edges,
            show_points=show_points,
            opacity=opacity,
        )

    def load_polymesh(self, case_dir: str | Path) -> bool:
        """OpenFOAM case 디렉터리에서 메시 로드."""
        return self._viewer.load_polymesh(case_dir)

    def clear(self) -> None:
        """뷰어 초기화."""
        self._viewer.clear()

    def set_show_edges(self, show: bool) -> None:
        self._viewer.set_show_edges(show)

    def set_opacity(self, opacity: float) -> None:
        self._viewer.set_opacity(opacity)

    # 하위 호환 (이전 코드에서 호출될 수 있음)
    def set_camera_view(self, view: str) -> None:
        if hasattr(self._viewer, "_apply_camera_view"):
            self._viewer._apply_camera_view(view)
