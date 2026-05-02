"""BC-EDITOR / beta2796 — Qt dialog for BC patch editing.

사용 흐름:
    1. mesh_viewer 의 face pick controller 가 set 누적.
    2. 사용자가 "BC 지정" 버튼 → BCEditorDialog 열림.
    3. patch 명, type, values (velocity/pressure/temp) 입력.
    4. accept → BCAssignment 반환 + BCManager 에 추가.
"""
from __future__ import annotations

from typing import Optional

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDialog, QFormLayout, QHBoxLayout, QVBoxLayout, QLineEdit,
        QComboBox, QSpinBox, QDoubleSpinBox, QLabel, QPushButton,
        QMessageBox, QDialogButtonBox, QGroupBox,
    )
    _QT_OK = True
except ImportError:
    _QT_OK = False

from desktop.qt_app.bc_face_picker import (
    BCAssignment, BC_TYPES, BC_DEFAULT_VALUES,
)


def _qt_required():
    if not _QT_OK:
        raise RuntimeError("PySide6 not installed (BC editor requires Qt)")


class BCEditorDialog(QDialog if _QT_OK else object):
    """단일 BC patch 의 type/values 편집 dialog."""

    def __init__(
        self,
        face_indices: list[int],
        existing: Optional[BCAssignment] = None,
        parent=None,
    ):
        _qt_required()
        super().__init__(parent)
        self.setWindowTitle("Boundary Condition Editor")
        self.face_indices = list(face_indices)
        self._existing = existing

        layout = QVBoxLayout(self)

        # info label.
        info = QLabel(
            f"Selected faces: {len(face_indices)}",
            self,
        )
        layout.addWidget(info)

        # form: name + type.
        form = QFormLayout()
        self.name_edit = QLineEdit(
            existing.name if existing else f"patch_{len(face_indices)}",
            self,
        )
        form.addRow("Patch name", self.name_edit)

        self.type_combo = QComboBox(self)
        for t in BC_TYPES:
            self.type_combo.addItem(t)
        if existing and existing.bc_type in BC_TYPES:
            self.type_combo.setCurrentText(existing.bc_type)
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        form.addRow("BC type", self.type_combo)

        self.comment_edit = QLineEdit(
            existing.comment if existing else "",
            self,
        )
        form.addRow("Comment (opt)", self.comment_edit)
        layout.addLayout(form)

        # values group (dynamic).
        self._values_group = QGroupBox("Values", self)
        self._values_layout = QFormLayout(self._values_group)
        layout.addWidget(self._values_group)
        self._value_widgets: dict = {}
        self._on_type_changed(self.type_combo.currentText())

        # buttons.
        bb = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self,
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

        self.resize(360, 280)

    def _clear_values_layout(self):
        while self._values_layout.rowCount() > 0:
            self._values_layout.removeRow(0)
        self._value_widgets.clear()

    def _on_type_changed(self, type_name: str):
        self._clear_values_layout()
        defaults = BC_DEFAULT_VALUES.get(type_name, {})
        existing_vals = (
            self._existing.values if self._existing
            and self._existing.bc_type == type_name
            else {}
        )

        for vname, vdefault in defaults.items():
            cur = existing_vals.get(vname, vdefault)
            if isinstance(cur, (list, tuple)) and len(cur) == 3:
                # vector input: 3 spinboxes side by side.
                row_widget = self._make_vector_row(vname, cur)
                self._values_layout.addRow(f"{vname} (xyz)", row_widget)
            else:
                # scalar.
                sb = QDoubleSpinBox(self)
                sb.setRange(-1e9, 1e9)
                sb.setDecimals(6)
                sb.setValue(float(cur))
                self._values_layout.addRow(f"{vname}", sb)
                self._value_widgets[vname] = sb

    def _make_vector_row(self, name: str, default: list):
        from PySide6.QtWidgets import QWidget
        w = QWidget(self)
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        sbs = []
        for i, v in enumerate(default):
            sb = QDoubleSpinBox(w)
            sb.setRange(-1e9, 1e9)
            sb.setDecimals(6)
            sb.setValue(float(v))
            h.addWidget(sb)
            sbs.append(sb)
        self._value_widgets[name] = sbs
        return w

    def get_assignment(self) -> BCAssignment:
        """dialog 결과를 BCAssignment 로."""
        name = self.name_edit.text().strip() or f"patch_{len(self.face_indices)}"
        bc_type = self.type_combo.currentText()
        comment = self.comment_edit.text().strip()
        values: dict = {}
        for vname, w in self._value_widgets.items():
            if isinstance(w, list):
                values[vname] = [float(sb.value()) for sb in w]
            else:
                try:
                    values[vname] = float(w.value())
                except Exception:
                    pass
        return BCAssignment(
            name=name,
            bc_type=bc_type,
            face_indices=list(self.face_indices),
            values=values,
            comment=comment,
        )


def make_bc_assignment_from_user_input(
    face_indices: list[int],
    name: str,
    bc_type: str,
    values: dict | None = None,
    comment: str = "",
) -> BCAssignment:
    """programmatic helper — Qt 없이 BCAssignment 생성 (testing/CLI)."""
    if bc_type not in BC_TYPES:
        bc_type = "wall"
    vals = dict(values) if values else dict(BC_DEFAULT_VALUES.get(bc_type, {}))
    return BCAssignment(
        name=name, bc_type=bc_type,
        face_indices=list(face_indices),
        values=vals, comment=comment,
    )
