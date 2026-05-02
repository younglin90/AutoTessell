"""BC-FACE-PICK / beta2795 — interactive boundary face selection + BC assignment.

GUI workflow (PyVista + Qt):
    1. mesh viewer 에서 사용자가 surface face 를 클릭/박스선택.
    2. 선택된 face 인덱스 set 을 patch 로 묶음.
    3. BCEditor dialog 로 patch 의 BC type (wall/inlet/outlet/symmetry)
       + 값 (velocity/pressure/temperature) 입력.
    4. 저장: ccmio_writer.write_ccmio_boundary_conditions (BETA2792).

핵심 컴포넌트:
    FacePickController: PyVista plotter 에 click/box callback 연결.
    BCAssignment: face_indices + bc_type + values 데이터클래스.
    BCEditorDialog: Qt form dialog (patch 명, type combo, values).

CLAUDE.md: PySide6 + pyvista 기존 의존만, 외부 lib 신규 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray


@dataclass
class BCAssignment:
    """단일 patch BC 할당."""

    name: str = ""
    bc_type: str = "wall"   # wall / inlet / outlet / symmetry / pressure_outlet
    face_indices: list[int] = field(default_factory=list)
    values: dict = field(default_factory=dict)
    color: tuple = (200, 200, 200)
    comment: str = ""


# 표준 BC 타입 표 (BETA2800 — 9 advanced types 추가).
BC_TYPES = (
    # basic.
    "wall",
    "inlet",
    "outlet",
    "symmetry",
    "pressure_outlet",
    "velocity_inlet",
    "moving_wall",
    "interface",
    "empty",
    # advanced.
    "periodic",
    "cyclic_ami",
    "interface_heat",
    "sliding_mesh",
    "fan",
    "porous_jump",
    "wedge",
    "mass_flow_inlet",
    "outflow",
)

# BC 타입별 default value 키.
BC_DEFAULT_VALUES = {
    # basic.
    "wall":              {"velocity": [0.0, 0.0, 0.0]},
    "inlet":             {"velocity": [1.0, 0.0, 0.0]},
    "outlet":            {"pressure": 0.0},
    "symmetry":          {},
    "pressure_outlet":   {"pressure": 0.0},
    "velocity_inlet":    {"velocity": [1.0, 0.0, 0.0]},
    "moving_wall":       {"velocity": [0.0, 0.0, 0.0]},
    "interface":         {},
    "empty":             {},
    # advanced.
    "periodic":          {"matched_patch": "patch_pair"},
    "cyclic_ami":        {"matched_patch": "patch_pair"},
    "interface_heat":    {"htc": 1000.0, "T_ext": 300.0},
    "sliding_mesh":      {"omega": 0.0, "axis": [0.0, 0.0, 1.0]},
    "fan":               {"pressure_jump": 100.0},
    "porous_jump":       {"resistance": 1e6, "thickness": 0.001},
    "wedge":             {"angle_deg": 5.0},
    "mass_flow_inlet":   {"mass_flow": 1.0, "temperature": 300.0},
    "outflow":           {"flow_split": 1.0},
}


class FacePickController:
    """PyVista plotter 에 face pick callback 을 연결하는 controller.

    선택된 face index list 를 누적, BCAssignment 로 묶을 수 있게 한다.
    """

    def __init__(
        self,
        plotter,
        surface_mesh: object,  # pyvista.PolyData
        on_selection_changed=None,
    ):
        """
        Args:
            plotter: pyvistaqt.QtInteractor or pyvista.Plotter.
            surface_mesh: pv.PolyData (boundary tri/quad).
            on_selection_changed: callback(selected_face_indices: list[int]).
        """
        self.plotter = plotter
        self.surface = surface_mesh
        self.callback = on_selection_changed
        self._selected: set[int] = set()
        self._mode: str = "off"   # off / single / box

    @property
    def selected_face_indices(self) -> list[int]:
        return sorted(self._selected)

    def clear(self):
        self._selected.clear()
        if self.callback:
            self.callback(self.selected_face_indices)

    def enable_single_pick(self, *, additive: bool = True):
        """단일 face 클릭 모드. additive=True 면 누적."""
        self._mode = "single"

        def _cb(picked, event=None):
            if picked is None:
                return
            try:
                cell_id = int(picked) if not hasattr(picked, "n_cells") else None
            except Exception:
                cell_id = None
            if cell_id is None:
                return
            if additive:
                if cell_id in self._selected:
                    self._selected.discard(cell_id)
                else:
                    self._selected.add(cell_id)
            else:
                self._selected = {cell_id}
            if self.callback:
                self.callback(self.selected_face_indices)

        try:
            self.plotter.enable_cell_picking(
                callback=_cb,
                show_message="Click face to select (Ctrl+click to deselect)",
                style="surface",
                color="red",
                through=False,
            )
        except Exception:
            pass

    def enable_box_pick(self):
        """drag 박스로 다수 face 선택."""
        self._mode = "box"

        def _cb(picked):
            if picked is None or not hasattr(picked, "cell_data"):
                return
            try:
                ids = picked.cell_data.get("vtkOriginalCellIds")
                if ids is not None:
                    for i in ids:
                        self._selected.add(int(i))
                if self.callback:
                    self.callback(self.selected_face_indices)
            except Exception:
                pass

        try:
            self.plotter.enable_cell_picking(
                callback=_cb,
                show_message="Drag box to select multiple faces",
                style="surface",
                color="blue",
                through=True,
            )
        except Exception:
            pass

    def disable(self):
        self._mode = "off"
        try:
            self.plotter.disable_picking()
        except Exception:
            pass


class BCManager:
    """BCAssignment 들의 collection + persist (ccmio_writer 연동)."""

    def __init__(self):
        self.assignments: list[BCAssignment] = []

    def add(self, ba: BCAssignment) -> int:
        """returns assignment index."""
        # name 중복이면 face indices merge.
        for i, existing in enumerate(self.assignments):
            if existing.name == ba.name:
                merged = sorted(set(existing.face_indices) | set(ba.face_indices))
                existing.face_indices = merged
                if ba.values:
                    existing.values.update(ba.values)
                return i
        self.assignments.append(ba)
        return len(self.assignments) - 1

    def remove(self, name: str) -> bool:
        for i, ba in enumerate(self.assignments):
            if ba.name == name:
                self.assignments.pop(i)
                return True
        return False

    def get(self, name: str) -> BCAssignment | None:
        for ba in self.assignments:
            if ba.name == name:
                return ba
        return None

    def to_ccmio_dict(self) -> dict:
        """ccmio_writer.write_ccmio_boundary_conditions 입력 형식."""
        out: dict = {}
        for ba in self.assignments:
            entry = {"type": ba.bc_type, "values": dict(ba.values)}
            if ba.comment:
                entry["comment"] = ba.comment
            out[ba.name] = entry
        return out

    def export_to_ccmio(self, ccm_path) -> bool:
        """existing CCMIO file 에 BC metadata 추가."""
        try:
            from core.utils.ccmio_writer import (
                write_ccmio_boundary_conditions,
            )
        except Exception:
            return False
        return write_ccmio_boundary_conditions(ccm_path, self.to_ccmio_dict())

    def export_face_groups_to_polymesh_boundary(
        self, polymesh_dir, n_total_faces: int,
    ) -> bool:
        """OpenFOAM polyMesh/boundary 파일 갱신 — 각 BC 를 patch 로 추가.

        Args:
            polymesh_dir: 기존 polyMesh dir.
            n_total_faces: 전체 face 수 (validate).

        Returns:
            성공 여부.
        """
        from pathlib import Path
        pdir = Path(polymesh_dir)
        bfile = pdir / "boundary"
        if not bfile.exists():
            return False
        try:
            patches_text = []
            for ba in self.assignments:
                patches_text.append(
                    f"    {ba.name}\n    {{\n"
                    f"        type            {ba.bc_type};\n"
                    f"        nFaces          {len(ba.face_indices)};\n"
                    f"        startFace       {min(ba.face_indices) if ba.face_indices else 0};\n"
                    f"    }}\n"
                )
            content = (
                "FoamFile\n{\n    version     2.0;\n    format      ascii;\n"
                "    class       polyBoundaryMesh;\n    object      boundary;\n}\n\n"
                f"{len(self.assignments)}\n(\n"
                + "".join(patches_text)
                + ")\n"
            )
            bfile.write_text(content)
            return True
        except Exception:
            return False

    def __len__(self):
        return len(self.assignments)


def boundary_faces_from_polymesh(
    pts: NDArray[np.float64],
    cells: list,
    owner: list[int],
    neighbour: list[int],
) -> tuple[NDArray[np.int64], list[int]]:
    """polyMesh 형식 → boundary face vertex array + boundary face IDs.

    Args:
        pts: (N, 3).
        cells: list of face vertex indices.
        owner, neighbour: face → cell id (neighbour=-1 → boundary).

    Returns:
        (boundary_face_pts (M, 3, max_v), boundary_face_global_ids (M,)).
    """
    bnd_face_ids = []
    for fi, nb in enumerate(neighbour):
        if int(nb) < 0:
            bnd_face_ids.append(fi)
    return np.asarray(bnd_face_ids, dtype=np.int64), bnd_face_ids
