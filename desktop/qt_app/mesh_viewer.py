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
import os

log = logging.getLogger(__name__)


def _env_flag(name: str) -> bool:
    """환경변수를 boolean feature flag로 해석한다."""
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _qt_runtime_is_headless() -> bool:
    """Qt/PyVistaQt가 native window를 만들기 어려운 환경인지 판별한다."""
    if os.environ.get("QT_QPA_PLATFORM", "").strip().lower() == "offscreen":
        return True
    if os.name == "nt":
        return False
    return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _force_static_viewer_requested() -> bool:
    """VTK native window 문제를 우회하기 위한 정적 뷰어 강제 flag."""
    return _env_flag("AUTOTESSELL_STATIC_VIEWER")


def _direct_polymesh_preview_enabled() -> bool:
    """OpenFOAMReader 직접 preview를 명시적으로 허용했는지 확인한다."""
    return _env_flag("AUTOTESSELL_POLYMESH_DIRECT_PREVIEW")


def _find_case_preview_mesh(case_dir: Path) -> Path | None:
    """OpenFOAM case에서 GUI preview에 적합한 VTK 계열 파일을 찾는다.

    foamToVTK 출력 구조:
      VTK/caseName_N/internal.vtu   — 실제 볼륨 cells (Quality 계산에 필수)
      VTK/caseName_N/boundary/*.vtp — 경계 면

    stale VTK (이전 tier/snappy 결과) 가 남아 있으면 GUI가 실제와 다른 셀 구성을
    보여주므로, `constant/polyMesh/faces` 의 mtime 보다 오래된 VTU 는 무시한다.
    """
    try:
        poly_faces = case_dir / "constant" / "polyMesh" / "faces"
        poly_mtime = poly_faces.stat().st_mtime if poly_faces.exists() else 0.0
    except Exception:
        poly_mtime = 0.0

    def _not_stale(p: Path) -> bool:
        try:
            return p.stat().st_mtime + 1.0 >= poly_mtime
        except Exception:
            return True

    # 우선순위 1: internal.vtu (foamToVTK 볼륨 출력) — stale 제외
    internal_files = [
        p for p in case_dir.glob("**/internal.vtu")
        if p.is_file() and _not_stale(p)
    ]
    if internal_files:
        return max(internal_files, key=lambda p: p.stat().st_mtime)
    # 우선순위 2: 나머지 VTK 포맷 — stale 제외
    for pattern in ("**/*.vtu", "**/*.vtk", "**/*.vtp", "**/*.vtm"):
        files = [
            p for p in case_dir.glob(pattern)
            if p.is_file() and _not_stale(p)
        ]
        if files:
            return max(files, key=lambda p: p.stat().st_mtime)
    return None


try:
    import pyvista as pv
    import numpy as np

    pv.OFF_SCREEN = _qt_runtime_is_headless()
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


# PyVista cell_quality 측정 키는 셀 타입마다 지원 범위가 다르다. ``skew`` 는
# quadrilateral / hexahedron 전용 → 표면(tri) 메쉬와 tetrahedral mesh 에서는 모두
# ``-1`` sentinel 을 반환한다. 사용자 정의 키 → 시도할 PyVista 측정 키 시퀀스.
_QUALITY_MEASURE_FALLBACKS = {
    # GUI label keys → ordered list of PyVista measures to try until 유효 값이 나옴.
    "skew":              ["skew", "scaled_jacobian", "shape"],
    "skewness":          ["skew", "scaled_jacobian", "shape"],
    "scaled_jacobian":   ["scaled_jacobian", "shape"],
    "aspect_ratio":      ["aspect_ratio", "aspect_frobenius", "max_edge_ratio"],
    "max_angle":         ["max_angle", "min_angle"],
    "min_angle":         ["min_angle", "max_angle"],
    "shape":             ["shape", "scaled_jacobian"],
    "volume":            ["volume", "jacobian"],
}


def _compute_cell_quality_compat(mesh, measure: str):
    """PyVista 0.45+ ``cell_quality()`` 우선 + 구버전 ``compute_cell_quality()`` fallback.

    추가로 — 요청된 measure 가 해당 셀 타입에 미지원이면 (모두 -1 sentinel) 같은
    의미 군의 대체 측정 키 (`_QUALITY_MEASURE_FALLBACKS`) 로 자동 재시도해 의미
    있는 컬러맵을 만든다.

    Returns: ``(qual_dataset, scalar_array_name)``. 실패 시 ``(None, "")``.
    """
    if mesh is None:
        return None, ""
    import warnings
    try:
        import numpy as _np

        candidates = _QUALITY_MEASURE_FALLBACKS.get(measure, [measure])

        def _try_one(m: str):
            try:
                if hasattr(mesh, "cell_quality"):
                    qual = mesh.cell_quality(quality_measure=m)
                    name = m if m in qual.cell_data else (
                        list(qual.cell_data.keys())[0]
                        if qual.cell_data else ""
                    )
                else:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        qual = mesh.compute_cell_quality(quality_measure=m)
                    name = "CellQuality"
                arr = qual.cell_data.get(name) if name else None
                if arr is None:
                    return None, ""
                a = _np.asarray(arr, dtype=float)
                # 유효 값(>-0.5 + finite) 이 하나도 없으면 다음 측정 키로 fallback.
                if not _np.any((a > -0.5) & _np.isfinite(a)):
                    return None, ""
                return qual, name
            except Exception:
                return None, ""

        for m in candidates:
            q, n = _try_one(m)
            if q is not None:
                return q, n
        return None, ""
    except Exception:
        return None, ""


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

if _qt_runtime_is_headless() or _force_static_viewer_requested():
    PYVISTAQT_AVAILABLE = False
    QtInteractor = None  # type: ignore[assignment]
    if _force_static_viewer_requested():
        log.info("AUTOTESSELL_STATIC_VIEWER=1 — 정적 PNG 뷰어 사용")
    else:
        log.info("headless/offscreen Qt 환경 — 정적 PNG 뷰어 사용")
else:
    try:
        from pyvistaqt import QtInteractor
        PYVISTAQT_AVAILABLE = True
    except ImportError:
        PYVISTAQT_AVAILABLE = False
        QtInteractor = None  # type: ignore[assignment]
        log.warning("pyvistaqt 미설치 — pip install pyvistaqt")
    except Exception as e:
        PYVISTAQT_AVAILABLE = False
        QtInteractor = None  # type: ignore[assignment]
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

            # smooth_shading=True 를 add_mesh에 넘기면 PyVista 내부에서
            # prepare_smooth_shading → _extract_surface → VTK _update_alg 를
            # 백그라운드 스레드에서 호출해 SIGSEGV를 유발한다.
            # 대신 normals를 미리 구운 뒤 smooth_shading=False 로 렌더한다.
            try:
                if isinstance(mesh, pv.UnstructuredGrid):
                    mesh = mesh.extract_surface(algorithm="dataset_surface")
            except Exception:
                pass
            try:
                if isinstance(mesh, pv.PolyData):
                    mesh = mesh.compute_normals(
                        feature_angle=30,
                        split_vertices=True,
                        consistent_normals=True,
                        non_manifold_traversal=False,
                    )
            except Exception:
                pass

            plotter.add_mesh(
                mesh,
                color="#00d9ff",
                opacity=opacity,
                show_edges=show_edges,
                edge_color="#ffffff" if show_edges else None,
                smooth_shading=False,  # normals already baked in above
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

    # 메시 로드 완료 후 PyVista mesh 객체 전달 — Quality 통계 계산 연결용
    mesh_ready = Signal(object)

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
        self._rendering: bool = False
        self._temp_files: list[Path] = []
        self._pending_path: object = None
        self._pending_kwargs: dict = {}

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

        if self._rendering:
            # 이전 렌더가 진행 중이면 최신 요청만 보관한다.
            self._pending_path = path
            self._pending_kwargs = dict(kwargs)
            return True

        self._set_placeholder("⏳ 렌더링 중...")
        self._info_label.setText("⏳ 메시 로딩 중...")

        # VTK 필터(_update_alg)를 백그라운드 스레드에서 실행하면 WSL2/X11 환경에서
        # SIGSEGV가 발생한다. QTimer.singleShot(0) 으로 메인 스레드에서 실행한다.
        from PySide6.QtCore import QTimer
        self._rendering = True
        QTimer.singleShot(0, lambda: self._do_render(path, **{k: v for k, v in kwargs.items()}))
        return True

    def _do_render(self, path: object, **kwargs: object) -> None:
        """메인 스레드에서 PyVista 오프스크린 렌더링을 실행한다."""
        worker = RenderWorker()
        worker.render_finished.connect(self._on_done)
        worker.render_error.connect(self._on_error)

        show_edges = bool(kwargs.get("show_edges", True))
        show_points = bool(kwargs.get("show_points", False))
        camera_view = str(kwargs.get("camera_view", "isometric"))
        opacity = float(kwargs.get("opacity", 0.95))

        worker.render_mesh(
            path,
            show_edges=show_edges,
            show_points=show_points,
            camera_view=camera_view,
            opacity=opacity,
        )

        # 렌더 완료 후 품질 통계 파이프라인 트리거 — 메시를 한번 더 로드해
        # mesh_ready를 emit한다 (메인 스레드 실행이므로 VTK 안전).
        try:
            mesh = _pv_read_any(Path(str(path)))
            if mesh is not None:
                self.mesh_ready.emit(mesh)
        except Exception:
            pass

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
        self._rendering = False
        self._flush_pending()

    def _on_error(self, msg: str) -> None:
        self._set_placeholder(f"❌ 오류:\n{msg[:50]}")
        self._info_label.setText(f"❌ {msg[:80]}")
        self._rendering = False
        self._flush_pending()

    def _flush_pending(self) -> None:
        """대기 중인 렌더 요청이 있으면 지금 시작한다."""
        if self._pending_path is not None:
            path, kwargs = self._pending_path, self._pending_kwargs
            self._pending_path = None
            self._pending_kwargs = {}
            self.load_mesh(path, **kwargs)

    def load_polymesh(self, case_dir: str | Path) -> bool:
        case_dir = Path(case_dir)
        preview_mesh = _find_case_preview_mesh(case_dir)
        if preview_mesh is not None:
            return self.load_mesh(preview_mesh)
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
        # BC-INTEGRATION / beta2798 — face-pick BC ui (lazy init).
        self._bc_ui = None
        self._bc_overlay_actors: list = []

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 툴바
        toolbar = self._build_toolbar()
        layout.addWidget(toolbar)

        # QtInteractor (VTK 렌더 윈도우) — BETA2864 ParaView-style 룩.
        try:
            self._plotter = QtInteractor(self)
            self._plotter.setMinimumSize(400, 300)
            # ParaView 와 비슷한 grey-blue 그라데이션 배경.
            try:
                self._plotter.set_background("#3c4046", top="#7a808a")
            except Exception:
                self._plotter.background_color = "#3c4046"
            # Anti-aliasing — MSAA / SSAA / FXAA 순서로 시도.
            for aa in ("ssaa", "msaa", "fxaa"):
                try:
                    self._plotter.enable_anti_aliasing(aa)
                    break
                except Exception:
                    continue
            # 3-light 표준 조명 — ParaView 의 default headlight 유사.
            try:
                self._plotter.enable_lightkit()
            except Exception:
                try:
                    self._plotter.enable_3_lights()
                except Exception:
                    pass
            # parallel projection — engineering view 표준 (orthographic).
            try:
                self._plotter.enable_parallel_projection()
            except Exception:
                pass
            # 좌하단 axes 위젯 (ParaView 스타일).
            try:
                self._plotter.show_axes()
            except Exception:
                try:
                    self._plotter.add_axes(
                        xlabel="X", ylabel="Y", zlabel="Z",
                        line_width=3, labels_off=False,
                    )
                except Exception:
                    pass
            layout.addWidget(self._plotter, stretch=1)
        except Exception as e:
            log.error(f"QtInteractor 초기화 실패: {e}")
            fallback = QLabel(f"❌ QtInteractor 초기화 실패:\n{e}")
            fallback.setAlignment(Qt.AlignCenter)
            fallback.setStyleSheet("background: #0d1117; color: white;")
            layout.addWidget(fallback, stretch=1)

        # BC-INTEGRATION — 중복 attach 제거 (BETA2810 이후 외부 MeshViewerWidget
        # 가 toolbar 부착을 담당). 여기서 한 번 더 부착하면 "Pick faces (single/box)"
        # 등 버튼이 두 번 표시됨.

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
        # BETA2876 — 단일 QHBoxLayout 가 너무 길어 우측 컨트롤이 화면 밖으로 잘려
        # 보이지 않는 문제 → 2 행 레이아웃 으로 변경. 1 행: 뷰/엣지/버텍스/품질,
        # 2 행: Slice/Clip/축/슬라이더. 두 행 모두 전체 너비에 맞춰 wrap 됨.
        bar = QWidget()
        bar.setStyleSheet(
            "QWidget { background-color: #161b22; border-bottom: 1px solid #30363d; }"
        )
        outer = QVBoxLayout(bar)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(4)
        row1 = QWidget(); row2 = QWidget()
        h = QHBoxLayout(row1); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(6)
        h2 = QHBoxLayout(row2); h2.setContentsMargins(0, 0, 0, 0); h2.setSpacing(6)
        outer.addWidget(row1); outer.addWidget(row2)

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

        # BETA2876 — 품질 토글: 1행 우측에 배치 (한 손에 잡힘).
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
        h.addStretch()
        h.addWidget(self._quality_btn)

        # ── 2 행: Slice / Clip / 축 / 슬라이더 (BETA2876) ──────────────
        from PySide6.QtWidgets import QSlider
        from PySide6.QtCore import Qt as _Qt

        def _mode_btn(label: str, tip: str) -> QPushButton:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setFixedHeight(26)
            b.setToolTip(tip)
            b.setStyleSheet(
                "QPushButton { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; "
                "border-radius: 4px; padding: 0 8px; font-size: 11px; } "
                "QPushButton:checked { background: #388bfd; border-color: #58a6ff; color: white; } "
                "QPushButton:hover { background: #30363d; }"
            )
            return b

        h2.addWidget(QLabel("자르기:"))
        self._slice_btn = _mode_btn(
            "Slice",
            "단면(Slice) — 셀 표면 결대로 자름. 축 선택 + 슬라이더 드래그.",
        )
        self._slice_btn.toggled.connect(self._toggle_slice)
        h2.addWidget(self._slice_btn)
        self._clip_btn = _mode_btn(
            "Clip",
            "클립(Clip) — 셀 단위로 한쪽만 표시. 축 선택 + 슬라이더 드래그.",
        )
        self._clip_btn.toggled.connect(self._toggle_clip)
        h2.addWidget(self._clip_btn)

        h2.addWidget(_separator())

        # 축 선택 (X/Y/Z) + 위치 슬라이더 — Slice/Clip 활성 시에만 동작.
        def _axis_btn(label: str) -> QPushButton:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setFixedHeight(26); b.setFixedWidth(28)
            b.setStyleSheet(
                "QPushButton { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; "
                "border-radius: 4px; font-size: 11px; font-weight: 700; } "
                "QPushButton:checked { background: #ff7b54; border-color: #ff9f7b; color: white; } "
                "QPushButton:hover { background: #30363d; }"
            )
            return b

        self._axis_btns: dict[str, QPushButton] = {}
        for axis in ("X", "Y", "Z"):
            ab = _axis_btn(axis)
            ab.clicked.connect(lambda _checked=False, a=axis: self._set_slice_axis(a))
            self._axis_btns[axis] = ab
            h2.addWidget(ab)
        self._slice_axis: str = "X"
        self._axis_btns["X"].setChecked(True)

        self._slice_slider = QSlider(_Qt.Horizontal)
        self._slice_slider.setRange(0, 1000)   # normalized [0..1] × 1000
        self._slice_slider.setValue(500)       # mid-plane.
        self._slice_slider.setFixedHeight(26)
        self._slice_slider.setMinimumWidth(140)
        self._slice_slider.setEnabled(False)
        self._slice_slider.setToolTip("선택한 축을 따라 평면 위치 드래그 (셀 결 따라 스냅).")
        self._slice_slider.setStyleSheet(
            "QSlider::groove:horizontal { background: #30363d; height: 4px; border-radius: 2px; } "
            "QSlider::handle:horizontal { background: #58a6ff; width: 14px; height: 14px; "
            "  margin: -6px 0; border-radius: 7px; } "
            "QSlider::sub-page:horizontal { background: #388bfd; border-radius: 2px; }"
        )
        self._slice_slider.valueChanged.connect(self._on_slice_slider_changed)
        h2.addWidget(self._slice_slider, stretch=1)

        self._slice_pos_label = QLabel("—")
        self._slice_pos_label.setFixedHeight(26)
        self._slice_pos_label.setMinimumWidth(78)
        self._slice_pos_label.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self._slice_pos_label.setStyleSheet(
            "QLabel { color: #c9d1d9; background: transparent; "
            "font-family: 'Courier New', monospace; font-size: 11px; padding-right: 4px; }"
        )
        h2.addWidget(self._slice_pos_label)

        h.addStretch()

        # 2026-05 사용자 요청: '와이어프레임' 버튼 제거. 엣지 표시는 '엣지 표시'
        # 토글 (_edge_btn) 으로만 컨트롤한다.
        self._wire_btn = None  # type: ignore[assignment]

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

        # 1. foamToVTK/meshio 결과 우선.
        preview_mesh = _find_case_preview_mesh(case_dir)
        if preview_mesh is not None:
            return self.load_mesh(preview_mesh, show_edges=True)

        # 2. OpenFOAM polyMesh 직접 읽기
        # pv.OpenFOAMReader는 케이스 디렉터리 안의 빈 .foam 파일을 입력으로 받음
        if (case_dir / "constant" / "polyMesh").exists():
            if not _direct_polymesh_preview_enabled():
                self._info_label.setText(
                    "✅ OpenFOAM polyMesh 생성됨 "
                    "(3D preview는 foamToVTK 결과가 있을 때 표시)"
                )
                return True
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
                    # Quality 탭 히스토그램 자동 갱신을 위해 mesh_ready 명시 emit.
                    # (_on_mesh_loaded 경로를 타지 않는 직접 읽기에서는 기존 emit 없음)
                    if hasattr(self, "mesh_ready"):
                        try:
                            self.mesh_ready.emit(mesh)
                        except Exception:
                            pass
                    return True
            except Exception as e:
                log.warning(f"OpenFOAM 읽기 실패: {e}")

            # 읽기 실패해도 polyMesh 존재 확인됐으므로 텍스트로 표시
            self._info_label.setText("✅ OpenFOAM polyMesh 생성됨 (3D 렌더링 불가)")
            return True

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
        """메시를 플로터에 그림 — BETA2864 ParaView-style 렌더 룩.

        - grey-blue 그라데이션 배경
        - 3-point lighting (이미 lightkit 활성)
        - PBR-ish 머티리얼 (silver-blue surface, 어두운 edge)
        - axes orientation widget (좌하단)
        - parallel projection (orthographic, ParaView default)
        """
        if self._plotter is None:
            return

        try:
            self._plotter.clear()
            try:
                self._plotter.set_background("#3c4046", top="#7a808a")
            except Exception:
                self._plotter.background_color = "#3c4046"

            # UnstructuredGrid (볼륨 메시)는 VTK plotter.clear() 후 재사용 시
            # dangling C++ 참조로 segfault가 발생한다. 표면을 추출해 PolyData로
            # 변환한 뒤 렌더링한다.
            try:
                if isinstance(mesh, pv.UnstructuredGrid):
                    mesh = mesh.extract_surface(algorithm="dataset_surface")
            except Exception:
                pass

            # BETA2871 — normals outward 보장 + auto-orient.
            # PolyData: compute_normals 으로 outward consistent normals 생성
            # (auto_orient_normals=True 로 closed surface 의 normal 외향 강제).
            try:
                if isinstance(mesh, pv.PolyData) and hasattr(mesh, "compute_normals"):
                    mesh = mesh.compute_normals(
                        feature_angle=30,
                        split_vertices=True,
                        consistent_normals=True,
                        auto_orient_normals=True,
                        non_manifold_traversal=False,
                        flip_normals=False,
                    )
            except Exception:
                pass

            # BETA2871 — solid Phong shading + backface culling ON.
            # 이전 (BETA2866) backface/frontface culling 모두 OFF 였음 → 닫힌
            # surface 의 안쪽 (back face) 가 viewport 일부에서 뚫려 보이는 착시.
            # 정상 구성 = backface culling ON (앞면만 그림) + outward normals 보장.
            self._mesh_actor = self._plotter.add_mesh(
                mesh,
                color="#c9d1d9",
                opacity=self._opacity,
                show_edges=self._show_edges,
                edge_color="#1a1f24" if self._show_edges else None,
                line_width=0.6,
                smooth_shading=True,
                ambient=0.30,
                diffuse=0.85,
                specular=0.18,
                specular_power=15,
                lighting=True,
                culling="back",  # backface culling — 앞면만 표시
                name="main_mesh",
            )
            # VTK property 보강 — 일부 PyVista 버전이 culling kwarg 무시 가능.
            try:
                prop = self._mesh_actor.GetProperty()  # vtkProperty
                prop.BackfaceCullingOn()      # 뒷면 안 그림 (착시 제거)
                prop.FrontfaceCullingOff()    # 앞면만 그림
                prop.SetInterpolationToPhong()
            except Exception:
                pass

            # 버텍스 표시
            if self._show_points and hasattr(mesh, "points"):
                self._points_actor = self._plotter.add_points(
                    mesh.points,
                    color="#ffd866",
                    point_size=5,
                    render_points_as_spheres=True,
                    name="mesh_points",
                )

            # ParaView 스타일 axes orientation widget (좌하단).
            try:
                self._plotter.show_axes()
            except Exception:
                self._plotter.add_axes(
                    xlabel="X", ylabel="Y", zlabel="Z",
                    line_width=3,
                )

            # parallel projection (engineering view).
            try:
                self._plotter.enable_parallel_projection()
            except Exception:
                pass

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
        if view == "keep":
            # 호출자가 카메라를 외부에서 복원할 예정이므로 변경하지 않음.
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

    # _toggle_wireframe 핸들러 제거 — 2026-05 GUI 정리에서 와이어프레임 버튼 삭제.

    # ── BETA2861 — cell-aligned slice / clip with axis + slider control ────
    def _set_slice_axis(self, axis: str) -> None:
        """축 선택 (X/Y/Z) — 슬라이더 범위를 해당 축의 bbox 로 갱신. 카메라 보존."""
        axis = axis.upper()
        if axis not in ("X", "Y", "Z"):
            return
        self._slice_axis = axis
        for k, b in self._axis_btns.items():
            try:
                b.setChecked(k == axis)
            except Exception:
                pass
        if self._slice_active or self._clip_active:
            cam = self._capture_camera()
            self._apply_slice_or_clip(preserve_camera=cam)

    def _on_slice_slider_changed(self, value: int) -> None:
        """슬라이더 드래그 — 슬라이스/클립 평면 위치만 갱신, 카메라(zoom 등) 보존."""
        if not (self._slice_active or self._clip_active):
            return
        cam = self._capture_camera()
        self._apply_slice_or_clip(preserve_camera=cam)

    def _slice_axis_index(self) -> int:
        return {"X": 0, "Y": 1, "Z": 2}[self._slice_axis]

    def _slice_world_position(self) -> tuple[float, float, float]:
        """슬라이더 [0..1000] 을 mesh bbox 의 해당 축 위치로 변환."""
        bounds = (-1.0, 1.0, -1.0, 1.0, -1.0, 1.0)
        try:
            bounds = tuple(self._current_mesh.bounds)  # type: ignore[union-attr]
        except Exception:
            pass
        idx = self._slice_axis_index()
        lo, hi = bounds[idx * 2], bounds[idx * 2 + 1]
        t = float(self._slice_slider.value()) / 1000.0
        return lo, hi, lo + (hi - lo) * t

    def _toggle_slice(self, checked: bool) -> None:
        """Slice 토글 — 셀 결을 따라 face stratum 표시. 카메라 위치 보존."""
        if self._plotter is None or self._current_mesh is None:
            return
        cam = self._capture_camera()
        self._slice_active = checked
        if checked and self._clip_active:
            self._clip_btn.setChecked(False)
        self._slice_slider.setEnabled(checked or self._clip_active)
        if checked:
            self._apply_slice_or_clip(preserve_camera=cam)
        else:
            self._render_mesh(self._current_mesh, camera_view="keep")
            self._restore_camera(cam)
            self._slice_pos_label.setText("—")

    def _toggle_clip(self, checked: bool) -> None:
        """Clip 토글 — 셀 단위로 한쪽 영역만 (셀 cut 없음). 카메라 보존."""
        if self._plotter is None or self._current_mesh is None:
            return
        cam = self._capture_camera()
        self._clip_active = checked
        if checked and self._slice_active:
            self._slice_btn.setChecked(False)
        self._slice_slider.setEnabled(checked or self._slice_active)
        if checked:
            self._apply_slice_or_clip(preserve_camera=cam)
        else:
            self._render_mesh(self._current_mesh, camera_view="keep")
            self._restore_camera(cam)
            self._slice_pos_label.setText("—")

    def _capture_camera(self) -> tuple | None:
        """현재 카메라 상태 capture (slice/clip 등 재렌더 시 복원용)."""
        if self._plotter is None:
            return None
        try:
            cam = self._plotter.camera
            return (
                tuple(cam.position),
                tuple(cam.focal_point),
                tuple(cam.up),
                float(cam.parallel_scale),
                bool(cam.parallel_projection),
            )
        except Exception:
            try:
                # 구버전 fallback
                return tuple(self._plotter.camera_position)  # type: ignore[union-attr]
            except Exception:
                return None

    def _restore_camera(self, cam) -> None:
        """_capture_camera 로 저장한 상태 복원."""
        if self._plotter is None or cam is None:
            return
        try:
            if isinstance(cam, tuple) and len(cam) == 5:
                pos, foc, up, pscale, ppar = cam
                c = self._plotter.camera
                c.position = pos
                c.focal_point = foc
                c.up = up
                c.parallel_scale = pscale
                if ppar:
                    self._plotter.enable_parallel_projection()
            else:
                self._plotter.camera_position = cam  # type: ignore[assignment]
            self._plotter.render()
        except Exception:
            pass

    def _apply_slice_or_clip(self, preserve_camera=None) -> None:
        """현재 axis + 슬라이더 위치로 cell-aligned slice / clip 재렌더.

        preserve_camera: _capture_camera() 반환값. None 이면 현재 카메라를 즉석에서 캡처해 보존.
        """
        if self._plotter is None or self._current_mesh is None:
            return
        if preserve_camera is None:
            preserve_camera = self._capture_camera()
        try:
            import numpy as _np
            mesh = self._current_mesh
            lo, hi, pos = self._slice_world_position()
            self._slice_pos_label.setText(f"{self._slice_axis}={pos:+.3g}")

            # 셀 중심을 셀당 1점으로 사용 → cell-aligned (셀을 자르지 않음).
            try:
                centers = _np.asarray(mesh.cell_centers().points)
            except Exception:
                centers = None
            self._plotter.clear()
            # _render_mesh 와 동일한 ParaView-style 룩 (배경 그라데이션 + 축).
            try:
                self._plotter.set_background("#3c4046", top="#7a808a")
            except Exception:
                self._plotter.background_color = "#3c4046"
            try:
                self._plotter.show_axes()
            except Exception:
                self._plotter.add_axes(xlabel="X", ylabel="Y", zlabel="Z", line_width=3)
            try:
                self._plotter.enable_parallel_projection()
            except Exception:
                pass

            ax = self._slice_axis_index()

            # _render_mesh 와 동일한 머티리얼/lighting kwarg 묶음.
            _surf_style = dict(
                color="#c9d1d9",
                show_edges=self._show_edges,
                edge_color="#1a1f24" if self._show_edges else None,
                line_width=0.6,
                smooth_shading=True,
                ambient=0.30,
                diffuse=0.85,
                specular=0.18,
                specular_power=15,
                lighting=True,
            )

            def _harden_actor(actor) -> None:
                """outward normal + backface culling — 닫힌 surface 의 안쪽 빈 공간이
                viewport 일부를 통과해 보이는 착시 제거 (clip 결과 앞면 보장)."""
                try:
                    prop = actor.GetProperty()
                    prop.BackfaceCullingOn()
                    prop.FrontfaceCullingOff()
                    prop.SetInterpolationToPhong()
                except Exception:
                    pass

            def _orient_normals(poly):
                """PolyData 면 법선을 외향으로 일관 정렬."""
                try:
                    if isinstance(poly, pv.PolyData) and hasattr(poly, "compute_normals"):
                        return poly.compute_normals(
                            feature_angle=30,
                            split_vertices=True,
                            consistent_normals=True,
                            auto_orient_normals=True,
                            non_manifold_traversal=False,
                            flip_normals=False,
                        )
                except Exception:
                    pass
                return poly

            if self._slice_active:
                # Slice: 평면이 메쉬를 자른 *단면* 만 표시 (PyVista 의 plane slice).
                # 양쪽 셀 surface 를 모두 그리지 않는다 — 그러면 clip 과 구분이 안 됨.
                try:
                    normal = [0.0, 0.0, 0.0]
                    normal[ax] = 1.0
                    origin = mesh.center
                    # PyVista 의 plane slice — UnstructuredGrid 든 PolyData 든 모두 지원.
                    cross = mesh.slice(
                        normal=normal,
                        origin=(origin[0] if ax != 0 else pos,
                                origin[1] if ax != 1 else pos,
                                origin[2] if ax != 2 else pos),
                    )
                    # PyVista 의 ``slice`` 는 지정 평면에서 자른 평면 PolyData 를 반환.
                    self._mesh_actor = self._plotter.add_mesh(
                        cross,
                        color="#4ea3ff",
                        show_edges=self._show_edges,
                        edge_color="#0d1117" if self._show_edges else None,
                        line_width=0.7,
                        lighting=False,  # 단면은 평면 — flat shading.
                        name="slice_cross_section",
                    )
                except Exception as _e:
                    log.debug(f"slice fail, fallback: {_e}")
                    self._render_mesh(mesh, camera_view="keep")
                    self._restore_camera(preserve_camera)
                    return
            elif self._clip_active:
                # Clip: 셀 중심이 plane 한쪽에 있는 셀만 추출 (cell cut 없음).
                # 반대쪽 outline / wireframe 은 그리지 않음 — slice 와 시각적 구분 명확화.
                if centers is not None and centers.shape[0] == mesh.n_cells:
                    keep = _np.where(centers[:, ax] >= pos)[0]
                    if keep.size > 0:
                        kept = mesh.extract_cells(keep).extract_surface(
                            algorithm="dataset_surface",
                        )
                        kept = _orient_normals(kept)
                        self._mesh_actor = self._plotter.add_mesh(
                            kept, opacity=self._opacity, name="clip_main", **_surf_style,
                        )
                        _harden_actor(self._mesh_actor)
                else:
                    # 셀 단위 클립 불가 → bbox-clip fallback.
                    bounds = list(mesh.bounds)
                    bounds[ax * 2] = pos
                    clipped = mesh.clip_box(bounds, invert=False)
                    try:
                        clipped = clipped.extract_surface(algorithm="dataset_surface")
                    except Exception:
                        pass
                    clipped = _orient_normals(clipped)
                    self._mesh_actor = self._plotter.add_mesh(
                        clipped, opacity=self._opacity, name="clip_main_bbox",
                        **_surf_style,
                    )
                    _harden_actor(self._mesh_actor)
            # 카메라 복원 — slice/clip 토글이 view 를 리셋하지 않도록 마지막에 복원.
            self._restore_camera(preserve_camera)
        except Exception as e:
            log.error(f"_apply_slice_or_clip 오류: {e}")
            try:
                self._render_mesh(self._current_mesh, camera_view="keep")
                self._restore_camera(preserve_camera)
            except Exception:
                pass

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
        """선택된 메트릭 기반 셀 품질 색상화 토글. 카메라 보존 + 컨투어 가시화 보장.

        BETA2876 — VTK_POLYHEDRON 셀은 ``cell_quality()`` 가 모두 -1 sentinel 을
        리턴하므로, 그 경우 먼저 ``extract_surface()`` 로 PolyData 표면을 뽑아
        triangle/quad 면 단위 quality 를 계산해 색상을 입힌다. 사용자에게는
        ``_info_label`` 로 fallback 사실을 알려준다.
        """
        if self._plotter is None or self._current_mesh is None:
            return
        cam = self._capture_camera()
        try:
            self._plotter.clear()
            # _render_mesh 와 동일한 ParaView-style 룩.
            try:
                self._plotter.set_background("#3c4046", top="#7a808a")
            except Exception:
                self._plotter.background_color = "#3c4046"
            try:
                self._plotter.show_axes()
            except Exception:
                self._plotter.add_axes(
                    xlabel="X", ylabel="Y", zlabel="Z", line_width=3,
                )
            try:
                self._plotter.enable_parallel_projection()
            except Exception:
                pass

            if checked:
                try:
                    import numpy as _np
                    metric = self._quality_metric
                    metric_info = self._QUALITY_METRICS.get(metric, ("Quality", "Quality"))

                    # 1차: 원본 메시에서 cell_quality 시도 (tet/hex 는 직접 값).
                    qual, scalar_name = _compute_cell_quality_compat(
                        self._current_mesh, metric
                    )
                    surf_for_render = None
                    arr_valid = None

                    def _extract_valid(_q, _name):
                        if _q is None or not _name:
                            return None
                        _a = _q.cell_data.get(_name)
                        if _a is None or len(_a) == 0:
                            return None
                        _a = _np.asarray(_a, dtype=float)
                        _v = _a[(_a > -0.5) & _np.isfinite(_a)]
                        return _v if _v.size > 0 else None

                    arr_valid = _extract_valid(qual, scalar_name)

                    # 2차 fallback: VTK_POLYHEDRON 셀 (poly mesh) → 표면 추출 후
                    # 표면 face 단위 quality 재계산.
                    if arr_valid is None:
                        try:
                            ext = self._current_mesh.extract_surface()  # type: ignore[attr-defined]
                            qual, scalar_name = _compute_cell_quality_compat(ext, metric)
                            arr_valid = _extract_valid(qual, scalar_name)
                            if arr_valid is not None:
                                surf_for_render = qual  # 이미 PolyData
                                try:
                                    self._info_label.setText(
                                        f"ℹ 표면 face 기준 {metric_info[0]} 색상화 (volume "
                                        "polyhedral cells 는 직접 측정 불가)"
                                    )
                                except Exception:
                                    pass
                        except Exception:
                            arr_valid = None

                    if arr_valid is None or arr_valid.size == 0:
                        try:
                            self._info_label.setText(
                                f"⚠ 품질 메트릭 '{metric_info[0]}' 계산 실패 — 메시 형식이 지원되지 않습니다"
                            )
                        except Exception:
                            pass
                        log.warning(
                            f"품질 메트릭 '{metric}' 의 유효 값이 없음 (셀 타입 미지원)"
                        )
                        self._render_mesh(self._current_mesh, camera_view="keep")
                        self._restore_camera(cam)
                        # 토글 상태 풀어줌 — 사용자에게 시각적 피드백.
                        try:
                            self._quality_btn.blockSignals(True)
                            self._quality_btn.setChecked(False)
                            self._quality_btn.blockSignals(False)
                        except Exception:
                            pass
                        return

                    a_valid = arr_valid
                    clim_min = float(_np.percentile(a_valid, 5))
                    clim_max = float(_np.percentile(a_valid, 95))
                    if clim_min >= clim_max:
                        clim_max = clim_min + 1.0

                    if surf_for_render is not None:
                        surf = surf_for_render
                    else:
                        try:
                            surf = qual.extract_surface(
                                algorithm="dataset_surface",
                                pass_cellid=True,
                            )
                        except Exception:
                            surf = qual
                    # 이름 매핑 — extract_surface 후에도 cell_data 에 존재하면 그대로,
                    # 없으면 첫 번째 cell_data array 로 fallback.
                    if scalar_name not in getattr(surf, "cell_data", {}):
                        keys = list(getattr(surf, "cell_data", {}).keys())
                        if keys:
                            scalar_name = keys[0]
                    try:
                        surf.set_active_scalars(scalar_name, preference="cell")
                    except Exception:
                        pass

                    if True:

                        # 셀별 컨투어가 또렷하게 보이도록 lighting OFF + interpolate
                        # before map=False (셀 단위 평면 색상). categorical scalar 가
                        # 아니어도 cell_data 는 셀당 1색으로 매핑된다.
                        self._plotter.add_mesh(
                            surf,
                            scalars=scalar_name,
                            preference="cell",
                            cmap="RdYlGn_r",
                            clim=[clim_min, clim_max],
                            show_edges=self._show_edges,
                            edge_color="#1a1f24" if self._show_edges else None,
                            line_width=0.6,
                            opacity=self._opacity,
                            lighting=False,
                            interpolate_before_map=False,
                            scalar_bar_args={
                                "title": metric_info[0],
                                "color": "#0d1117",
                                "fmt": "%.3g",
                                "n_labels": 5,
                                "shadow": False,
                                "title_font_size": 14,
                                "label_font_size": 12,
                            },
                            name="quality_mesh",
                        )
                        # actor property 보강 — 일부 PyVista 버전이 lighting kwarg 무시.
                        try:
                            actor = self._plotter.actors.get("quality_mesh")
                            if actor is not None:
                                prop = actor.GetProperty()
                                prop.LightingOff()
                                prop.SetInterpolationToFlat()
                        except Exception:
                            pass
                        self._restore_camera(cam)
                        return
                except Exception as e:
                    log.warning(f"품질 색상화 실패, 기본 렌더로 전환: {e}")
            self._render_mesh(self._current_mesh, camera_view="keep")
            self._restore_camera(cam)
        except Exception as e:
            log.error(f"_toggle_quality_color 오류: {e}")
            self._render_mesh(self._current_mesh, camera_view="keep")
            self._restore_camera(cam)

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
        else:
            self._viewer = StaticMeshViewer(self)
            log.warning("정적 PNG 폴백 뷰어 사용 중 (pyvistaqt 미설치)")
        # mesh_ready Signal로 품질 통계 파이프라인 트리거 (두 뷰어 공통)
        if hasattr(self._viewer, "mesh_ready"):
            try:
                self._viewer.mesh_ready.connect(self._compute_and_emit_stats)
            except Exception:
                pass

        layout.addWidget(self._viewer)

        # BC-INTEGRATION / beta2810 — face-pick BC toolbar 를 MeshViewerWidget
        # 에 직접 부착 (Static / Interactive 양쪽 fallback 보장).
        self._bc_ui = None
        try:
            from desktop.qt_app.bc_picker_integration import attach_bc_picker
            plotter = getattr(self._viewer, "_plotter", None)
            if plotter is not None:
                self._bc_ui = attach_bc_picker(
                    plotter, surface_mesh=None, parent=self,
                )
                if self._bc_ui and self._bc_ui.toolbar is not None:
                    layout.addWidget(self._bc_ui.toolbar)
                    log.info("BC face-pick toolbar attached to MeshViewerWidget")
            else:
                log.info("BC toolbar skipped — viewer has no plotter (static fallback)")
        except Exception as _bc_exc:
            log.debug(f"BC toolbar attach skipped: {_bc_exc}")

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

                # 셀 구성 (타입별 개수).
                # foamToVTK가 생성한 internal.vtu는 OpenFOAM polyMesh의 각 cell 을
                # VTK_POLYHEDRON(42) 으로 내보내는 경우가 많다. VTK type 만 보면
                # 전부 polyhedron이 되어 Quality 탭의 Hex/Tet 분류가 비현실적으로
                # 나온다. 따라서 cell 당 point 개수 를 우선 기준으로 재분류한다:
                #   4 pts → Tet, 5 pts → Pyramid, 6 pts → Wedge,
                #   8 pts → Hex, 기타 → Polyhedral.
                hex_types = {12, 25, 29}  # VTK_HEXAHEDRON, VTK_QUADRATIC_HEX, VTK_TRIQUADRATIC_HEX
                tet_types = {10, 24}      # VTK_TETRA, VTK_QUADRATIC_TETRA
                prism_types = {13, 26}    # VTK_WEDGE / VTK_QUADRATIC_WEDGE
                poly_types = {42}         # VTK_POLYHEDRON

                if n_cells > 0 and hasattr(mesh, "celltypes"):
                    import numpy as _np_ct
                    ct_arr = _np_ct.asarray(getattr(mesh, "celltypes", []), dtype=_np_ct.int32)
                    n_hex = n_tet = n_prism = n_poly = 0

                    # vectorized classification for non-polyhedron types
                    mask_tet   = _np_ct.isin(ct_arr, list(tet_types))
                    mask_hex   = _np_ct.isin(ct_arr, list(hex_types))
                    mask_prism = _np_ct.isin(ct_arr, list(prism_types))
                    mask_poly  = _np_ct.isin(ct_arr, list(poly_types))
                    mask_other = ~(mask_tet | mask_hex | mask_prism | mask_poly)

                    n_tet   = int(mask_tet.sum())
                    n_hex   = int(mask_hex.sum())
                    n_prism = int(mask_prism.sum())
                    n_poly  = int(mask_other.sum())  # unknown → polyhedral

                    # VTK_POLYHEDRON — per-cell points 개수로 재분류 (loop 최소화)
                    poly_indices = _np_ct.where(mask_poly)[0]
                    for idx in poly_indices.tolist():
                        try:
                            npts = int(mesh.get_cell(idx).n_points)  # type: ignore[attr-defined]
                        except Exception:
                            npts = 0
                        if npts == 4:
                            n_tet += 1
                        elif npts == 8:
                            n_hex += 1
                        elif npts == 6:
                            n_prism += 1
                        else:
                            n_poly += 1

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
            # pyvista >= 0.45: compute_cell_quality() deprecated → cell_quality() 사용
            if n_cells > 0 and n_cells <= 500_000:
                import numpy as _np

                def _cell_quality_array(m: object, measure: str) -> "_np.ndarray | None":
                    """모듈 레벨 _compute_cell_quality_compat 위임 (deprecation 안전)."""
                    qual, name = _compute_cell_quality_compat(m, measure)
                    if qual is None or not name:
                        return None
                    arr = qual.cell_data.get(name)
                    if arr is None or len(arr) == 0:
                        return None
                    arr = _np.asarray(arr, dtype=float)
                    return arr[_np.isfinite(arr)] if len(arr) > 0 else None

                # BETA2874 — PyVista cell_quality() 가 VTK_POLYHEDRON (type 42)
                # cell 에 대해 quality measure 미지원 → -1.0 sentinel 반환.
                # cfMesh 출력은 모두 polyhedron 으로 export 되므로 max=-1 가
                # GUI Quality 탭을 덮어씀. 음수/-1 sentinel 필터링.
                def _valid_quality_arr(a):
                    if a is None or len(a) == 0:
                        return None
                    a = a[(a > -0.5) & _np.isfinite(a)]
                    return a if len(a) > 0 else None

                arr = _valid_quality_arr(_cell_quality_array(mesh, "aspect_ratio"))
                if arr is not None:
                    stats["max_aspect_ratio"] = float(arr.max())
                    stats["mean_aspect_ratio"] = float(arr.mean())
                    stats["hist_aspect_ratio"] = arr.tolist()

                arr = _valid_quality_arr(_cell_quality_array(mesh, "skew"))
                if arr is not None:
                    stats["max_skewness"] = float(arr.max())
                    stats["mean_skewness"] = float(arr.mean())
                    stats["hist_skewness"] = arr.tolist()

                arr = _valid_quality_arr(_cell_quality_array(mesh, "max_angle"))
                if arr is not None:
                    stats["max_non_orthogonality"] = float(arr.max())
                    stats["mean_non_orthogonality"] = float(arr.mean())
                    stats["hist_non_orthogonality"] = arr.tolist()

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
