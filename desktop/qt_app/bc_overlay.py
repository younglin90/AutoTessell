"""BC-OVERLAY / beta2799 — patch 별 색상 visualization.

BCManager 의 BC assignments 를 PyVista plotter 에 색상 overlay 로 표시.

BC type 별 default 색상 표:
    wall            #808080 gray
    inlet           #1e88e5 blue
    outlet          #e53935 red
    symmetry        #43a047 green
    pressure_outlet #fb8c00 orange
    velocity_inlet  #00acc1 cyan
    moving_wall     #8e24aa purple
    interface       #fdd835 yellow
    empty           #757575 dark-gray
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


# BC type → RGB tuple (0-255).
BC_COLOR_MAP: dict[str, tuple[int, int, int]] = {
    # basic.
    "wall":            (128, 128, 128),
    "inlet":           ( 30, 136, 229),
    "outlet":          (229,  57,  53),
    "symmetry":        ( 67, 160,  71),
    "pressure_outlet": (251, 140,   0),
    "velocity_inlet":  (  0, 172, 193),
    "moving_wall":     (142,  36, 170),
    "interface":       (253, 216,  53),
    "empty":           (117, 117, 117),
    # advanced (BETA2800).
    "periodic":        ( 33, 150, 243),
    "cyclic_ami":      ( 26, 118, 210),
    "interface_heat":  (255, 152,   0),
    "sliding_mesh":    (156,  39, 176),
    "fan":             (236,  64, 122),
    "porous_jump":     (109,  76,  65),
    "wedge":           (  0, 121, 107),
    "mass_flow_inlet": (255, 193,   7),
    "outflow":         (200,  50,  50),
}


def get_bc_color(bc_type: str) -> tuple[int, int, int]:
    """BC type → default RGB."""
    return BC_COLOR_MAP.get(bc_type, (180, 180, 180))


def render_bc_overlay(
    plotter,
    surface_mesh,
    bc_manager,
    *,
    opacity: float = 0.7,
    show_edges: bool = True,
) -> list:
    """BCManager assignments 를 surface mesh 위 색상 overlay 로 표시.

    Args:
        plotter: pyvistaqt.QtInteractor or pv.Plotter.
        surface_mesh: pv.PolyData of boundary tris (cell ids = face_indices basis).
        bc_manager: BCManager.
        opacity: overlay 투명도.
        show_edges: edge 표시 여부.

    Returns:
        list of actor handles (caller 가 remove 시 사용).
    """
    actors = []
    try:
        import pyvista as pv
    except ImportError:
        return actors

    if surface_mesh is None or bc_manager is None:
        return actors

    for ba in bc_manager.assignments:
        if not ba.face_indices:
            continue
        try:
            ids = np.asarray(ba.face_indices, dtype=np.int64)
            valid = ids[ids < surface_mesh.n_cells]
            if valid.size == 0:
                continue
            sub = surface_mesh.extract_cells(valid)
            color = ba.color if ba.color != (200, 200, 200) else get_bc_color(ba.bc_type)
            actor = plotter.add_mesh(
                sub,
                color=tuple(c / 255 for c in color),
                opacity=float(opacity),
                show_edges=bool(show_edges),
                edge_color="white",
                line_width=1,
                pickable=False,
                name=f"bc_overlay_{ba.name}",
                label=f"{ba.name} ({ba.bc_type})",
            )
            actors.append(actor)
        except Exception:
            continue

    return actors


def remove_bc_overlay(plotter, actors: list) -> int:
    """기존 overlay actor 제거.

    Returns: 제거된 actor 수.
    """
    n = 0
    if plotter is None or not actors:
        return 0
    for a in actors:
        try:
            plotter.remove_actor(a)
            n += 1
        except Exception:
            continue
    return n


def patch_color_legend(bc_manager) -> list[tuple[str, str, tuple[int, int, int]]]:
    """legend 표시용 list[(patch_name, bc_type, rgb)]."""
    out = []
    if bc_manager is None:
        return out
    for ba in bc_manager.assignments:
        c = ba.color if ba.color != (200, 200, 200) else get_bc_color(ba.bc_type)
        out.append((ba.name, ba.bc_type, c))
    return out
