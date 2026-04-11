"""VTK/ParaView 포맷 내보내기 + 품질 컬러맵 시각화.

생성된 메쉬를 VTK 포맷으로 내보내고, 셀 품질(non-orthogonality, skewness 등)을
스칼라 필드로 첨부하여 ParaView에서 시각화할 수 있게 한다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.utils.logging import get_logger
from core.utils.polymesh_reader import (
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

log = get_logger(__name__)


def export_vtk(
    case_dir: Path,
    output_path: Path | None = None,
    include_quality: bool = True,
) -> Path | None:
    """polyMesh를 VTK UnstructuredGrid (.vtu) 포맷으로 내보낸다.

    Args:
        case_dir: OpenFOAM case 디렉터리.
        output_path: 출력 .vtu 파일 경로 (None이면 case_dir/mesh.vtu).
        include_quality: True이면 셀 품질 필드를 포함.

    Returns:
        생성된 .vtu 파일 경로. 실패 시 None.
    """
    poly_dir = case_dir / "constant" / "polyMesh"
    if not poly_dir.exists():
        log.warning("vtk_export_no_polymesh", case_dir=str(case_dir))
        return None

    try:
        points = np.array(parse_foam_points(poly_dir / "points"))
        faces = parse_foam_faces(poly_dir / "faces")
        owner = np.array(parse_foam_labels(poly_dir / "owner"))
        neighbour = np.array(parse_foam_labels(poly_dir / "neighbour"))
    except Exception as exc:
        log.warning("vtk_export_parse_failed", error=str(exc))
        return None

    if len(points) == 0 or len(faces) == 0:
        return None

    n_internal = len(neighbour)
    max_cell = int(owner.max()) if len(owner) > 0 else -1
    if len(neighbour) > 0:
        max_cell = max(max_cell, int(neighbour.max()))
    n_cells = max_cell + 1

    # 셀 → 면 → 정점 매핑으로 셀 정점 집합 구성
    cell_verts: list[list[int]] = [[] for _ in range(n_cells)]
    for face_idx, face in enumerate(faces):
        cell_id = int(owner[face_idx])
        for v in face:
            if v not in cell_verts[cell_id]:
                cell_verts[cell_id].append(v)
        if face_idx < n_internal:
            nbr_id = int(neighbour[face_idx])
            for v in face:
                if v not in cell_verts[nbr_id]:
                    cell_verts[nbr_id].append(v)

    # VTU XML 생성
    out = output_path or (case_dir / "mesh.vtu")

    try:
        _write_vtu(out, points, cell_verts, faces, owner, neighbour, n_cells, n_internal,
                   include_quality)
        log.info("vtk_exported", path=str(out), n_cells=n_cells)
        return out
    except Exception as exc:
        log.warning("vtk_export_write_failed", error=str(exc))
        return None


def _write_vtu(
    path: Path,
    points: np.ndarray,
    cell_verts: list[list[int]],
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_cells: int,
    n_internal: int,
    include_quality: bool,
) -> None:
    """VTK UnstructuredGrid XML (.vtu) 파일을 작성한다."""
    n_points = len(points)

    # Connectivity + offsets + types
    connectivity: list[int] = []
    offsets: list[int] = []
    types: list[int] = []
    offset = 0

    for cell in cell_verts:
        n_verts = len(cell)
        connectivity.extend(cell)
        offset += n_verts
        offsets.append(offset)

        # VTK cell type
        if n_verts == 4:
            types.append(10)  # VTK_TETRA
        elif n_verts == 8:
            types.append(12)  # VTK_HEXAHEDRON
        elif n_verts == 6:
            types.append(13)  # VTK_WEDGE
        elif n_verts == 5:
            types.append(14)  # VTK_PYRAMID
        else:
            types.append(42)  # VTK_POLYHEDRON (fallback)

    vtk_index_type = _select_vtk_index_type(connectivity, offsets)
    if vtk_index_type == "Int64":
        log.info("vtk_export_using_int64_indices", reason="index_out_of_int32_range")

    # Quality fields
    quality_fields: dict[str, np.ndarray] = {}
    if include_quality:
        quality_fields = _compute_quality_fields(
            points, faces, owner, neighbour, n_cells, n_internal
        )

    # Write XML
    lines: list[str] = [
        '<?xml version="1.0"?>',
        '<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian">',
        '  <UnstructuredGrid>',
        f'    <Piece NumberOfPoints="{n_points}" NumberOfCells="{n_cells}">',
    ]

    # Points
    lines.append('      <Points>')
    lines.append('        <DataArray type="Float64" NumberOfComponents="3" format="ascii">')
    for p in points:
        lines.append(f'          {p[0]:.10g} {p[1]:.10g} {p[2]:.10g}')
    lines.append('        </DataArray>')
    lines.append('      </Points>')

    # Cells
    lines.append('      <Cells>')
    lines.append(f'        <DataArray type="{vtk_index_type}" Name="connectivity" format="ascii">')
    lines.append('          ' + ' '.join(str(c) for c in connectivity))
    lines.append('        </DataArray>')
    lines.append(f'        <DataArray type="{vtk_index_type}" Name="offsets" format="ascii">')
    lines.append('          ' + ' '.join(str(o) for o in offsets))
    lines.append('        </DataArray>')
    lines.append('        <DataArray type="UInt8" Name="types" format="ascii">')
    lines.append('          ' + ' '.join(str(t) for t in types))
    lines.append('        </DataArray>')
    lines.append('      </Cells>')

    # Cell quality data
    if quality_fields:
        lines.append('      <CellData>')
        for name, values in quality_fields.items():
            lines.append(f'        <DataArray type="Float64" Name="{name}" format="ascii">')
            lines.append('          ' + ' '.join(f'{v:.6g}' for v in values))
            lines.append('        </DataArray>')
        lines.append('      </CellData>')

    lines.append('    </Piece>')
    lines.append('  </UnstructuredGrid>')
    lines.append('</VTKFile>')

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines))


def _select_vtk_index_type(connectivity: list[int], offsets: list[int]) -> str:
    """VTK 인덱스 배열 타입(Int32/Int64)을 값 범위에 맞춰 선택한다."""
    int32 = np.iinfo(np.int32)
    for values in (connectivity, offsets):
        if not values:
            continue
        arr = np.asarray(values, dtype=np.int64)
        if arr.min() < int32.min or arr.max() > int32.max:
            return "Int64"
    return "Int32"


def _compute_quality_fields(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_cells: int,
    n_internal: int,
) -> dict[str, np.ndarray]:
    """셀별 품질 필드를 계산한다 (ParaView 시각화용)."""
    fields: dict[str, np.ndarray] = {}

    # Face centres + normals
    n_faces = len(faces)
    face_centres = np.zeros((n_faces, 3))
    face_normals = np.zeros((n_faces, 3))

    for i, face in enumerate(faces):
        if len(face) < 3:
            continue
        verts = points[face]
        face_centres[i] = verts.mean(axis=0)
        v0 = verts[0]
        area_vec = np.zeros(3)
        for k in range(1, len(face) - 1):
            area_vec += np.cross(verts[k] - v0, verts[k + 1] - v0)
        mag = np.linalg.norm(area_vec)
        if mag > 0:
            face_normals[i] = area_vec / mag

    # Cell centres
    cell_centres = np.zeros((n_cells, 3))
    cell_counts = np.zeros(n_cells)
    np.add.at(cell_centres, owner, face_centres)
    np.add.at(cell_counts, owner, 1)
    if n_internal > 0:
        np.add.at(cell_centres, neighbour, face_centres[:n_internal])
        np.add.at(cell_counts, neighbour, 1)
    nonzero = cell_counts > 0
    cell_centres[nonzero] /= cell_counts[nonzero, np.newaxis]

    # Non-orthogonality per cell (max among internal faces)
    non_ortho = np.zeros(n_cells)
    if n_internal > 0:
        own = owner[:n_internal]
        nbr = neighbour[:n_internal]
        d = cell_centres[nbr] - cell_centres[own]
        d_mag = np.linalg.norm(d, axis=1)
        n_hat = face_normals[:n_internal]
        n_mag = np.linalg.norm(n_hat, axis=1)
        valid = (d_mag > 1e-30) & (n_mag > 1e-30)
        cos_theta = np.zeros(n_internal)
        cos_theta[valid] = np.einsum('ij,ij->i', d[valid], n_hat[valid]) / (d_mag[valid] * n_mag[valid])
        cos_theta = np.clip(cos_theta, -1, 1)
        angles = np.degrees(np.arccos(np.abs(cos_theta)))
        np.maximum.at(non_ortho, own, angles)
        np.maximum.at(non_ortho, nbr, angles)
    fields["NonOrthogonality"] = non_ortho

    # Cell volume (divergence theorem)
    face_areas = np.linalg.norm(
        np.array([np.cross(points[f[1]] - points[f[0]], points[f[2]] - points[f[0]])
                  if len(f) >= 3 else np.zeros(3) for f in faces]),
        axis=1,
    ) * 0.5
    contribution = np.einsum('ij,ij->i', face_centres, face_normals) * face_areas
    volumes = np.zeros(n_cells)
    np.add.at(volumes, owner, contribution)
    if n_internal > 0:
        np.subtract.at(volumes, neighbour, contribution[:n_internal])
    volumes /= 3.0
    fields["CellVolume"] = np.abs(volumes)

    return fields
