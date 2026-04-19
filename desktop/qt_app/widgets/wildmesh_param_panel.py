"""WildMesh 파라미터 슬라이더 패널.

사이드바에서 엔진=wildmesh 선택 시 표시되는 실시간 튜닝 UI:
- epsilon (log-scale 0.0001 ~ 0.1)
- edge_length_r (linear 0.005 ~ 0.2)
- stop_quality (linear 3 ~ 100)
- max_its (linear 10 ~ 500)
- 3종 프리셋 버튼 (Draft / Standard / Fine)

값 변경 시 `params_changed` Signal emit → main_window가 tier_specific_params로 변환.
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


# 각 프리셋별 (epsilon, edge_length_r, stop_quality, max_its)
PRESETS: dict[str, dict[str, float]] = {
    "draft":    {"epsilon": 0.002,  "edge_length_r": 0.06, "stop_quality": 20.0, "max_its": 40},
    "standard": {"epsilon": 0.001,  "edge_length_r": 0.04, "stop_quality": 10.0, "max_its": 80},
    "fine":     {"epsilon": 0.0003, "edge_length_r": 0.02, "stop_quality": 5.0,  "max_its": 200},
}


class WildMeshParamPanel(QFrame):
    """4개 슬라이더 + 프리셋 버튼. 실시간 파라미터 변경 Signal."""

    # 변경된 파라미터 dict (wildmesh_* 키로 emit)
    params_changed = Signal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "WildMeshParamPanel { "
            "background: transparent; "
            "border: 1px solid #323a46; border-radius: 5px; "
            "}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        title = QLabel("🔧 WildMesh 파라미터")
        title.setStyleSheet(
            "color: #e8ecf2; font-size: 11px; font-weight: 600; "
            "background: transparent; padding: 0;"
        )
        root.addWidget(title)

        # 프리셋 버튼 3개
        preset_row = QHBoxLayout()
        preset_row.setSpacing(4)
        for name in ("draft", "standard", "fine"):
            btn = QPushButton(name.capitalize())
            btn.setStyleSheet(
                "QPushButton { background: #1c2129; color: #b6bdc9; "
                "border: 1px solid #323a46; border-radius: 3px; "
                "padding: 4px 10px; font-size: 11px; }"
                "QPushButton:hover { border-color: #4ea3ff; color: #e8ecf2; }"
            )
            btn.clicked.connect(lambda _checked=False, n=name: self.apply_preset(n))
            preset_row.addWidget(btn)
        preset_row.addStretch()
        root.addLayout(preset_row)

        # 슬라이더 4개
        # epsilon: log scale 0.0001(1e-4) ~ 0.1(1e-1) → slider 0~1000
        self._eps_slider, self._eps_label = self._make_slider_row(
            root, "epsilon (envelope)", 0, 1000,
            fmt=lambda v: f"{self._slider_to_eps(v):.4f}",
            tooltip="작을수록 형상 보존 정확, 클수록 빠름. 0.0001 ~ 0.1",
        )
        self._edge_slider, self._edge_label = self._make_slider_row(
            root, "edge_length_r", 5, 200,  # 0.005 ~ 0.2 (x0.001)
            fmt=lambda v: f"{v / 1000:.3f}",
            tooltip="bbox 대비 엣지 비율. 작을수록 고해상도",
        )
        self._quality_slider, self._quality_label = self._make_slider_row(
            root, "stop_quality", 3, 100,
            fmt=lambda v: f"{v}",
            tooltip="목표 품질. 낮을수록 고품질 (수렴 오래 걸림)",
        )
        self._its_slider, self._its_label = self._make_slider_row(
            root, "max_iterations", 10, 500,
            fmt=lambda v: f"{v}",
            tooltip="최대 최적화 반복 횟수",
        )

        # 초기값 — draft
        self.apply_preset("draft")

    # ------------------------------------------------------------------

    def _make_slider_row(
        self,
        parent_layout,
        name: str,
        min_val: int,
        max_val: int,
        fmt,
        tooltip: str = "",
    ) -> tuple[QSlider, QLabel]:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        name_lbl = QLabel(name)
        name_lbl.setFixedWidth(120)
        name_lbl.setStyleSheet(
            "color: #b6bdc9; font-size: 11px; background: transparent;"
        )
        if tooltip:
            name_lbl.setToolTip(tooltip)
        layout.addWidget(name_lbl)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setStyleSheet(
            "QSlider::groove:horizontal { background: #323a46; height: 4px; border-radius: 2px; }"
            "QSlider::handle:horizontal { background: #4ea3ff; width: 14px; margin: -5px 0; "
            "border-radius: 7px; }"
            "QSlider::sub-page:horizontal { background: #4ea3ff; border-radius: 2px; }"
        )
        if tooltip:
            slider.setToolTip(tooltip)
        layout.addWidget(slider, stretch=1)

        value_lbl = QLabel("—")
        value_lbl.setFixedWidth(54)
        value_lbl.setAlignment(Qt.AlignRight)
        value_lbl.setStyleSheet(
            "color: #e8ecf2; font-size: 11px; font-weight: 500; "
            "font-family: 'JetBrains Mono', monospace; background: transparent;"
        )
        layout.addWidget(value_lbl)

        # 변경 핸들러
        def _on_change(v: int) -> None:
            value_lbl.setText(fmt(v))
            self._emit_params()

        slider.valueChanged.connect(_on_change)
        parent_layout.addWidget(row)
        return slider, value_lbl

    # ------------------------------------------------------------------
    # epsilon log scale 변환: slider(0~1000) ↔ value(0.0001~0.1)
    @staticmethod
    def _eps_to_slider(eps: float) -> int:
        # 1e-4 ~ 1e-1 (3 decades) → 0~1000
        log_eps = math.log10(max(1e-4, min(1e-1, eps)))
        return int((log_eps - (-4)) / 3 * 1000)

    @staticmethod
    def _slider_to_eps(slider_val: int) -> float:
        log_eps = -4 + (slider_val / 1000) * 3
        return 10 ** log_eps

    # ------------------------------------------------------------------

    def apply_preset(self, name: str) -> None:
        """프리셋 이름(draft/standard/fine) 로 슬라이더 세팅."""
        p = PRESETS.get(name)
        if not p:
            return
        # 슬라이더 일괄 설정 (각 valueChanged가 emit하지만 최종 emit은 공통)
        self._eps_slider.blockSignals(True)
        self._edge_slider.blockSignals(True)
        self._quality_slider.blockSignals(True)
        self._its_slider.blockSignals(True)
        try:
            self._eps_slider.setValue(self._eps_to_slider(p["epsilon"]))
            self._edge_slider.setValue(int(p["edge_length_r"] * 1000))
            self._quality_slider.setValue(int(p["stop_quality"]))
            self._its_slider.setValue(int(p["max_its"]))
        finally:
            self._eps_slider.blockSignals(False)
            self._edge_slider.blockSignals(False)
            self._quality_slider.blockSignals(False)
            self._its_slider.blockSignals(False)
        # 라벨 수동 갱신
        self._eps_label.setText(f"{p['epsilon']:.4f}")
        self._edge_label.setText(f"{p['edge_length_r']:.3f}")
        self._quality_label.setText(f"{int(p['stop_quality'])}")
        self._its_label.setText(f"{int(p['max_its'])}")
        self._emit_params()

    def current_params(self) -> dict:
        """현재 슬라이더 값을 wildmesh_* 키의 dict로 반환."""
        return {
            "wildmesh_epsilon": self._slider_to_eps(self._eps_slider.value()),
            "wildmesh_edge_length_r": self._edge_slider.value() / 1000.0,
            "wildmesh_stop_quality": float(self._quality_slider.value()),
            "wildmesh_max_its": int(self._its_slider.value()),
        }

    def set_params(self, params: dict) -> None:
        """외부에서 params dict를 세팅 (ex: param_history.pop)."""
        if not params:
            return
        self._eps_slider.blockSignals(True)
        self._edge_slider.blockSignals(True)
        self._quality_slider.blockSignals(True)
        self._its_slider.blockSignals(True)
        try:
            if "wildmesh_epsilon" in params:
                self._eps_slider.setValue(
                    self._eps_to_slider(float(params["wildmesh_epsilon"]))
                )
            if "wildmesh_edge_length_r" in params:
                self._edge_slider.setValue(
                    int(float(params["wildmesh_edge_length_r"]) * 1000)
                )
            if "wildmesh_stop_quality" in params:
                self._quality_slider.setValue(
                    int(float(params["wildmesh_stop_quality"]))
                )
            if "wildmesh_max_its" in params:
                self._its_slider.setValue(int(params["wildmesh_max_its"]))
        finally:
            self._eps_slider.blockSignals(False)
            self._edge_slider.blockSignals(False)
            self._quality_slider.blockSignals(False)
            self._its_slider.blockSignals(False)
        # 라벨 수동 갱신
        cur = self.current_params()
        self._eps_label.setText(f"{cur['wildmesh_epsilon']:.4f}")
        self._edge_label.setText(f"{cur['wildmesh_edge_length_r']:.3f}")
        self._quality_label.setText(f"{int(cur['wildmesh_stop_quality'])}")
        self._its_label.setText(f"{int(cur['wildmesh_max_its'])}")
        self._emit_params()

    def _emit_params(self) -> None:
        self.params_changed.emit(self.current_params())
