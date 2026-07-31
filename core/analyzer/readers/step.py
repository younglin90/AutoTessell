"""Native STEP/IGES/BREP reader (v0.4.0-beta53).

OCP (OpenCASCADE Python bindings) 를 **직접** 호출해 BRepMesh 로 tessellate.
cadquery wrapper layer 를 건너뛰어 의존 체인을 축소한다.

OCP 는 cadquery 가 내부에서 사용하는 같은 C++ OpenCASCADE 라이브러리 바인딩.
OCP 가 미설치되면 graceful fallback 을 위해 ImportError 를 raise (file_reader
상위에서 cadquery / gmsh 로 이어간다).

완전 native ISO 10303 STEP parser 는 v1.0 로드맵 (연구급 작업, 수개월).
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np

from core.utils.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class CadEntityProvenance:
    """Read-only B-Rep authority carried beside the legacy triangle stream."""

    status: str
    face_count: int
    topological_edge_count: int
    triangle_face_ordinals: np.ndarray
    triangle_orientation_reversed: np.ndarray
    seam_vertex_ids: np.ndarray
    canonical_vertex_source_ids: np.ndarray
    oriented_canonical_faces: np.ndarray
    face_names: tuple[str | None, ...]
    physical_group_names: tuple[str | None, ...]
    face_ordinals_authoritative: bool
    face_orientation_authoritative: bool
    seam_connectivity_authoritative: bool
    physical_groups_authoritative: bool
    ordered_triangle_coordinate_sha256: str
    ordered_face_ordinal_sha256: str
    ordered_orientation_sha256: str
    seam_connectivity_sha256: str


@dataclass(frozen=True)
class CadNativeTriangulation:
    """Legacy arrays plus an optional, immutable provenance side payload."""

    vertices: np.ndarray
    faces: np.ndarray
    provenance: CadEntityProvenance


class _DisjointSet:
    """Small deterministic union-find for B-Rep-authoritative seam nodes."""

    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, value: int) -> int:
        parent = self._parent
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(self, first: int, second: int) -> None:
        first_root = self.find(first)
        second_root = self.find(second)
        if first_root != second_root:
            parent, child = sorted((first_root, second_root))
            self._parent[child] = parent


def _readonly(array: np.ndarray) -> np.ndarray:
    array.setflags(write=False)
    return array


def _array_sha256(array: np.ndarray, dtype: str) -> str:
    return sha256(np.ascontiguousarray(array, dtype=dtype).tobytes()).hexdigest()


def load_cad_native(path: Path, fmt: str) -> tuple[np.ndarray, np.ndarray]:
    """OCP 로 STEP/IGES/BREP 파일을 tessellate 하여 (vertices, faces) 반환.

    Args:
        path: 입력 파일 경로.
        fmt: 확장자 (``.step`` / ``.stp`` / ``.iges`` / ``.igs`` / ``.brep``).

    Returns:
        ``(vertices (N,3) float64, faces (M,3) int64)``.

    Raises:
        ImportError: OCP 미설치.
        ValueError: 로딩/테셀레이션 실패.
    """
    try:
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.BRepTools import BRepTools
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.IGESControl import IGESControl_Reader
        from OCP.STEPControl import STEPControl_Reader
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS, TopoDS_Shape
    except ImportError as exc:
        raise ImportError(
            "OCP (python-occ) 미설치 — native CAD reader 사용 불가.\n"
            "pip install cadquery-ocp 또는 pip install OCP 를 시도하거나, "
            "cadquery / gmsh fallback 을 사용하세요."
        ) from exc

    ext = fmt.lstrip(".").lower()
    shape: Any = None

    if ext in ("step", "stp"):
        reader = STEPControl_Reader()
        status = reader.ReadFile(str(path))
        if status != IFSelect_RetDone:
            raise ValueError(f"STEP 파일 파싱 실패: {path}")
        reader.TransferRoots()
        shape = reader.OneShape()
    elif ext in ("iges", "igs"):
        reader = IGESControl_Reader()
        status = reader.ReadFile(str(path))
        if status != IFSelect_RetDone:
            raise ValueError(f"IGES 파일 파싱 실패: {path}")
        reader.TransferRoots()
        shape = reader.OneShape()
    elif ext == "brep":
        builder = BRep_Builder()
        shape = TopoDS_Shape()
        success = BRepTools.Read_s(shape, str(path), builder)
        if not success:
            raise ValueError(f"BREP 파일 파싱 실패: {path}")
    else:
        raise ValueError(f"지원하지 않는 CAD 확장자: {fmt}")

    # BRepMesh 로 tessellate (linear deflection, angular deflection)
    BRepMesh_IncrementalMesh(shape, 0.01, False, 0.1, True)

    # 모든 Face 를 순회해 triangulation 추출
    vertices_list: list[tuple[float, float, float]] = []
    faces_list: list[tuple[int, int, int]] = []
    vert_offset = 0

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face_shape = explorer.Current()
        face = TopoDS.Face_s(face_shape)  # TopoDS_Shape → TopoDS_Face 캐스팅
        loc = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, loc)
        if triangulation is None:
            explorer.Next()
            continue
        trsf = loc.Transformation()

        # Nodes
        n_nodes = triangulation.NbNodes()
        for i in range(1, n_nodes + 1):  # OCC 1-based
            pt = triangulation.Node(i).Transformed(trsf)
            vertices_list.append((pt.X(), pt.Y(), pt.Z()))

        # Triangles
        n_tri = triangulation.NbTriangles()
        for i in range(1, n_tri + 1):
            tri = triangulation.Triangle(i)
            a, b, c = tri.Get()
            # OCC 1-based → 0-based + offset
            faces_list.append(
                (
                    vert_offset + a - 1,
                    vert_offset + b - 1,
                    vert_offset + c - 1,
                )
            )
        vert_offset += n_nodes
        explorer.Next()

    if not vertices_list or not faces_list:
        raise ValueError(f"테셀레이션 결과가 비어있음: {path}")

    V = np.array(vertices_list, dtype=np.float64)
    F = np.array(faces_list, dtype=np.int64)

    log.info(
        "cad_loaded_via_ocp_native",
        path=str(path),
        fmt=ext,
        num_vertices=V.shape[0],
        num_faces=F.shape[0],
    )
    return V, F


def load_cad_native_with_provenance(path: Path, fmt: str) -> CadNativeTriangulation:
    """Return the unchanged legacy arrays with authoritative B-Rep metadata.

    This API deliberately performs a second, read-only OCP traversal after
    :func:`load_cad_native`.  Keeping the legacy implementation untouched
    protects its coordinate and triangle-order byte contract.  The second
    traversal must match that stream exactly or this function fails closed.

    Surface identities are deterministic ordinals of actual B-Rep faces.
    Shared triangulation nodes are joined only when the same topological B-Rep
    edge exposes the same IEEE-754 coordinate; unrelated coincident geometry
    is never welded.  STEPControl does not expose XDE names or physical groups,
    so those authority flags remain false instead of inventing labels.
    """
    vertices, faces = load_cad_native(path, fmt)
    try:
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.BRepTools import BRepTools
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.IGESControl import IGESControl_Reader
        from OCP.STEPControl import STEPControl_Reader
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED
        from OCP.TopExp import TopExp, TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS, TopoDS_Shape
        from OCP.TopTools import TopTools_IndexedMapOfShape
    except ImportError as exc:
        raise ImportError("OCP provenance traversal unavailable") from exc

    ext = fmt.lstrip(".").lower()
    shape: Any
    if ext in ("step", "stp"):
        reader = STEPControl_Reader()
        if reader.ReadFile(str(path)) != IFSelect_RetDone:
            raise ValueError(f"STEP provenance parsing failed: {path}")
        reader.TransferRoots()
        shape = reader.OneShape()
    elif ext in ("iges", "igs"):
        reader = IGESControl_Reader()
        if reader.ReadFile(str(path)) != IFSelect_RetDone:
            raise ValueError(f"IGES provenance parsing failed: {path}")
        reader.TransferRoots()
        shape = reader.OneShape()
    elif ext == "brep":
        builder = BRep_Builder()
        shape = TopoDS_Shape()
        if not BRepTools.Read_s(shape, str(path), builder):
            raise ValueError(f"BREP provenance parsing failed: {path}")
    else:
        raise ValueError(f"unsupported CAD provenance extension: {fmt}")

    BRepMesh_IncrementalMesh(shape, 0.01, False, 0.1, True)
    edge_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_EDGE, edge_map)

    face_ordinals: list[int] = []
    orientation_reversed: list[bool] = []
    seam_records: dict[tuple[int, bytes], list[int]] = {}
    edge_occurrences: dict[int, list[tuple[bytes, ...]]] = {}
    vertex_offset = 0
    triangle_offset = 0
    face_ordinal = 0
    missing_edge_polygons = 0

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is None:
            explorer.Next()
            continue
        transformation = location.Transformation()
        node_count = triangulation.NbNodes()
        triangle_count = triangulation.NbTriangles()
        local_coordinates: list[tuple[float, float, float]] = []
        for node_index in range(1, node_count + 1):
            point = triangulation.Node(node_index).Transformed(transformation)
            local_coordinates.append((point.X(), point.Y(), point.Z()))
        expected_vertices = np.asarray(local_coordinates, dtype=np.float64)
        if not np.array_equal(
            vertices[vertex_offset : vertex_offset + node_count], expected_vertices
        ):
            raise ValueError("CAD provenance traversal changed the legacy vertex stream")

        local_faces: list[tuple[int, int, int]] = []
        for triangle_index in range(1, triangle_count + 1):
            first, second, third = triangulation.Triangle(triangle_index).Get()
            local_faces.append(
                (
                    vertex_offset + first - 1,
                    vertex_offset + second - 1,
                    vertex_offset + third - 1,
                )
            )
        expected_faces = np.asarray(local_faces, dtype=np.int64)
        if not np.array_equal(
            faces[triangle_offset : triangle_offset + triangle_count], expected_faces
        ):
            raise ValueError("CAD provenance traversal changed the legacy triangle stream")

        reversed_face = face.Orientation() == TopAbs_REVERSED
        face_ordinals.extend([face_ordinal] * triangle_count)
        orientation_reversed.extend([reversed_face] * triangle_count)

        edge_explorer = TopExp_Explorer(face, TopAbs_EDGE)
        while edge_explorer.More():
            edge = TopoDS.Edge_s(edge_explorer.Current())
            edge_ordinal = edge_map.FindIndex(edge)
            polygon = BRep_Tool.PolygonOnTriangulation_s(edge, triangulation, location)
            if edge_ordinal <= 0 or polygon is None:
                missing_edge_polygons += 1
                edge_explorer.Next()
                continue
            occurrence: list[bytes] = []
            for local_node in polygon.Nodes():
                coordinate_key = np.asarray(
                    local_coordinates[int(local_node) - 1], dtype="<f8"
                ).tobytes()
                occurrence.append(coordinate_key)
                key = (int(edge_ordinal), coordinate_key)
                seam_records.setdefault(key, []).append(vertex_offset + int(local_node) - 1)
            edge_occurrences.setdefault(int(edge_ordinal), []).append(tuple(sorted(occurrence)))
            edge_explorer.Next()

        vertex_offset += node_count
        triangle_offset += triangle_count
        face_ordinal += 1
        explorer.Next()

    if vertex_offset != len(vertices) or triangle_offset != len(faces):
        raise ValueError("CAD provenance traversal did not cover the legacy arrays")
    incompatible_edges = sum(
        any(occurrence != occurrences[0] for occurrence in occurrences[1:])
        for occurrences in edge_occurrences.values()
    )
    if missing_edge_polygons or incompatible_edges:
        raise ValueError(
            "CAD B-Rep seam authority incomplete: "
            f"missing_polygons={missing_edge_polygons}, "
            f"incompatible_edges={incompatible_edges}"
        )

    disjoint = _DisjointSet(len(vertices))
    for records in seam_records.values():
        for record in records[1:]:
            disjoint.union(records[0], record)
    roots = [disjoint.find(index) for index in range(len(vertices))]
    canonical_by_root: dict[int, int] = {}
    canonical_sources: list[int] = []
    seam_vertex_ids: np.ndarray = np.empty(len(vertices), dtype=np.int64)
    for source, root in enumerate(roots):
        canonical = canonical_by_root.get(root)
        if canonical is None:
            canonical = len(canonical_sources)
            canonical_by_root[root] = canonical
            canonical_sources.append(source)
        seam_vertex_ids[source] = canonical

    face_ordinal_array = np.asarray(face_ordinals, dtype=np.int64)
    reversed_array = np.asarray(orientation_reversed, dtype=np.bool_)
    oriented_faces = faces.copy()
    oriented_faces[reversed_array] = oriented_faces[reversed_array][:, (0, 2, 1)]
    canonical_faces = seam_vertex_ids[oriented_faces]
    canonical_source_array = np.asarray(canonical_sources, dtype=np.int64)
    triangle_coordinates = vertices[faces]
    physical_groups_authoritative = False
    provenance = CadEntityProvenance(
        status="partial_authority_physical_groups_unavailable",
        face_count=face_ordinal,
        topological_edge_count=int(edge_map.Extent()),
        triangle_face_ordinals=_readonly(face_ordinal_array),
        triangle_orientation_reversed=_readonly(reversed_array),
        seam_vertex_ids=_readonly(seam_vertex_ids),
        canonical_vertex_source_ids=_readonly(canonical_source_array),
        oriented_canonical_faces=_readonly(canonical_faces),
        face_names=(None,) * face_ordinal,
        physical_group_names=(None,) * face_ordinal,
        face_ordinals_authoritative=True,
        face_orientation_authoritative=True,
        seam_connectivity_authoritative=True,
        physical_groups_authoritative=physical_groups_authoritative,
        ordered_triangle_coordinate_sha256=_array_sha256(triangle_coordinates, "<f8"),
        ordered_face_ordinal_sha256=_array_sha256(face_ordinal_array, "<i8"),
        ordered_orientation_sha256=_array_sha256(reversed_array, "u1"),
        seam_connectivity_sha256=_array_sha256(canonical_faces, "<i8"),
    )
    return CadNativeTriangulation(vertices, faces, provenance)
