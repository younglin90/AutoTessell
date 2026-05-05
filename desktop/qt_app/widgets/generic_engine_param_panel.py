"""Spec-driven 엔진 파라미터 패널.

`EngineParamSpec` 리스트를 받아 각 파라미터별로 자동 UI 생성:
  - float  → QSlider (log_scale 옵션) + 값 라벨
  - int    → QSlider + 값 라벨
  - bool   → QCheckBox
  - choice → QComboBox
  - str    → QLineEdit

각 행 앞에 ⓘ 버튼 — 클릭 시 QMessageBox 팝업으로 상세 설명.
값 변경 시 params_changed Signal emit.
"""
from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from desktop.qt_app.widgets.engine_params_spec import (
    ENGINE_PARAM_REGISTRY,
    EngineParamSpec,
    get_specs_for_engine,
    resolve_engine_key,
)

_SLIDER_STEPS = 1000  # float slider 분해능


def _info_button(spec: EngineParamSpec) -> QPushButton:
    btn = QPushButton("ⓘ")
    btn.setFixedSize(18, 18)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setToolTip(f"{spec.label} 상세 설명")
    btn.setStyleSheet(
        "QPushButton { background: transparent; border: none; "
        "color: #818a99; font-size: 13px; padding: 0; }"
        "QPushButton:hover { color: #4ea3ff; }"
    )

    def _popup() -> None:
        msg = QMessageBox()
        msg.setWindowTitle(f"{spec.label}")
        msg.setText(f"<b>{spec.label}</b>  <code>({spec.key})</code>")
        body = spec.doc.strip() or "(추가 설명 없음)"
        body += f"\n\n기본값: {spec.default}"
        if spec.kind in ("float", "int") and spec.min_val is not None:
            body += f"\n범위: [{spec.min_val}, {spec.max_val}]"
            if spec.log_scale:
                body += " (log-scale)"
        if spec.kind == "choice":
            options = ", ".join(v for v, _ in spec.choices)
            body += f"\n선택지: {options}"
        msg.setInformativeText(body)
        msg.setStyleSheet(
            "QMessageBox { background: #101318; color: #e8ecf2; }"
            "QMessageBox QLabel { color: #e8ecf2; }"
            "QMessageBox QPushButton { "
            "  background: #1c2129; color: #b6bdc9; "
            "  border: 1px solid #323a46; border-radius: 3px; "
            "  padding: 4px 16px; min-width: 60px; }"
            "QMessageBox QPushButton:hover { "
            "  border-color: #4ea3ff; color: #e8ecf2; }"
        )
        msg.exec()

    btn.clicked.connect(_popup)
    return btn


def _dark_combo_style() -> str:
    return (
        "QComboBox { background: #161a20; color: #e8ecf2; "
        "border: 1px solid #323a46; border-radius: 4px; padding: 3px 8px; "
        "font-size: 11px; min-height: 24px; }"
        "QComboBox:hover { border-color: #4ea3ff; }"
        "QComboBox::drop-down { border: none; width: 20px; }"
        "QComboBox QAbstractItemView { background: #161a20; color: #e8ecf2; "
        "selection-background-color: #2c5f97; selection-color: #e8ecf2; "
        "border: 1px solid #323a46; outline: none; padding: 2px; }"
    )


def _dark_lineedit_style() -> str:
    return (
        "QLineEdit { background: #161a20; color: #e8ecf2; "
        "border: 1px solid #323a46; border-radius: 4px; padding: 3px 8px; "
        "font-size: 11px; min-height: 22px; }"
        "QLineEdit:focus { border-color: #4ea3ff; }"
    )


def _slider_style() -> str:
    return (
        "QSlider::groove:horizontal { background: #323a46; height: 4px; border-radius: 2px; }"
        "QSlider::handle:horizontal { background: #4ea3ff; width: 14px; margin: -5px 0; "
        "border-radius: 7px; }"
        "QSlider::sub-page:horizontal { background: #4ea3ff; border-radius: 2px; }"
    )


class GenericEngineParamPanel(QFrame):
    """임의의 spec 리스트로 파라미터 UI 자동 생성."""

    params_changed = Signal(dict)

    def __init__(self, engine_key: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "GenericEngineParamPanel { "
            "background: transparent; "
            "border: 1px solid #323a46; border-radius: 5px; "
            "}"
        )
        self._engine_key: str = ""
        self._specs: list[EngineParamSpec] = []
        # key → (widget, read_fn, write_fn)
        self._controls: dict[str, tuple[QWidget, Any, Any]] = {}

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(10, 10, 10, 10)
        self._root.setSpacing(6)

        self._title = QLabel("엔진 파라미터")
        self._title.setStyleSheet(
            "color: #e8ecf2; font-size: 11px; font-weight: 600; "
            "background: transparent; padding: 0;"
        )
        self._root.addWidget(self._title)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._inner = QWidget()
        self._inner.setStyleSheet("background: transparent;")
        self._form = QVBoxLayout(self._inner)
        self._form.setContentsMargins(0, 4, 0, 4)
        self._form.setSpacing(4)
        self._inner.setLayout(self._form)
        self._scroll.setWidget(self._inner)
        self._scroll.setMinimumHeight(160)
        self._root.addWidget(self._scroll)

        self._empty_label = QLabel("(이 엔진은 추가 튜닝 파라미터가 없습니다)")
        self._empty_label.setStyleSheet(
            "color: #818a99; font-size: 10.5px; "
            "background: transparent; padding: 6px; font-style: italic;"
        )
        self._empty_label.setVisible(False)
        self._root.addWidget(self._empty_label)

        if engine_key:
            self.set_engine(engine_key)

    # ------------------------------------------------------------------

    def set_engine(self, engine_key: str) -> None:
        """엔진 선택 변경 — spec 교체 후 UI 재생성."""
        resolved = resolve_engine_key(engine_key)
        specs = get_specs_for_engine(resolved)
        self._engine_key = resolved
        self._specs = specs

        # 기존 위젯 제거
        while self._form.count():
            item = self._form.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._controls.clear()

        self._title.setText(f"🔧 {resolved} 파라미터")
        self._empty_label.setVisible(not specs)
        if not specs:
            # (참고: wildmesh/polyhedral 은 별도 panel 로 처리됨)
            return

        # spec 종류별 그룹핑
        numeric_specs = [s for s in specs if s.kind in ("float", "int")]
        flag_specs    = [s for s in specs if s.kind == "bool"]
        choice_specs  = [s for s in specs if s.kind == "choice"]
        text_specs    = [s for s in specs if s.kind == "str"]

        if numeric_specs:
            self._section_header("수치 파라미터")
            for spec in numeric_specs:
                self._add_numeric_row(spec)
        if choice_specs:
            self._section_header("선택")
            for spec in choice_specs:
                self._add_choice_row(spec)
        if flag_specs:
            self._section_header("플래그")
            for spec in flag_specs:
                self._add_checkbox_row(spec)
        if text_specs:
            self._section_header("문자열")
            for spec in text_specs:
                self._add_text_row(spec)

        self._emit_params()

    def _section_header(self, text: str) -> None:
        h = QLabel(text)
        h.setStyleSheet(
            "color: #818a99; font-size: 10px; font-weight: 600; "
            "letter-spacing: 1px; background: transparent; padding: 4px 0 2px 0;"
        )
        self._form.addWidget(h)

    # ------------------------------------------------------------------
    # 행 생성
    # ------------------------------------------------------------------

    def _row_container(self, spec: EngineParamSpec) -> QHBoxLayout:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(_info_button(spec))
        lbl = QLabel(spec.label)
        lbl.setFixedWidth(140)
        lbl.setStyleSheet(
            "color: #b6bdc9; font-size: 11px; background: transparent;"
        )
        if spec.doc:
            lbl.setToolTip(spec.doc.split("\n\n")[0])
        layout.addWidget(lbl)
        self._form.addWidget(row)
        return layout

    def _add_numeric_row(self, spec: EngineParamSpec) -> None:
        layout = self._row_container(spec)
        slider = QSlider(Qt.Horizontal)
        slider.setStyleSheet(_slider_style())
        if spec.doc:
            slider.setToolTip(spec.doc.split("\n\n")[0])

        min_v = float(spec.min_val if spec.min_val is not None else 0.0)
        max_v = float(spec.max_val if spec.max_val is not None else 1.0)

        if spec.kind == "int":
            # 정수 슬라이더 — 범위 그대로
            slider.setRange(int(min_v), int(max_v))
            slider.setValue(int(spec.default))
            value_lbl = QLabel(str(int(spec.default)))

            def read() -> Any:
                return int(slider.value())

            def write(value: Any) -> None:
                try:
                    v = int(float(value))
                except Exception:
                    return
                slider.blockSignals(True)
                try:
                    slider.setValue(v)
                finally:
                    slider.blockSignals(False)
                value_lbl.setText(str(v))

            def on_change(v: int) -> None:
                value_lbl.setText(str(v))
                self._emit_params()

            slider.valueChanged.connect(on_change)
        else:  # float
            slider.setRange(0, _SLIDER_STEPS)
            fmt = self._float_formatter(spec)

            def to_slider(val: float) -> int:
                return _float_to_slider(val, min_v, max_v, spec.log_scale)

            def to_value(s: int) -> float:
                return _slider_to_float(s, min_v, max_v, spec.log_scale)

            slider.setValue(to_slider(float(spec.default)))
            value_lbl = QLabel(fmt(float(spec.default)))

            def read() -> Any:
                return to_value(slider.value())

            def write(value: Any) -> None:
                try:
                    v = float(value)
                except Exception:
                    return
                slider.blockSignals(True)
                try:
                    slider.setValue(to_slider(v))
                finally:
                    slider.blockSignals(False)
                value_lbl.setText(fmt(v))

            def on_change(_s: int) -> None:
                value_lbl.setText(fmt(to_value(_s)))
                self._emit_params()

            slider.valueChanged.connect(on_change)

        value_lbl.setFixedWidth(60)
        value_lbl.setAlignment(Qt.AlignRight)
        value_lbl.setStyleSheet(
            "color: #e8ecf2; font-size: 11px; font-weight: 500; "
            "font-family: 'JetBrains Mono', monospace; background: transparent;"
        )
        layout.addWidget(slider, stretch=1)
        layout.addWidget(value_lbl)

        self._controls[spec.key] = (slider, read, write)

    def _add_checkbox_row(self, spec: EngineParamSpec) -> None:
        # row_container 이미 info + label 붙였지만 QCheckBox는 자체 라벨 있음.
        # → 별도 구조: info + checkbox (라벨은 checkbox 자체)
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(_info_button(spec))
        cb = QCheckBox(spec.label)
        cb.setChecked(bool(spec.default))
        cb.setStyleSheet(
            "QCheckBox { color: #b6bdc9; font-size: 11px; background: transparent; }"
            "QCheckBox::indicator { width: 14px; height: 14px; }"
            "QCheckBox::indicator:unchecked { "
            "  background: #161a20; border: 1px solid #323a46; border-radius: 2px; }"
            "QCheckBox::indicator:checked { "
            "  background: #4ea3ff; border: 1px solid #4ea3ff; border-radius: 2px; }"
        )
        if spec.doc:
            cb.setToolTip(spec.doc.split("\n\n")[0])
        cb.toggled.connect(lambda _v: self._emit_params())
        layout.addWidget(cb)
        layout.addStretch()
        self._form.addWidget(row)

        def read() -> Any:
            return bool(cb.isChecked())

        def write(value: Any) -> None:
            cb.blockSignals(True)
            try:
                cb.setChecked(bool(value))
            finally:
                cb.blockSignals(False)

        self._controls[spec.key] = (cb, read, write)

    def _add_choice_row(self, spec: EngineParamSpec) -> None:
        layout = self._row_container(spec)
        combo = QComboBox()
        combo.setStyleSheet(_dark_combo_style())
        for value, display in spec.choices:
            combo.addItem(display, value)
        # default 매칭
        for i in range(combo.count()):
            if str(combo.itemData(i)) == str(spec.default):
                combo.setCurrentIndex(i)
                break
        combo.currentIndexChanged.connect(lambda _i: self._emit_params())
        layout.addWidget(combo, stretch=1)

        def read() -> Any:
            return str(combo.currentData() if combo.currentData() is not None else spec.default)

        def write(value: Any) -> None:
            s = str(value)
            for i in range(combo.count()):
                if str(combo.itemData(i)) == s:
                    combo.blockSignals(True)
                    try:
                        combo.setCurrentIndex(i)
                    finally:
                        combo.blockSignals(False)
                    return

        self._controls[spec.key] = (combo, read, write)

    def _add_text_row(self, spec: EngineParamSpec) -> None:
        layout = self._row_container(spec)
        edit = QLineEdit()
        edit.setStyleSheet(_dark_lineedit_style())
        edit.setText(str(spec.default))
        edit.textChanged.connect(lambda _t: self._emit_params())
        layout.addWidget(edit, stretch=1)

        def read() -> Any:
            return edit.text()

        def write(value: Any) -> None:
            edit.blockSignals(True)
            try:
                edit.setText(str(value))
            finally:
                edit.blockSignals(False)

        self._controls[spec.key] = (edit, read, write)

    # ------------------------------------------------------------------
    # 값 읽기/쓰기
    # ------------------------------------------------------------------

    def current_params(self) -> dict:
        out: dict = {}
        for key, (_w, read, _write) in self._controls.items():
            try:
                out[key] = read()
            except Exception:
                pass
        return out

    def set_params(self, params: dict) -> None:
        if not params:
            return
        for key, (_w, _r, write) in self._controls.items():
            if key in params:
                try:
                    write(params[key])
                except Exception:
                    pass
        self._emit_params()

    def _emit_params(self) -> None:
        self.params_changed.emit(self.current_params())

    # ------------------------------------------------------------------

    def _float_formatter(self, spec: EngineParamSpec):
        """범위 크기에 따라 자릿수 결정."""
        rng = float((spec.max_val or 1.0) - (spec.min_val or 0.0))
        if spec.log_scale or rng < 0.1:
            return lambda v: f"{v:.4g}"
        if rng < 10:
            return lambda v: f"{v:.3g}"
        return lambda v: f"{v:.2f}" if isinstance(v, float) else f"{v}"


# ---------------------------------------------------------------------------
# float ↔ slider 변환 유틸
# ---------------------------------------------------------------------------


def _float_to_slider(val: float, vmin: float, vmax: float, log: bool) -> int:
    val = max(vmin, min(vmax, val))
    if log:
        # log scale — 양수 범위만
        a = max(1e-12, vmin)
        b = max(a * 10, vmax)
        ratio = (math.log10(max(a, val)) - math.log10(a)) / (math.log10(b) - math.log10(a))
    else:
        span = vmax - vmin if vmax > vmin else 1.0
        ratio = (val - vmin) / span
    return int(max(0, min(_SLIDER_STEPS, ratio * _SLIDER_STEPS)))


def _slider_to_float(s: int, vmin: float, vmax: float, log: bool) -> float:
    ratio = s / _SLIDER_STEPS
    if log:
        a = max(1e-12, vmin)
        b = max(a * 10, vmax)
        return 10 ** (math.log10(a) + ratio * (math.log10(b) - math.log10(a)))
    return vmin + ratio * (vmax - vmin)
