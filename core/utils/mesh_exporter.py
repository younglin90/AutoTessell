"""CFD 솔버 포맷 내보내기 — polyMesh → SU2, Fluent, CGNS.

meshio를 활용해 생성된 OpenFOAM polyMesh를 다양한 CFD 솔버 포맷으로 변환한다.
지원 포맷: SU2(.su2), ANSYS Fluent(.msh), CGNS(.cgns)
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np

from core.utils.logging import get_logger
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

log = get_logger(__name__)

SupportedFormat = Literal["su2", "fluent", "cgns"]

_FORMAT_EXTENSIONS: dict[str, str] = {
    "su2": ".su2",
    "fluent": ".msh",
    "cgns": ".cgns",
}

_MESHIO_FORMAT: dict[str, str] = {
    "su2": "su2",
    "fluent": "fluent",
    "cgns": "cgns",
}


def export_mesh(
    case_dir: Path,
    output_path: Path | None = None,
    fmt: SupportedFormat = "su2",
) -> Path | None:
    """polyMesh를 지정된 CFD 솔버 포맷으로 내보낸다.

    Args:
        case_dir: OpenFOAM case 디렉터리. ``constant/polyMesh`` 하위 파일 사용.
        output_path: 출력 파일 경로 (None이면 case_dir/<mesh>.<ext>).
        fmt: 출력 포맷 — 'su2' | 'fluent' | 'cgns'.

    Returns:
        생성된 파일 경로. 실패 시 None.
    """
    try:
        import meshio  # noqa: F401
    except ImportError:
        log.error("mesh_exporter_meshio_missing", hint="pip install meshio")
        return None

    poly_dir = case_dir / "constant" / "polyMesh"
    if not poly_dir.exists():
        log.warning("mesh_exporter_no_polymesh", case_dir=str(case_dir))
        return None

    try:
        points_raw = parse_foam_points(poly_dir / "points")
        faces = parse_foam_faces(poly_dir / "faces")
        owner = parse_foam_labels(poly_dir / "owner")
        neighbour = parse_foam_labels(poly_dir / "neighbour")
    except Exception as exc:
        log.warning("mesh_exporter_parse_failed", error=str(exc))
        return None

    points = np.array(points_raw, dtype=np.float64)
    owner_arr = np.array(owner, dtype=np.int64)
    neighbour_arr = np.array(neighbour, dtype=np.int64)

    # 셀 → 면 매핑으로 셀 정점 집합 구성
    n_internal = len(neighbour_arr)
    max_cell = int(owner_arr.max()) if len(owner_arr) > 0 else -1
    if len(neighbour_arr) > 0:
        max_cell = max(max_cell, int(neighbour_arr.max()))
    n_cells = max_cell + 1

    cell_verts: list[set[int]] = [set() for _ in range(n_cells)]
    for face_idx, face in enumerate(faces):
        cell_id = int(owner_arr[face_idx])
        cell_verts[cell_id].update(face)
        if face_idx < n_internal:
            nbr_id = int(neighbour_arr[face_idx])
            cell_verts[nbr_id].update(face)

    # meshio 셀 블록 구성 (tet/hex/wedge/pyramid/polyhedron 분리)
    tet_cells: list[list[int]] = []
    hex_cells: list[list[int]] = []
    wedge_cells: list[list[int]] = []
    pyramid_cells: list[list[int]] = []
    poly_cells: list[list[int]] = []

    for verts in cell_verts:
        vlist = sorted(verts)
        n = len(vlist)
        if n == 4:
            tet_cells.append(vlist)
        elif n == 8:
            hex_cells.append(vlist)
        elif n == 6:
            wedge_cells.append(vlist)
        elif n == 5:
            pyramid_cells.append(vlist)
        else:
            poly_cells.append(vlist[:8] if n > 8 else vlist)  # fallback: 첫 8정점

    import meshio

    cells = []
    if tet_cells:
        cells.append(meshio.CellBlock("tetra", np.array(tet_cells, dtype=np.int64)))
    if hex_cells:
        cells.append(meshio.CellBlock("hexahedron", np.array(hex_cells, dtype=np.int64)))
    if wedge_cells:
        cells.append(meshio.CellBlock("wedge", np.array(wedge_cells, dtype=np.int64)))
    if pyramid_cells:
        cells.append(meshio.CellBlock("pyramid", np.array(pyramid_cells, dtype=np.int64)))
    if poly_cells:
        # polyhedron은 SU2/CGNS에서 직접 지원 안 되므로 hex fallback으로 패딩
        arr = np.zeros((len(poly_cells), 8), dtype=np.int64)
        for i, v in enumerate(poly_cells):
            arr[i, : len(v)] = v
            arr[i, len(v) :] = v[-1]  # 마지막 정점으로 패딩
        cells.append(meshio.CellBlock("hexahedron", arr))

    if not cells:
        log.warning("mesh_exporter_no_cells", n_cells=n_cells)
        return None

    mesh = meshio.Mesh(points=points, cells=cells)

    ext = _FORMAT_EXTENSIONS[fmt]
    out = output_path or (case_dir / f"mesh{ext}")

    try:
        meshio.write(str(out), mesh, file_format=_MESHIO_FORMAT[fmt])
        log.info("mesh_exported", fmt=fmt, path=str(out), n_cells=n_cells)
        return out
    except Exception as exc:
        log.warning("mesh_export_write_failed", fmt=fmt, error=str(exc))
        return None
