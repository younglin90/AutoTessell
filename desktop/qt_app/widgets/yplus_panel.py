"""y⁺ 기반 첫 번째 BL 층 두께 자동 계산 패널 (beta98).

레이아웃:
    ┌──────────────── y⁺ 자동 BL 두께 계산 ──────────────────┐
    │ 유체   [air ▼]  유입 속도 [__10.0__] m/s               │
    │ 특성 길이 [___1.0__] m  (기본: bbox 대각선 자동)        │
    │ 목표 y⁺ [___1.0__]                                     │
    │                     [ 계산하기 ]                        │
    │ 첫 층 두께: 3.47e-05 m  (Re=6.60e+05, Cf=3.07e-03)    │
    └─────────────────────────────────────────────────────────┘

"계산하기" 클릭 시 estimate_first_layer_thickness 호출 → 결과 라벨 + 클립보드 복사.
계산된 값을 bl_thickness_computed 시그널로 외부에 전달 (메인 윈도우가 bl_first_height
파라미터에 자동 주입 가능).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class YPlusPanel(QFrame):
    """y⁺ 기반 첫 번째 BL 층 두께 자동 계산 패널 (beta98)."""

    # 계산된 첫 층 두께 [m] 를 외부에 전달
    bl_thickness_computed = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("YPlusPanel")
        self.setStyleSheet(
            "YPlusPanel { "
            "background: transparent; "
            "border: 1px solid #323a46; border-radius: 5px; "
            "}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # 제목
        title = QLabel("y⁺ 자동 BL 두께 계산")
        title.setStyleSheet(
            "color: #e8ecf2; font-size: 11px; font-weight: 600; "
            "background: transparent; padding: 0; border: none;"
        )
        root.addWidget(title)

        # 행 1: 유체 + 유입 속도
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        fluid_lbl = QLabel("유체")
        fluid_lbl.setStyleSheet(
            "color: #b6bdc9; font-size: 11px; background: transparent; border: none;"
        )
        row1.addWidget(fluid_lbl)

        self._fluid_combo = QComboBox()
        self._fluid_combo.addItems(["air", "water", "oil"])
        self._fluid_combo.setFixedWidth(72)
        self._fluid_combo.setStyleSheet(
            "QComboBox { background: #1c2129; color: #e8ecf2; "
            "border: 1px solid #323a46; border-radius: 3px; "
            "padding: 2px 4px; font-size: 11px; }"
            "QComboBox::drop-down { border: none; }"
            "QComboBox QAbstractItemView { background: #1c2129; color: #e8ecf2; "
            "border: 1px solid #323a46; }"
        )
        row1.addWidget(self._fluid_combo)

        row1.addSpacing(12)

        vel_lbl = QLabel("유입 속도")
        vel_lbl.setStyleSheet(
            "color: #b6bdc9; font-size: 11px; background: transparent; border: none;"
        )
        row1.addWidget(vel_lbl)

        self._velocity_spin = QDoubleSpinBox()
        self._velocity_spin.setRange(0.001, 1e6)
        self._velocity_spin.setDecimals(3)
        self._velocity_spin.setValue(10.0)
        self._velocity_spin.setFixedWidth(80)
        self._velocity_spin.setStyleSheet(self._spin_css())
        row1.addWidget(self._velocity_spin)

        ms_lbl = QLabel("m/s")
        ms_lbl.setStyleSheet(
            "color: #818a99; font-size: 11px; background: transparent; border: none;"
        )
        row1.addWidget(ms_lbl)
        row1.addStretch()
        root.addLayout(row1)

        # 행 2: 특성 길이
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        len_lbl = QLabel("특성 길이")
        len_lbl.setStyleSheet(
            "color: #b6bdc9; font-size: 11px; background: transparent; border: none;"
        )
        row2.addWidget(len_lbl)

        self._length_spin = QDoubleSpinBox()
        self._length_spin.setRange(1e-6, 1e6)
        self._length_spin.setDecimals(4)
        self._length_spin.setValue(1.0)
        self._length_spin.setFixedWidth(88)
        self._length_spin.setStyleSheet(self._spin_css())
        row2.addWidget(self._length_spin)

        m_lbl = QLabel("m")
        m_lbl.setStyleSheet(
            "color: #818a99; font-size: 11px; background: transparent; border: none;"
        )
        row2.addWidget(m_lbl)

        hint_lbl = QLabel("(기본: bbox 대각선)")
        hint_lbl.setStyleSheet(
            "color: #5a6270; font-size: 10px; background: transparent; border: none;"
        )
        row2.addWidget(hint_lbl)
        row2.addStretch()
        root.addLayout(row2)

        # 행 3: 목표 y+
        row3 = QHBoxLayout()
        row3.setSpacing(8)

        yp_lbl = QLabel("목표 y⁺")
        yp_lbl.setStyleSheet(
            "color: #b6bdc9; font-size: 11px; background: transparent; border: none;"
        )
        row3.addWidget(yp_lbl)

        self._yplus_spin = QDoubleSpinBox()
        self._yplus_spin.setRange(0.01, 1000.0)
        self._yplus_spin.setDecimals(2)
        self._yplus_spin.setValue(1.0)
        self._yplus_spin.setFixedWidth(72)
        self._yplus_spin.setStyleSheet(self._spin_css())
        row3.addWidget(self._yplus_spin)

        yp_hint = QLabel("(1.0 = low-Re 모델, 30~300 = 벽 함수)")
        yp_hint.setStyleSheet(
            "color: #5a6270; font-size: 10px; background: transparent; border: none;"
        )
        row3.addWidget(yp_hint)
        row3.addStretch()
        root.addLayout(row3)

        # 계산 버튼
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._calc_btn = QPushButton("계산하기")
        self._calc_btn.setFixedHeight(26)
        self._calc_btn.setStyleSheet(
            "QPushButton { background: #1c4a8c; color: #e8ecf2; "
            "border: 1px solid #2a6abf; border-radius: 4px; "
            "padding: 4px 18px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background: #2a6abf; }"
            "QPushButton:pressed { background: #153766; }"
        )
        self._calc_btn.clicked.connect(self._on_calculate)
        btn_row.addWidget(self._calc_btn)
        root.addLayout(btn_row)

        # 결과 라벨
        self._result_label = QLabel("")
        self._result_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._result_label.setWordWrap(True)
        self._result_label.setStyleSheet(
            "color: #4ea3ff; font-size: 11px; font-family: 'JetBrains Mono', monospace; "
            "background: transparent; border: none; padding: 2px 0;"
        )
        root.addWidget(self._result_label)

    # ------------------------------------------------------------------
    # 내부 헬퍼

    @staticmethod
    def _spin_css() -> str:
        return (
            "QDoubleSpinBox { background: #1c2129; color: #e8ecf2; "
            "border: 1px solid #323a46; border-radius: 3px; "
            "padding: 2px 4px; font-size: 11px; }"
            "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 14px; }"
        )

    # ------------------------------------------------------------------

    def _on_calculate(self) -> None:
        """계산하기 버튼 클릭 핸들러."""
        try:
            from core.utils.yplus import estimate_first_layer_thickness  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            self._result_label.setText(f"[error] yplus import 실패: {exc}")
            return

        fluid = self._fluid_combo.currentText()
        velocity = self._velocity_spin.value()
        length = self._length_spin.value()
        y_plus = self._yplus_spin.value()

        try:
            result = estimate_first_layer_thickness(
                velocity,
                length,
                fluid=fluid,
                y_plus_target=y_plus,
            )
        except ValueError as exc:
            self._result_label.setStyleSheet(
                "color: #e05e5e; font-size: 11px; "
                "background: transparent; border: none;"
            )
            self._result_label.setText(f"[error] {exc}")
            return

        # 성공 표시
        self._result_label.setStyleSheet(
            "color: #4ea3ff; font-size: 11px; font-family: 'JetBrains Mono', monospace; "
            "background: transparent; border: none; padding: 2px 0;"
        )
        text = (
            f"첫 층 두께: {result.y_first:.3e} m\n"
            f"(Re={result.re_l:.2e}, Cf={result.cf:.2e}, "
            f"uτ={result.u_tau:.4f} m/s)"
        )
        self._result_label.setText(text)

        # 클립보드 복사
        try:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(f"{result.y_first:.6e}")
        except Exception:  # noqa: BLE001
            pass

        # 시그널 발행
        self.bl_thickness_computed.emit(result.y_first)

    # ------------------------------------------------------------------
    # 외부 API

    def set_characteristic_length(self, length: float) -> None:
        """bbox 대각선 등 외부에서 특성 길이를 주입할 때 사용."""
        if length > 0:
            self._length_spin.setValue(length)

    def get_last_result(self) -> float | None:
        """마지막으로 계산된 y_first 값 반환. 미계산 시 None."""
        text = self._result_label.text()
        if not text or "[error]" in text:
            return None
        # "첫 층 두께: 3.47e-05 m" 에서 숫자 추출
        import re  # noqa: PLC0415
        m = re.search(r"([\d.]+e[+-]?\d+)", text)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
        return None
