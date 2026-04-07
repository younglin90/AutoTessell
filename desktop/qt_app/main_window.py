"""AutoTessell 메인 윈도우 — PySide6 + PyVistaQt.

헤드리스 환경에서도 클래스 정의만은 import 가능하도록
Qt 위젯 클래스를 최상위 스코프에서 직접 참조하지 않는다.
실제 위젯 생성은 __init__ 내부에서만 수행한다.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # 타입 힌트 전용 임포트 (런타임 불필요)

# ---------------------------------------------------------------------------
# QualityLevel enum — Qt 없이도 사용 가능
# ---------------------------------------------------------------------------


class QualityLevel(str, Enum):
    DRAFT = "draft"
    STANDARD = "standard"
    FINE = "fine"


# ---------------------------------------------------------------------------
# AutoTessellWindow
# ---------------------------------------------------------------------------


class AutoTessellWindow:  # type: ignore[misc]
    """PySide6 QMainWindow 기반 메인 윈도우.

    헤드리스 환경에서 임포트만 할 경우를 위해 QMainWindow 상속은
    인스턴스화 시점까지 지연한다.
    실제 GUI 환경에서는 _build() 를 호출해 완전한 위젯 트리를 구성한다.
    """

    #: 지원하는 파일 확장자
    SUPPORTED_EXTENSIONS: tuple[str, ...] = (
        ".stl", ".obj", ".ply", ".off", ".3mf",
        ".step", ".stp", ".iges", ".igs", ".brep",
        ".msh", ".vtu", ".vtk",
    )

    def __init__(self) -> None:
        self._input_path: Path | None = None
        self._quality_level: QualityLevel = QualityLevel.DRAFT
        self._worker: object | None = None  # PipelineWorker (lazy)

        # Qt 위젯 속성 — _build() 호출 후 설정됨
        self._plotter: object | None = None
        self._log_edit: object | None = None
        self._quality_combo: object | None = None
        self._drop_label: object | None = None
        self._run_btn: object | None = None

    # ------------------------------------------------------------------
    # Public API (Qt 없이도 호출 가능)
    # ------------------------------------------------------------------

    def set_input_path(self, path: str | Path) -> None:
        """드래그앤드롭 또는 파일 다이얼로그로 입력 파일을 설정한다."""
        resolved = Path(path).expanduser().resolve()
        if resolved.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"지원하지 않는 파일 형식: {resolved.suffix!r}. "
                f"지원 형식: {self.SUPPORTED_EXTENSIONS}"
            )
        self._input_path = resolved

    def get_input_path(self) -> Path | None:
        """현재 설정된 입력 파일 경로를 반환한다."""
        return self._input_path

    def set_quality_level(self, level: QualityLevel | str) -> None:
        """품질 레벨을 설정한다."""
        self._quality_level = QualityLevel(level)

    def get_quality_level(self) -> QualityLevel:
        """현재 품질 레벨을 반환한다."""
        return self._quality_level

    # ------------------------------------------------------------------
    # Qt 의존 초기화 — QApplication 존재 시에만 호출한다
    # ------------------------------------------------------------------

    def _build(self) -> None:  # pragma: no cover
        """Qt 위젯 트리를 구성한다. QApplication 생성 후 호출해야 한다."""
        from PySide6.QtWidgets import (
            QMainWindow,
            QWidget,
            QHBoxLayout,
            QVBoxLayout,
            QLabel,
            QComboBox,
            QPushButton,
            QPlainTextEdit,
            QSizePolicy,
        )
        from PySide6.QtCore import Qt

        # QMainWindow를 동적으로 상속하는 대신 인스턴스를 합성(composition)
        self._qmain = QMainWindow()
        self._qmain.setWindowTitle("AutoTessell v2")
        self._qmain.resize(1400, 800)

        central = QWidget()
        self._qmain.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        # --- 상단: 3-열 패널 ---
        top = QWidget()
        top_layout = QHBoxLayout(top)
        root_layout.addWidget(top, stretch=1)

        # 좌: 드래그앤드롭 패널
        self._drop_label = QLabel("파일을 여기에 드래그하세요\n(STL / STEP / OBJ …)")
        self._drop_label.setAlignment(Qt.AlignCenter)
        self._drop_label.setAcceptDrops(True)
        self._drop_label.setMinimumWidth(200)
        self._drop_label.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Expanding
        )
        self._drop_label.setStyleSheet(
            "border: 2px dashed #888; border-radius: 8px; padding: 12px;"
        )
        self._drop_label.dragEnterEvent = self._on_drag_enter  # type: ignore[assignment]
        self._drop_label.dropEvent = self._on_drop  # type: ignore[assignment]
        top_layout.addWidget(self._drop_label, stretch=1)

        # 중: PyVistaQt 3D 뷰어
        try:
            from pyvistaqt import BackgroundPlotter

            self._plotter = BackgroundPlotter(show=False)
            top_layout.addWidget(self._plotter.app_window, stretch=4)
        except Exception:  # pyvistaqt 없거나 헤드리스
            placeholder = QLabel("3D 뷰어 (pyvistaqt 필요)")
            placeholder.setAlignment(Qt.AlignCenter)
            top_layout.addWidget(placeholder, stretch=4)

        # 우: 컨트롤 패널
        ctrl = QWidget()
        ctrl_layout = QVBoxLayout(ctrl)
        ctrl_layout.addWidget(QLabel("품질 레벨"))
        self._quality_combo = QComboBox()
        for lvl in QualityLevel:
            self._quality_combo.addItem(lvl.value)
        ctrl_layout.addWidget(self._quality_combo)
        self._run_btn = QPushButton("메쉬 생성")
        self._run_btn.clicked.connect(self._on_run_clicked)
        ctrl_layout.addWidget(self._run_btn)
        ctrl_layout.addStretch()
        ctrl.setMinimumWidth(160)
        top_layout.addWidget(ctrl, stretch=1)

        # 하: 진행 로그
        self._log_edit = QPlainTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setMaximumHeight(180)
        root_layout.addWidget(self._log_edit)

    def show(self) -> None:  # pragma: no cover
        """윈도우를 화면에 표시한다."""
        if not hasattr(self, "_qmain"):
            self._build()
        self._qmain.show()

    # ------------------------------------------------------------------
    # 내부 이벤트 핸들러
    # ------------------------------------------------------------------

    def _on_drag_enter(self, event: object) -> None:  # pragma: no cover
        from PySide6.QtCore import Qt

        mime = event.mimeData()  # type: ignore[attr-defined]
        if mime.hasUrls():
            event.acceptProposedAction()  # type: ignore[attr-defined]

    def _on_drop(self, event: object) -> None:  # pragma: no cover
        mime = event.mimeData()  # type: ignore[attr-defined]
        if mime.hasUrls():
            path = mime.urls()[0].toLocalFile()
            try:
                self.set_input_path(path)
                if self._drop_label is not None:
                    self._drop_label.setText(f"입력: {Path(path).name}")  # type: ignore[union-attr]
                self._append_log(f"파일 설정: {path}")
            except ValueError as e:
                self._append_log(f"[오류] {e}")

    def _on_run_clicked(self) -> None:  # pragma: no cover
        from desktop.qt_app.pipeline_worker import PipelineWorker

        if self._input_path is None:
            self._append_log("[오류] 입력 파일을 먼저 선택하세요.")
            return

        if self._quality_combo is not None:
            self._quality_level = QualityLevel(self._quality_combo.currentText())  # type: ignore[union-attr]

        if self._run_btn is not None:
            self._run_btn.setEnabled(False)  # type: ignore[union-attr]

        self._worker = PipelineWorker(self._input_path, self._quality_level)
        self._worker.progress.connect(self._append_log)  # type: ignore[union-attr]
        self._worker.finished.connect(self._on_pipeline_finished)  # type: ignore[union-attr]
        self._worker.start()  # type: ignore[union-attr]

    def _on_pipeline_finished(self, result: object) -> None:  # pragma: no cover
        if self._run_btn is not None:
            self._run_btn.setEnabled(True)  # type: ignore[union-attr]
        success = getattr(result, "success", False)
        self._append_log(
            f"[완료] {'성공' if success else '실패'} — "
            f"소요: {getattr(result, 'total_time_seconds', 0):.1f}s"
        )

    def _append_log(self, message: str) -> None:  # pragma: no cover
        if self._log_edit is not None:
            self._log_edit.appendPlainText(message)  # type: ignore[union-attr]
