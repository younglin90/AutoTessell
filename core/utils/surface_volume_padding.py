"""Explicit OpenFOAM writer around native planar-surface padding kernel.

Numerical validation, plane detection, edge sizing, extrusion, and cell
connectivity are executed by ``native_surface_padding`` C++ extension.  No
surface format calls this module implicitly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from core.generator.polymesh_writer import write_generic_polymesh
from core.utils.logging import get_logger
from core.utils.native_extensions import import_native_extension

log = get_logger(__name__)

AxisName = Literal["x", "y", "z"]
PlaneName = Literal["xy", "xz", "yz"]
_NATIVE_MODULE: Any | None = None
_NATIVE_IMPORT_ATTEMPTED = False


class SurfacePaddingReport(BaseModel):
    """Audit record returned by native padding kernel."""

    model_config = ConfigDict(frozen=True)

    normal_axis: AxisName
    plane: PlaneName
    direction: Literal[-1, 1]
    padding_thickness: float = Field(gt=0.0)
    source_tri_faces: int = Field(ge=0)
    source_quad_faces: int = Field(ge=0)
    prism_cells: int = Field(ge=0)
    hex_cells: int = Field(ge=0)

    @property
    def volume_cells(self) -> int:
        return self.prism_cells + self.hex_cells


@dataclass(frozen=True)
class PaddedSurfaceVolume:
    """Native padded vertices and outward-facing OpenFOAM cell faces."""

    vertices: np.ndarray
    cell_faces: tuple[tuple[tuple[int, ...], ...], ...]
    report: SurfacePaddingReport


def _load_native_surface_padding() -> Any:
    """Load project-local native kernel, adding configured build directory once."""
    global _NATIVE_MODULE, _NATIVE_IMPORT_ATTEMPTED
    if _NATIVE_IMPORT_ATTEMPTED:
        if _NATIVE_MODULE is None:
            raise RuntimeError(
                "native_surface_padding is unavailable; build auto_tessell_core target "
                "native_surface_padding first"
            )
        return _NATIVE_MODULE
    _NATIVE_IMPORT_ATTEMPTED = True

    try:
        _NATIVE_MODULE = import_native_extension("native_surface_padding")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "native_surface_padding is unavailable; build auto_tessell_core target "
            "native_surface_padding first"
        ) from exc
    return _NATIVE_MODULE


def pad_axis_aligned_surface_to_volume(
    vertices: np.ndarray | Sequence[Sequence[float]],
    faces: Sequence[Sequence[int]],
    *,
    direction: Literal[-1, 1] = 1,
    tolerance: float = 1e-9,
) -> PaddedSurfaceVolume:
    """Explicitly call native kernel to extrude one planar surface layer."""
    native = _load_native_surface_padding()
    result = native.pad_axis_aligned_surface_to_volume(
        np.asarray(vertices, dtype=np.float64),
        faces,
        direction,
        tolerance,
    )
    return PaddedSurfaceVolume(
        vertices=np.asarray(result["vertices"], dtype=np.float64),
        cell_faces=tuple(
            tuple(tuple(int(index) for index in face) for face in cell)
            for cell in result["cell_faces"]
        ),
        report=SurfacePaddingReport.model_validate(dict(result["report"])),
    )


def write_padded_surface_to_openfoam(
    vertices: np.ndarray | Sequence[Sequence[float]],
    faces: Sequence[Sequence[int]],
    case_dir: Path,
    *,
    direction: Literal[-1, 1] = 1,
    tolerance: float = 1e-9,
    patch_name: str = "paddedSurfaceWall",
    patch_type: str = "wall",
) -> SurfacePaddingReport:
    """Explicitly write one native-padded surface layer as OpenFOAM polyMesh."""
    padded = pad_axis_aligned_surface_to_volume(
        vertices,
        faces,
        direction=direction,
        tolerance=tolerance,
    )
    stats = write_generic_polymesh(
        padded.vertices,
        padded.cell_faces,
        case_dir,
        patch_name=patch_name,
        patch_type=patch_type,
    )
    if stats["num_cells"] != padded.report.volume_cells:
        raise RuntimeError(
            "OpenFOAM writer dropped padded cells: "
            f"expected {padded.report.volume_cells}, wrote {stats['num_cells']}"
        )
    log.info(
        "surface_volume_padding_exported",
        case_dir=str(case_dir),
        plane=padded.report.plane,
        direction=padded.report.direction,
        thickness=padded.report.padding_thickness,
        prism_cells=padded.report.prism_cells,
        hex_cells=padded.report.hex_cells,
    )
    return padded.report
