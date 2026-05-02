"""BC-INTEGRATION / beta2797 — mesh_viewer 에 face picker + BC editor 통합 helper.

기존 InteractiveMeshViewer 가 self.plotter (pyvistaqt.QtInteractor) 를 가질 때,
이 helper 를 호출하여 face pick UI + BC editor 를 wire-in.

사용:
    from desktop.qt_app.bc_picker_integration import attach_bc_picker
    self.bc_ui = attach_bc_picker(self.plotter, surface_mesh, parent=self)
    # → toolbar 에 'Pick BC' / 'Add BC' / 'Save BC' 버튼 자동 추가.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:
    from PySide6.QtWidgets import (
        QWidget, QHBoxLayout, QPushButton, QLabel, QFileDialog, QMessageBox,
    )
    _QT_OK = True
except ImportError:
    _QT_OK = False

from desktop.qt_app.bc_face_picker import (
    BCManager, FacePickController, BCAssignment,
)


@dataclass
class BCPickerUI:
    plotter: object = None
    surface: object = None
    controller: Optional[FacePickController] = None
    manager: BCManager = None
    toolbar: Optional[object] = None

    def __post_init__(self):
        if self.manager is None:
            self.manager = BCManager()


def attach_bc_picker(
    plotter,
    surface_mesh,
    *,
    parent=None,
) -> BCPickerUI:
    """plotter 에 BC picker UI 부착. toolbar (QWidget) 반환.

    Args:
        plotter: pyvistaqt.QtInteractor or pv.Plotter.
        surface_mesh: pv.PolyData of boundary tris/quads.
        parent: parent QWidget (optional).

    Returns:
        BCPickerUI dataclass with .toolbar (QWidget) for layout insert.
    """
    if not _QT_OK:
        return BCPickerUI(plotter=plotter, surface=surface_mesh,
                          controller=None, manager=BCManager())

    manager = BCManager()
    selected_label = QLabel("0 faces selected", parent)

    def _on_sel_changed(face_ids):
        selected_label.setText(f"{len(face_ids)} faces selected")

    controller = FacePickController(
        plotter, surface_mesh, on_selection_changed=_on_sel_changed,
    )

    toolbar = QWidget(parent)
    h = QHBoxLayout(toolbar)
    h.setContentsMargins(4, 2, 4, 2)

    btn_single = QPushButton("Pick faces (single)", toolbar)
    btn_single.setCheckable(True)

    def _toggle_single(checked):
        if checked:
            controller.enable_single_pick(additive=True)
            btn_box.setChecked(False)
        else:
            controller.disable()

    btn_single.toggled.connect(_toggle_single)

    btn_box = QPushButton("Pick faces (box)", toolbar)
    btn_box.setCheckable(True)

    def _toggle_box(checked):
        if checked:
            controller.enable_box_pick()
            btn_single.setChecked(False)
        else:
            controller.disable()

    btn_box.toggled.connect(_toggle_box)

    btn_clear = QPushButton("Clear", toolbar)
    btn_clear.clicked.connect(controller.clear)

    btn_assign = QPushButton("Assign BC...", toolbar)

    def _assign_bc():
        ids = controller.selected_face_indices
        if not ids:
            QMessageBox.information(parent, "BC", "No face selected.")
            return
        from desktop.qt_app.bc_editor_dialog import BCEditorDialog
        dlg = BCEditorDialog(face_indices=ids, parent=parent)
        if dlg.exec():
            ba = dlg.get_assignment()
            manager.add(ba)
            controller.clear()
            QMessageBox.information(
                parent, "BC", f"Patch '{ba.name}' added with {len(ba.face_indices)} faces.",
            )

    btn_assign.clicked.connect(_assign_bc)

    btn_save = QPushButton("Save BC →", toolbar)
    btn_save.setToolTip("Save BC metadata to .ccm file or polyMesh dir")

    def _save_bc():
        if len(manager) == 0:
            QMessageBox.information(parent, "BC", "No BC assigned yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            parent, "Save BC to...",
            filter="CCMIO HDF5 (*.ccm *.h5);;OpenFOAM polyMesh dir (*)",
        )
        if not path:
            return
        ok = False
        if path.endswith(".ccm") or path.endswith(".h5"):
            ok = manager.export_to_ccmio(path)
        else:
            from pathlib import Path
            ok = manager.export_face_groups_to_polymesh_boundary(
                Path(path), n_total_faces=10**9,
            )
        QMessageBox.information(
            parent, "BC", "Saved." if ok else "Save failed.",
        )

    btn_save.clicked.connect(_save_bc)

    # C / beta2802 — OpenFOAM 0/ field files 자동 생성.
    btn_save_fields = QPushButton("Save 0/ fields", toolbar)
    btn_save_fields.setToolTip(
        "Generate OpenFOAM 0/U, 0/p, 0/T field files for solver",
    )

    def _save_fields():
        if len(manager) == 0:
            QMessageBox.information(parent, "BC", "No BC assigned yet.")
            return
        path = QFileDialog.getExistingDirectory(
            parent, "Select OpenFOAM case directory...",
        )
        if not path:
            return
        # detect: include T if any patch has temperature/htc value.
        has_T = any(
            "temperature" in (ba.values or {})
            or ba.bc_type == "interface_heat"
            for ba in manager.assignments
        )
        res = manager.export_openfoam_fields(
            path,
            fields=("U", "p"),
            include_turbulence=False,
            include_temperature=has_T,
        )
        QMessageBox.information(
            parent, "BC",
            f"OpenFOAM fields:\n{res.message}\n"
            f"\nfiles:\n" + "\n".join(res.field_paths),
        )

    btn_save_fields.clicked.connect(_save_fields)

    btn_list = QPushButton("List BC", toolbar)

    def _list_bc():
        if len(manager) == 0:
            QMessageBox.information(parent, "BC", "(empty)")
            return
        lines = []
        for ba in manager.assignments:
            lines.append(f"{ba.name}  type={ba.bc_type}  "
                         f"faces={len(ba.face_indices)}  values={ba.values}")
        QMessageBox.information(parent, "BC list", "\n".join(lines))

    btn_list.clicked.connect(_list_bc)

    # BC-OVERLAY / beta2799 — patch color visualization toggle.
    btn_overlay = QPushButton("Show colors", toolbar)
    btn_overlay.setCheckable(True)
    btn_overlay.setToolTip("Color BC patches on the mesh")
    overlay_actors: list = []

    def _toggle_overlay(checked):
        from desktop.qt_app.bc_overlay import (
            render_bc_overlay, remove_bc_overlay,
        )
        nonlocal overlay_actors
        if overlay_actors:
            remove_bc_overlay(plotter, overlay_actors)
            overlay_actors = []
        if checked and len(manager) > 0:
            actors = render_bc_overlay(
                plotter, surface_mesh, manager,
                opacity=0.7, show_edges=True,
            )
            overlay_actors = actors
        try:
            plotter.render()
        except Exception:
            pass

    btn_overlay.toggled.connect(_toggle_overlay)

    h.addWidget(btn_single)
    h.addWidget(btn_box)
    h.addWidget(btn_clear)
    h.addWidget(btn_assign)
    h.addWidget(btn_list)
    h.addWidget(btn_overlay)
    h.addWidget(btn_save)
    h.addWidget(btn_save_fields)
    h.addWidget(selected_label, stretch=1)

    return BCPickerUI(
        plotter=plotter, surface=surface_mesh,
        controller=controller, manager=manager, toolbar=toolbar,
    )
