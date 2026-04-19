"""파라미터 실시간 유효성 검증 위젯.

QLineEdit을 감싸서 사용자 입력을 타이핑마다 validate:
- 유효 → 기본 테두리
- 경고 (추천 범위 밖) → 노랑
- 에러 (파싱 실패, 범위 밖 심각) → 빨강

인라인 에러 라벨로 해결 힌트 표시.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget


@dataclass
class ValidationResult:
    level: str                # "ok" | "warn" | "err"
    message: str = ""         # 표시할 힌트 (err/warn일 때만)
    parsed_value: float | int | str | None = None


def numeric_validator(
    type_: str = "float",
    min_val: float | None = None,
    max_val: float | None = None,
    recommended_min: float | None = None,
    recommended_max: float | None = None,
) -> Callable[[str], ValidationResult]:
    """numeric (float/int) 값에 대한 validator factory.

    - min/max 범위 초과 → err
    - recommended 범위 밖이지만 허용 범위 내 → warn
    - 범위 내 → ok
    - 빈 문자열 → ok (auto)
    """
    def _validate(text: str) -> ValidationResult:
        s = (text or "").strip()
        if not s:
            return ValidationResult(level="ok", parsed_value=None)
        try:
            if type_ == "int":
                v = int(float(s))  # "5.0" → 5 허용
            else:
                v = float(s)
        except (ValueError, TypeError):
            return ValidationResult(
                level="err",
                message=f"숫자 필요 — '{s}'는 파싱 실패",
            )
        if min_val is not None and v < min_val:
            return ValidationResult(
                level="err",
                message=f"{v} < 최소 {min_val}",
                parsed_value=v,
            )
        if max_val is not None and v > max_val:
            return ValidationResult(
                level="err",
                message=f"{v} > 최대 {max_val}",
                parsed_value=v,
            )
        if recommended_min is not None and v < recommended_min:
            return ValidationResult(
                level="warn",
                message=f"권장 범위 [{recommended_min}, {recommended_max}] 밖 (작음)",
                parsed_value=v,
            )
        if recommended_max is not None and v > recommended_max:
            return ValidationResult(
                level="warn",
                message=f"권장 범위 [{recommended_min}, {recommended_max}] 밖 (큼)",
                parsed_value=v,
            )
        return ValidationResult(level="ok", parsed_value=v)

    return _validate


_STYLES = {
    "ok":   "QLineEdit { border: 1px solid #3e4757; }",
    "warn": "QLineEdit { border: 1px solid #f5b454; }",
    "err":  "QLineEdit { border: 1px solid #ff6b6b; }",
}
_HINT_COLORS = {
    "ok": "#818a99",
    "warn": "#f5b454",
    "err": "#ff6b6b",
}


class ValidatedLineEdit(QWidget):
    """QLineEdit + 인라인 힌트 라벨 (에러/경고시 색상 표시).

    사용:
        w = ValidatedLineEdit(validator=numeric_validator("float", min_val=0))
        w.setText("0.001")
        w.value_changed.connect(lambda ok, val: ...)
    """

    value_changed = Signal(bool, object)  # (is_valid, parsed_value)

    def __init__(
        self,
        validator: Callable[[str], ValidationResult] | None = None,
        placeholder: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._validator = validator

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setStyleSheet(
            "QLineEdit { background: #161a20; color: #e8ecf2; "
            "border: 1px solid #3e4757; border-radius: 4px; "
            "padding: 4px 8px; font-size: 12px; }"
            "QLineEdit:focus { border-color: #4ea3ff; }"
        )
        layout.addWidget(self.edit)

        self.hint = QLabel("")
        self.hint.setStyleSheet(
            f"color: {_HINT_COLORS['ok']}; font-size: 10px; "
            f"background: transparent; padding: 2px 2px 0 2px;"
        )
        self.hint.setWordWrap(True)
        self.hint.setVisible(False)
        layout.addWidget(self.hint)

        self.edit.textChanged.connect(self._on_text_changed)

    def text(self) -> str:
        return self.edit.text()

    def setText(self, value: str) -> None:
        self.edit.setText(value)

    def setValidator(self, validator: Callable[[str], ValidationResult] | None) -> None:
        self._validator = validator
        self._on_text_changed(self.edit.text())

    def current_validation(self) -> ValidationResult:
        if self._validator is None:
            return ValidationResult(level="ok")
        return self._validator(self.edit.text())

    def _on_text_changed(self, text: str) -> None:
        if self._validator is None:
            self.hint.setVisible(False)
            self.value_changed.emit(True, text)
            return
        result = self._validator(text)
        base_style = (
            "QLineEdit { background: #161a20; color: #e8ecf2; "
            "border-radius: 4px; padding: 4px 8px; font-size: 12px; }"
            "QLineEdit:focus { border-color: #4ea3ff; }"
        )
        border = {
            "ok": "#3e4757",
            "warn": "#f5b454",
            "err": "#ff6b6b",
        }.get(result.level, "#3e4757")
        self.edit.setStyleSheet(
            base_style
            + f"QLineEdit {{ border: 1px solid {border}; }}"
        )
        if result.message:
            self.hint.setText(result.message)
            self.hint.setStyleSheet(
                f"color: {_HINT_COLORS.get(result.level, '#818a99')}; "
                f"font-size: 10px; background: transparent; padding: 2px;"
            )
            self.hint.setVisible(True)
        else:
            self.hint.setVisible(False)

        self.value_changed.emit(result.level != "err", result.parsed_value)
