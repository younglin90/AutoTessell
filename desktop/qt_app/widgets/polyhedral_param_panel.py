"""polyDualMesh 파라미터 패널.

사이드바에서 엔진 = polyhedral 선택 시 표시.

수치 파라미터:
  - feature_angle  (0~180°)

플래그 파라미터:
  - concave_multi_cells      (권장 ON)
  - split_all_faces
  - preserve_face_zones      (기본 ON)
  - overwrite                (내부용, 기본 ON)

선행 tet precursor 선택:
  - precursor_engine : auto / wildmesh / tetwild / meshpy

각 파라미터 옆 ⓘ 버튼 클릭 시 QMessageBox 로 상세 설명 표시.
변경 시 params_changed Signal emit (`polyhedral_*` 키).
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)


# 프리셋 — 선행 tet 의 edge_length_r 가 셀 크기를 지배한다.
# feature_angle 은 보존할 feature 각도일 뿐 셀 크기와 무관하다는 점에 주의.
PRESETS: dict[str, dict[str, object]] = {
    "draft":    {
        "feature_angle": 45.0,
        "precursor_edge_length_r": 0.06,
        "precursor_epsilon": 2e-3,
        "concave_multi_cells": True,
        "split_all_faces": False,
        "preserve_face_zones": True,
        "precursor_engine": "auto",
    },
    "standard": {
        "feature_angle": 30.0,
        "precursor_edge_length_r": 0.04,   # 조밀 ↓
        "precursor_epsilon": 1e-3,
        "concave_multi_cells": True,
        "split_all_faces": False,
        "preserve_face_zones": True,
        "precursor_engine": "auto",
    },
    "fine":     {
        "feature_angle": 15.0,
        "precursor_edge_length_r": 0.025,  # 매우 조밀
        "precursor_epsilon": 5e-4,
        "concave_multi_cells": True,
        "split_all_faces": True,
        "preserve_face_zones": True,
        "precursor_engine": "tetwild",
    },
}


PARAM_DOCS: dict[str, dict[str, str]] = {
    "feature_angle": {
        "title": "feature_angle — 형상 feature 보존 각도 (※ 셀 크기와 무관)",
        "body": (
            "⚠ 셀 크기를 조절하는 파라미터가 아닙니다.\n"
            "셀 크기는 아래 'precursor_edge_length_r' 로 조정하세요.\n\n"
            "feature_angle 은 dual 변환 시 원본 mesh 의 feature edge 를 보존할\n"
            "각도 임계값 (degree). 인접 두 face 법선의 사이 각이 이 값을 넘으면\n"
            "feature 로 간주한다.\n\n"
            "작을수록 (0~20°):\n"
            "  • 날카로운 모서리 엄격히 보존 (cube 각 뚜렷)\n"
            "  • feature point 에서 degenerate poly cell 위험\n\n"
            "중간 (30~60°, 권장):\n"
            "  • 주요 edge 만 보존, sliver 최소화\n"
            "  • 실측 sweet spot\n\n"
            "클수록 (60~180°):\n"
            "  • feature 대부분 무시 — 매끈한 poly\n"
            "  • 형상 충실도 하락"
        ),
    },
    "precursor_edge_length_r": {
        "title": "precursor_edge_length_r — 선행 tet 조밀도 (★ 셀 크기 제어)",
        "body": (
            "polyDualMesh 는 먼저 tet mesh 를 만든 뒤 그 dual 을 취한다.\n"
            "따라서 최종 poly cell 의 크기는 이 선행 tet 의 edge 길이가 결정한다.\n"
            "bbox 대각선 대비 상대 비율.\n\n"
            "작을수록:\n"
            "  • 매우 조밀한 dual (poly cell 수 증가)\n"
            "  • 시간 크게 증가\n"
            "  • 0.02 이하에서는 precursor 가 timeout 날 수 있음\n\n"
            "클수록:\n"
            "  • 성긴 dual, 빠름\n"
            "  • 형상 재현도 하락\n\n"
            "권장: draft 0.06, standard 0.04, fine 0.025"
        ),
    },
    "precursor_epsilon": {
        "title": "precursor_epsilon — 선행 tet envelope 두께",
        "body": (
            "선행 tet mesh 의 표면 허용 오차 (WildMesh/TetWild 의 epsilon).\n"
            "bbox 대각선 비율.\n\n"
            "작을수록:\n"
            "  • 원본 표면에 바싹 붙는 tet → dual 도 형상 정확\n"
            "  • 시간 증가\n\n"
            "클수록:\n"
            "  • 느슨한 envelope — 얇은 feature 뭉개짐\n\n"
            "권장: draft 2e-3, standard 1e-3, fine 5e-4"
        ),
    },
    "concave_multi_cells": {
        "title": "concave_multi_cells — 오목 경계 edge 분할",
        "body": (
            "원본 mesh 의 오목(concave) 경계 edge 를 dual 변환 시 여러 개 셀로 분할.\n\n"
            "✔ (기본 ON):\n"
            "  • 오목 코너에서 poly cell 이 여러 개로 쪼개져 형상 정확\n"
            "  • L-bracket 같은 안쪽 90° 모서리를 올바르게 재현\n\n"
            "✘:\n"
            "  • 오목 edge 를 단일 cell 로 병합\n"
            "  • cell 수는 적지만 오목 영역에서 심한 sliver 발생"
        ),
    },
    "split_all_faces": {
        "title": "split_all_faces — 모든 face 를 다중 분할",
        "body": (
            "인접한 두 dual cell 사이에 공유되는 face 를 **하나의 face** 로 병합할지,\n"
            "원본 mesh 의 각 tri/quad face 를 **개별 face** 로 보존할지.\n\n"
            "✔ (fine 권장):\n"
            "  • 원본 해상도를 dual 에서도 유지\n"
            "  • face 수 대폭 증가 (메모리/성능 비용 ↑)\n"
            "  • 곡면 영역에서 더 정확한 orthogonality\n\n"
            "✘ (기본, draft/standard):\n"
            "  • 인접 cell 사이 face 통합 — 빠르고 간결\n"
            "  • 대부분 CFD 에선 충분"
        ),
    },
    "preserve_face_zones": {
        "title": "preserve_face_zones — faceZone 보존",
        "body": (
            "원본 mesh 의 faceZone (이름있는 face 집합) 을 dual 에서 유지.\n\n"
            "✔ (기본 ON):\n"
            "  • 경계 조건 패치 이름/구조 그대로 보존\n"
            "  • OpenFOAM 케이스 파일 재생성 안 해도 됨\n\n"
            "✘:\n"
            "  • faceZone 무시 — patch 이름이 리셋될 수 있음\n"
            "  • 특별한 이유 아니면 켜둘 것"
        ),
    },
    "precursor_engine": {
        "title": "precursor_engine — 선행 tet mesh 생성 엔진",
        "body": (
            "polyDualMesh 는 tet/hex polyMesh 를 입력으로 받는다.\n"
            "선행 tet 의 sliver 가 dual cell 의 품질에 결정적인 영향을 미치므로\n"
            "안정적인 엔진을 고르는 것이 중요하다.\n\n"
            "• auto (기본): WildMesh → TetWild → MeshPy 순 시도\n"
            "• wildmesh   : 빠르고 결과 간결. 복잡 형상에 약함\n"
            "• tetwild    : 가장 robust. knot/고복잡 형상 대응\n"
            "• meshpy     : Delaunay — watertight 입력에만 적합"
        ),
    },
}


def _info_button(name: str) -> QPushButton:
    btn = QPushButton("ⓘ")
    btn.setFixedSize(18, 18)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setToolTip(f"{name} 상세 설명 보기")
    btn.setStyleSheet(
        "QPushButton { background: transparent; border: none; "
        "color: #818a99; font-size: 13px; padding: 0; }"
        "QPushButton:hover { color: #4ea3ff; }"
    )

    def _popup() -> None:
        doc = PARAM_DOCS.get(name, {})
        if not doc:
            return
        msg = QMessageBox()
        msg.setWindowTitle(doc.get("title", name))
        msg.setText(f"<b>{doc.get('title', name)}</b>")
        msg.setInformativeText(doc.get("body", ""))
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


class PolyhedralParamPanel(QFrame):
    """polyDualMesh + precursor 설정 패널."""

    params_changed = Signal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "PolyhedralParamPanel { "
            "background: transparent; "
            "border: 1px solid #323a46; border-radius: 5px; "
            "}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        title = QLabel("🔷 polyDualMesh 파라미터")
        title.setStyleSheet(
            "color: #e8ecf2; font-size: 11px; font-weight: 600; "
            "background: transparent; padding: 0;"
        )
        root.addWidget(title)

        # 프리셋 버튼
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
            btn.clicked.connect(lambda _chk=False, n=name: self.apply_preset(n))
            preset_row.addWidget(btn)
        preset_row.addStretch()
        root.addLayout(preset_row)

        # 스크롤 내부 form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        form = QVBoxLayout(inner)
        form.setContentsMargins(0, 4, 0, 4)
        form.setSpacing(4)

        # ── 수치 파라미터 ──────────────────
        numeric_header = QLabel("수치 파라미터")
        numeric_header.setStyleSheet(
            "color: #818a99; font-size: 10px; font-weight: 600; "
            "letter-spacing: 1px; background: transparent; padding: 2px 0;"
        )
        form.addWidget(numeric_header)

        # ★ 셀 크기 제어 — 선행 tet 의 edge_length_r (bbox 대비 상대비율)
        # 슬라이더 범위 10~200 → 실제 값 0.010~0.200 (x0.001)
        self._edge_slider, self._edge_label = self._make_slider_row(
            form, "precursor_edge_length_r", 10, 200,
            fmt=lambda v: f"{v / 1000:.3f}",
        )

        # 선행 tet envelope — log scale 가상 slider 0~1000 → 1e-4~1e-1
        self._eps_slider, self._eps_label = self._make_slider_row(
            form, "precursor_epsilon", 0, 1000,
            fmt=lambda v: f"{self._slider_to_eps(v):.4f}",
        )

        # feature_angle (0~180°, step 1) — feature 보존용 (셀 크기와 무관)
        self._angle_slider, self._angle_label = self._make_slider_row(
            form, "feature_angle", 0, 180, fmt=lambda v: f"{v}°",
        )

        # ── 플래그 파라미터 ──────────────────
        flag_header = QLabel("플래그")
        flag_header.setStyleSheet(
            "color: #818a99; font-size: 10px; font-weight: 600; "
            "letter-spacing: 1px; background: transparent; padding: 6px 0 2px 0;"
        )
        form.addWidget(flag_header)

        self._flags: dict[str, QCheckBox] = {}
        _flag_defaults = {
            "concave_multi_cells": True,
            "split_all_faces": False,
            "preserve_face_zones": True,
        }
        for name, default in _flag_defaults.items():
            self._add_checkbox_row(form, name, default)

        # ── Precursor 엔진 ──────────────────
        prec_header = QLabel("선행 tet 엔진")
        prec_header.setStyleSheet(
            "color: #818a99; font-size: 10px; font-weight: 600; "
            "letter-spacing: 1px; background: transparent; padding: 6px 0 2px 0;"
        )
        form.addWidget(prec_header)

        prec_row = QWidget()
        prec_row.setStyleSheet("background: transparent;")
        prl = QHBoxLayout(prec_row)
        prl.setContentsMargins(0, 0, 0, 0)
        prl.setSpacing(6)
        prl.addWidget(_info_button("precursor_engine"))
        prec_lbl = QLabel("precursor_engine")
        prec_lbl.setFixedWidth(112)
        prec_lbl.setStyleSheet(
            "color: #b6bdc9; font-size: 11px; background: transparent;"
        )
        prl.addWidget(prec_lbl)

        self._precursor_combo = QComboBox()
        self._precursor_combo.setStyleSheet(_dark_combo_style())
        for value, label in (
            ("auto",     "auto (WildMesh → TetWild → MeshPy)"),
            ("wildmesh", "WildMesh"),
            ("tetwild",  "TetWild"),
            ("meshpy",   "MeshPy (TetGen)"),
        ):
            self._precursor_combo.addItem(label, value)
        self._precursor_combo.currentIndexChanged.connect(
            lambda _i: self._emit_params()
        )
        prl.addWidget(self._precursor_combo, stretch=1)
        form.addWidget(prec_row)

        inner.setLayout(form)
        scroll.setWidget(inner)
        scroll.setMinimumHeight(180)
        root.addWidget(scroll)

        # 초기값 — draft
        self.apply_preset("draft")

    # ------------------------------------------------------------------

    def _make_slider_row(
        self, parent_layout, name: str, min_val: int, max_val: int, fmt,
    ) -> tuple[QSlider, QLabel]:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(_info_button(name))

        name_lbl = QLabel(name)
        name_lbl.setFixedWidth(112)
        name_lbl.setStyleSheet(
            "color: #b6bdc9; font-size: 11px; background: transparent;"
        )
        doc = PARAM_DOCS.get(name, {})
        if doc:
            name_lbl.setToolTip(doc.get("body", "").split("\n\n")[0])
        layout.addWidget(name_lbl)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setStyleSheet(
            "QSlider::groove:horizontal { background: #323a46; height: 4px; border-radius: 2px; }"
            "QSlider::handle:horizontal { background: #4ea3ff; width: 14px; margin: -5px 0; "
            "border-radius: 7px; }"
            "QSlider::sub-page:horizontal { background: #4ea3ff; border-radius: 2px; }"
        )
        if doc:
            slider.setToolTip(doc.get("body", "").split("\n\n")[0])
        layout.addWidget(slider, stretch=1)

        value_lbl = QLabel("—")
        value_lbl.setFixedWidth(54)
        value_lbl.setAlignment(Qt.AlignRight)
        value_lbl.setStyleSheet(
            "color: #e8ecf2; font-size: 11px; font-weight: 500; "
            "font-family: 'JetBrains Mono', monospace; background: transparent;"
        )
        layout.addWidget(value_lbl)

        def _on_change(v: int) -> None:
            value_lbl.setText(fmt(v))
            self._emit_params()

        slider.valueChanged.connect(_on_change)
        parent_layout.addWidget(row)
        return slider, value_lbl

    def _add_checkbox_row(self, parent_layout, name: str, default: bool) -> None:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(_info_button(name))

        cb = QCheckBox(name)
        cb.setChecked(default)
        cb.setStyleSheet(
            "QCheckBox { color: #b6bdc9; font-size: 11px; background: transparent; }"
            "QCheckBox::indicator { width: 14px; height: 14px; }"
            "QCheckBox::indicator:unchecked { "
            "  background: #161a20; border: 1px solid #323a46; border-radius: 2px; }"
            "QCheckBox::indicator:checked { "
            "  background: #4ea3ff; border: 1px solid #4ea3ff; border-radius: 2px; }"
        )
        doc = PARAM_DOCS.get(name, {})
        if doc:
            cb.setToolTip(doc.get("body", "").split("\n\n")[0])
        cb.toggled.connect(lambda _v: self._emit_params())
        layout.addWidget(cb)
        layout.addStretch()

        self._flags[name] = cb
        parent_layout.addWidget(row)

    # ------------------------------------------------------------------

    # log-scale helpers for precursor_epsilon (1e-4 ~ 1e-1)
    @staticmethod
    def _eps_to_slider(eps: float) -> int:
        log_eps = math.log10(max(1e-4, min(1e-1, eps)))
        return int((log_eps - (-4)) / 3 * 1000)

    @staticmethod
    def _slider_to_eps(slider_val: int) -> float:
        log_eps = -4 + (slider_val / 1000) * 3
        return 10 ** log_eps

    def apply_preset(self, name: str) -> None:
        p = PRESETS.get(name)
        if not p:
            return
        sliders = (self._angle_slider, self._edge_slider, self._eps_slider)
        for s in sliders:
            s.blockSignals(True)
        try:
            self._angle_slider.setValue(int(float(p["feature_angle"])))
            self._edge_slider.setValue(
                int(float(p.get("precursor_edge_length_r", 0.05)) * 1000)
            )
            self._eps_slider.setValue(
                self._eps_to_slider(float(p.get("precursor_epsilon", 1e-3)))
            )
        finally:
            for s in sliders:
                s.blockSignals(False)
        self._angle_label.setText(f"{int(float(p['feature_angle']))}°")
        self._edge_label.setText(
            f"{float(p.get('precursor_edge_length_r', 0.05)):.3f}"
        )
        self._eps_label.setText(
            f"{float(p.get('precursor_epsilon', 1e-3)):.4f}"
        )

        for flag_name, cb in self._flags.items():
            if flag_name in p:
                cb.blockSignals(True)
                try:
                    cb.setChecked(bool(p[flag_name]))
                finally:
                    cb.blockSignals(False)

        # precursor
        desired = str(p.get("precursor_engine", "auto"))
        for i in range(self._precursor_combo.count()):
            if self._precursor_combo.itemData(i) == desired:
                self._precursor_combo.blockSignals(True)
                try:
                    self._precursor_combo.setCurrentIndex(i)
                finally:
                    self._precursor_combo.blockSignals(False)
                break

        self._emit_params()

    def current_params(self) -> dict:
        out: dict = {
            "polyhedral_feature_angle": float(self._angle_slider.value()),
            "polyhedral_precursor_edge_length_r": float(self._edge_slider.value()) / 1000.0,
            "polyhedral_precursor_epsilon": self._slider_to_eps(self._eps_slider.value()),
            "polyhedral_precursor": str(
                self._precursor_combo.currentData() or "auto"
            ),
        }
        for name, cb in self._flags.items():
            out[f"polyhedral_{name}"] = bool(cb.isChecked())
        return out

    def set_params(self, params: dict) -> None:
        if not params:
            return
        if "polyhedral_feature_angle" in params:
            self._angle_slider.blockSignals(True)
            try:
                self._angle_slider.setValue(
                    int(float(params["polyhedral_feature_angle"]))
                )
            finally:
                self._angle_slider.blockSignals(False)
            self._angle_label.setText(
                f"{int(float(params['polyhedral_feature_angle']))}°"
            )
        if "polyhedral_precursor_edge_length_r" in params:
            self._edge_slider.blockSignals(True)
            try:
                self._edge_slider.setValue(
                    int(float(params["polyhedral_precursor_edge_length_r"]) * 1000)
                )
            finally:
                self._edge_slider.blockSignals(False)
            self._edge_label.setText(
                f"{float(params['polyhedral_precursor_edge_length_r']):.3f}"
            )
        if "polyhedral_precursor_epsilon" in params:
            self._eps_slider.blockSignals(True)
            try:
                self._eps_slider.setValue(
                    self._eps_to_slider(float(params["polyhedral_precursor_epsilon"]))
                )
            finally:
                self._eps_slider.blockSignals(False)
            self._eps_label.setText(
                f"{float(params['polyhedral_precursor_epsilon']):.4f}"
            )
        for name, cb in self._flags.items():
            key = f"polyhedral_{name}"
            if key in params:
                cb.blockSignals(True)
                try:
                    cb.setChecked(bool(params[key]))
                finally:
                    cb.blockSignals(False)
        if "polyhedral_precursor" in params:
            desired = str(params["polyhedral_precursor"])
            for i in range(self._precursor_combo.count()):
                if self._precursor_combo.itemData(i) == desired:
                    self._precursor_combo.blockSignals(True)
                    try:
                        self._precursor_combo.setCurrentIndex(i)
                    finally:
                        self._precursor_combo.blockSignals(False)
                    break
        self._emit_params()

    def _emit_params(self) -> None:
        self.params_changed.emit(self.current_params())
