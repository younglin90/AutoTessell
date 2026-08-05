"""Native STEP/IGES/BREP reader (v0.4.0-beta53).

OCP (OpenCASCADE Python bindings) 를 **직접** 호출해 BRepMesh 로 tessellate.
cadquery wrapper layer 를 건너뛰어 의존 체인을 축소한다.

OCP 는 cadquery 가 내부에서 사용하는 같은 C++ OpenCASCADE 라이브러리 바인딩.
OCP 가 미설치되면 graceful fallback 을 위해 ImportError 를 raise (file_reader
상위에서 cadquery / gmsh 로 이어간다).

완전 native ISO 10303 STEP parser 는 v1.0 로드맵 (연구급 작업, 수개월).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

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
    xde_layer_names: tuple[tuple[str, ...], ...]
    xde_surface_colors: tuple[tuple[float, float, float] | None, ...]
    xde_assembly_paths: tuple[tuple[str, ...] | None, ...]
    xde_layer_authoritative: bool
    xde_layer_coverage_count: int
    xde_color_display_metadata_authoritative: bool
    xde_assembly_identity_authoritative: bool
    face_ordinals_authoritative: bool
    face_orientation_authoritative: bool
    seam_connectivity_authoritative: bool
    physical_groups_authoritative: bool
    ordered_triangle_coordinate_sha256: str
    ordered_face_ordinal_sha256: str
    ordered_orientation_sha256: str
    seam_connectivity_sha256: str
    xde_metadata_sha256: str
    triangle_brep_edge_ids: np.ndarray | None = None
    triangle_brep_edge_segment_ids: np.ndarray | None = None
    triangle_brep_edge_segment_parameters: np.ndarray | None = None
    brep_edge_face_direction_records: tuple[dict[str, Any], ...] | None = None


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
        from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Curve2d, BRepAdaptor_Surface
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


def load_cad_native_with_provenance(
    path: Path, fmt: str, *, mesh_domain_side_by_face: Mapping[int, int] | None = None
) -> CadNativeTriangulation:
    """Return the unchanged legacy arrays with authoritative B-Rep metadata.

    This API deliberately performs a second, read-only OCP traversal after
    :func:`load_cad_native`.  Keeping the legacy implementation untouched
    protects its coordinate and triangle-order byte contract.  The second
    traversal must match that stream exactly or this function fails closed.

    Surface identities are deterministic ordinals of actual B-Rep faces.
    Shared triangulation nodes are joined only when the same topological B-Rep
    edge exposes the same IEEE-754 coordinate; unrelated coincident geometry
    is never welded. STEPCAF/XDE supplies optional layer, display-color, and
    assembly identity metadata. None is promoted to physical-group or boundary-
    condition meaning without a separate explicit user/import mapping contract.
    """
    vertices, faces = load_cad_native(path, fmt)
    try:
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Curve2d, BRepAdaptor_Surface
        from OCP.BRepTopAdaptor import BRepTopAdaptor_FClass2d
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.BRepTools import BRepTools
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.IGESControl import IGESControl_Reader
        from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
        from OCP.STEPCAFControl import STEPCAFControl_Reader
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDF import TDF_AttributeIterator, TDF_Label, TDF_LabelSequence
        from OCP.TDocStd import TDocStd_Document
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED, TopAbs_IN, TopAbs_OUT, TopAbs_ON, TopAbs_UNKNOWN
        from OCP.TopExp import TopExp, TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS, TopoDS_Shape
        from OCP.gp import gp_Pnt, gp_Pnt2d, gp_Vec, gp_Vec2d
        from OCP.TopTools import TopTools_IndexedMapOfShape
        from OCP.XCAFDoc import XCAFDoc_ColorSurf, XCAFDoc_DocumentTool
    except ImportError as exc:
        raise ImportError("OCP provenance traversal unavailable") from exc

    ext = fmt.lstrip(".").lower()
    shape: Any
    xde_document: Any = None
    if ext in ("step", "stp"):
        reader = STEPCAFControl_Reader()
        reader.SetNameMode(True)
        reader.SetLayerMode(True)
        reader.SetColorMode(True)
        if reader.ReadFile(str(path)) != IFSelect_RetDone:
            raise ValueError(f"STEP provenance parsing failed: {path}")
        xde_document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
        if not reader.Transfer(xde_document):
            raise ValueError(f"STEP XDE provenance transfer failed: {path}")
        shape = reader.Reader().OneShape()
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
    face_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, face_map)

    face_ordinals: list[int] = []
    orientation_reversed: list[bool] = []
    seam_records: dict[tuple[int, bytes], list[int]] = {}
    edge_occurrences: dict[int, list[tuple[bytes, ...]]] = {}
    edge_segment_ordinals: dict[tuple[bytes, bytes], set[int]] = {}
    edge_segment_records: dict[tuple[bytes, bytes], set[tuple[int, int, float, float]]] = {}
    vertex_offset = 0
    triangle_offset = 0
    face_ordinal = 0
    missing_edge_polygons = 0
    direction_records: list[dict[str, Any]] = []

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
            try:
                curve2d = BRepAdaptor_Curve2d(edge, face)
                parameter_first = float(curve2d.FirstParameter())
                parameter_last = float(curve2d.LastParameter())
                parameter_mid = 0.5 * (parameter_first + parameter_last)
                uv_point = curve2d.Value(parameter_mid)
                uv_value = gp_Pnt2d()
                uv_tangent = gp_Vec2d()
                curve2d.D1(parameter_mid, uv_value, uv_tangent)
                curve3d = BRepAdaptor_Curve(edge, face)
                xyz_value = curve3d.Value(parameter_mid)
                xyz_point = gp_Pnt()
                xyz_tangent = gp_Vec()
                curve3d.D1(parameter_mid, xyz_point, xyz_tangent)
                surface = BRepAdaptor_Surface(face, True)
                surface_point = surface.Value(uv_value.X(), uv_value.Y())
                surface_d1_point = gp_Pnt()
                surface_du = gp_Vec()
                surface_dv = gp_Vec()
                surface.D1(uv_value.X(), uv_value.Y(), surface_d1_point, surface_du, surface_dv)
                is_closed_pcurve = bool(BRep_Tool.IsClosed_s(edge, face))
                surface_is_u_periodic = bool(surface.IsUPeriodic())
                surface_is_v_periodic = bool(surface.IsVPeriodic())
                u_period = float(surface.UPeriod()) if surface_is_u_periodic else None
                v_period = float(surface.VPeriod()) if surface_is_v_periodic else None
                pcurve_branch_count = 2 if is_closed_pcurve else 1
                pcurve_branch_status = (
                    "seam_branches_unresolved" if is_closed_pcurve else "single_branch"
                )
                pcurve_is_stored: bool | None = None
                pcurve_storage_status = "not_exposed_by_ocp_binding"
                edge_occurrence_reversed = edge.Orientation() == TopAbs_REVERSED
                effective_occurrence_reversed = bool(edge_occurrence_reversed) ^ bool(reversed_face)
                period_shift = [0, 0]
                uv_canonical = [float(uv_value.X()), float(uv_value.Y())]
                uv_tangent_norm = float(np.hypot(uv_tangent.X(), uv_tangent.Y()))
                if uv_tangent_norm <= 1.0e-14:
                    raise ValueError("degenerate B-Rep p-curve tangent")
                if mesh_domain_side_by_face is None:
                    domain_side: int | None = None
                else:
                    if face_ordinal not in mesh_domain_side_by_face:
                        raise ValueError("mesh-domain-side authority missing for B-Rep face")
                    domain_side = int(mesh_domain_side_by_face[face_ordinal])
                    if domain_side not in (-1, 1):
                        raise ValueError("mesh-domain-side authority must be -1 or +1")
                edge_tolerance = float(BRep_Tool.Tolerance_s(edge))
                face_tolerance = float(BRep_Tool.Tolerance_s(face))
                classification_tolerance = max(edge_tolerance, face_tolerance, 1.0e-7)
                parameter_span = max(abs(parameter_last - parameter_first), 1.0e-6)
                probe_rho = max(10.0 * classification_tolerance, min(1.0e-2, 0.05 * parameter_span))
                probe_radii = (probe_rho, 2.0 * probe_rho)
                classifier = BRepTopAdaptor_FClass2d(face, classification_tolerance)
                probe_results: list[dict[str, Any]] = []
                for radius in probe_radii:
                    plus_uv = gp_Pnt2d(
                        uv_value.X() - uv_tangent.Y() / uv_tangent_norm * radius,
                        uv_value.Y() + uv_tangent.X() / uv_tangent_norm * radius,
                    )
                    minus_uv = gp_Pnt2d(
                        uv_value.X() + uv_tangent.Y() / uv_tangent_norm * radius,
                        uv_value.Y() - uv_tangent.X() / uv_tangent_norm * radius,
                    )
                    plus_state = classifier.Perform(plus_uv, False)
                    minus_state = classifier.Perform(minus_uv, False)
                    plus_restriction = classifier.TestOnRestriction(plus_uv, classification_tolerance, False)
                    minus_restriction = classifier.TestOnRestriction(minus_uv, classification_tolerance, False)
                    probe_results.append(
                        {
                            "radius": float(radius),
                            "plus": str(plus_state).split(".")[-1],
                            "minus": str(minus_state).split(".")[-1],
                            "plus_restriction": str(plus_restriction).split(".")[-1],
                            "minus_restriction": str(minus_restriction).split(".")[-1],
                        }
                    )
                stable_opposite = all(
                    (probe["plus"] == "TopAbs_IN" and probe["minus"] == "TopAbs_OUT")
                    or (probe["plus"] == "TopAbs_OUT" and probe["minus"] == "TopAbs_IN")
                    for probe in probe_results
                )
                restrictions_clear = all(
                    probe["plus_restriction"] not in {"TopAbs_ON", "TopAbs_UNKNOWN"}
                    and probe["minus_restriction"] not in {"TopAbs_ON", "TopAbs_UNKNOWN"}
                    for probe in probe_results
                )
                trimmed_interior_status = (
                    "one_side_certified" if stable_opposite and restrictions_clear else "ambiguous_trimmed_interior"
                )
                if is_closed_pcurve:
                    trimmed_interior_status = "ambiguous_periodic_branch"
                trimmed_side_sign = (
                    1 if probe_results[0]["plus"] == "TopAbs_IN" else -1
                    if probe_results[0]["minus"] == "TopAbs_IN" else 0
                )
                curve_xyz = np.asarray([xyz_value.X(), xyz_value.Y(), xyz_value.Z()], dtype="<f8")
                surface_xyz = np.asarray([surface_point.X(), surface_point.Y(), surface_point.Z()], dtype="<f8")
                surface_derivatives = np.asarray(
                    [surface_du.X(), surface_du.Y(), surface_du.Z(),
                     surface_dv.X(), surface_dv.Y(), surface_dv.Z()],
                    dtype="<f8",
                )
                pcurve_values = np.asarray(
                    [uv_value.X(), uv_value.Y(), uv_tangent.X(), uv_tangent.Y(),
                     parameter_first, parameter_last],
                    dtype="<f8",
                )
                branch_values = np.asarray(
                    [
                        float(pcurve_branch_count),
                        float(1 if is_closed_pcurve else 0),
                        float(u_period or 0.0),
                        float(v_period or 0.0),
                        float(period_shift[0]),
                        float(period_shift[1]),
                    ],
                    dtype="<f8",
                )
                branch_digest = sha256(branch_values.tobytes()).hexdigest()
                surface_values = np.concatenate((surface_xyz, surface_derivatives))
                certificate_values = np.asarray(
                    [float(edge_ordinal), float(face_ordinal), parameter_mid,
                     *pcurve_values.tolist(), *surface_values.tolist(), *branch_values.tolist()],
                    dtype="<f8",
                )
                direction_records.append(
                    {
                        "edge_id": int(edge_ordinal),
                        "face_id": int(face_ordinal),
                        "segment_id": 0,
                        "parameter_first": parameter_first,
                        "parameter_last": parameter_last,
                        "parameter_mid": parameter_mid,
                        "uv_point": [float(uv_value.X()), float(uv_value.Y())],
                        "uv_canonical": uv_canonical,
                        "period_shift": period_shift,
                        "uv_tangent": [float(uv_tangent.X()), float(uv_tangent.Y())],
                        "edge_point": curve_xyz.tolist(),
                        "edge_tangent": [float(xyz_tangent.X()), float(xyz_tangent.Y()), float(xyz_tangent.Z())],
                        "surface_point": surface_xyz.tolist(),
                        "surface_du": [float(surface_du.X()), float(surface_du.Y()), float(surface_du.Z())],
                        "surface_dv": [float(surface_dv.X()), float(surface_dv.Y()), float(surface_dv.Z())],
                        "surface_residual": float(np.linalg.norm(curve_xyz - surface_xyz)),
                        "face_orientation_sign": -1 if reversed_face else 1,
                        "edge_occurrence_reversed": edge_occurrence_reversed,
                        "effective_occurrence_reversed": effective_occurrence_reversed,
                        "pcurve_branch_rank": 0,
                        "pcurve_branch_count": pcurve_branch_count,
                        "seam_branch_count": pcurve_branch_count,
                        "pcurve_branch_status": pcurve_branch_status,
                        "pcurve_is_stored": pcurve_is_stored,
                        "pcurve_storage_status": pcurve_storage_status,
                        "is_closed_pcurve": is_closed_pcurve,
                        "surface_is_u_periodic": surface_is_u_periodic,
                        "surface_is_v_periodic": surface_is_v_periodic,
                        "u_period": u_period,
                        "v_period": v_period,
                        "branch_digest": branch_digest,
                        "mesh_domain_side": domain_side,
                        "domain_side_authoritative": domain_side is not None,
                        "trimmed_interior_status": trimmed_interior_status,
                        "trimmed_side_sign": trimmed_side_sign,
                        "classification_tolerance": classification_tolerance,
                        "probe_radii": [float(radius) for radius in probe_radii],
                        "probe_results": probe_results,
                        "uv_inward": [
                            -float(uv_tangent.Y()) / uv_tangent_norm,
                            float(uv_tangent.X()) / uv_tangent_norm,
                        ],
                        "pcurve_digest": sha256(pcurve_values.tobytes()).hexdigest(),
                        "surface_digest": sha256(surface_values.tobytes()).hexdigest(),
                        "certificate_digest": sha256(certificate_values.tobytes()).hexdigest(),
                    }
                )
            except Exception as exc:
                raise ValueError(
                    f"CAD p-curve/surface extraction failed for edge {edge_ordinal}, face {face_ordinal}"
                ) from exc
            occurrence: list[bytes] = []
            for local_node in polygon.Nodes():
                coordinate_key = np.asarray(
                    local_coordinates[int(local_node) - 1], dtype="<f8"
                ).tobytes()
                occurrence.append(coordinate_key)
                key = (int(edge_ordinal), coordinate_key)
                seam_records.setdefault(key, []).append(vertex_offset + int(local_node) - 1)
            edge_occurrences.setdefault(int(edge_ordinal), []).append(tuple(sorted(occurrence)))
            polygon_nodes = [int(local_node) for local_node in polygon.Nodes()]
            segment_denominator = max(len(polygon_nodes) - 1, 1)
            for segment_index, (first_node, second_node) in enumerate(
                zip(polygon_nodes, polygon_nodes[1:], strict=False)
            ):
                first_key = np.asarray(local_coordinates[first_node - 1], dtype="<f8").tobytes()
                second_key = np.asarray(local_coordinates[second_node - 1], dtype="<f8").tobytes()
                edge_key = tuple(sorted((first_key, second_key)))
                t0 = float(segment_index) / float(segment_denominator)
                t1 = float(segment_index + 1) / float(segment_denominator)
                if second_key < first_key:
                    t0, t1 = t1, t0
                edge_segment_ordinals.setdefault(edge_key, set()).add(int(edge_ordinal))
                edge_segment_records.setdefault(edge_key, set()).add(
                    (int(edge_ordinal), int(segment_index), t0, t1)
                )
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
    triangle_brep_edge_ids: list[tuple[int, int, int]] = []
    triangle_brep_edge_segment_ids: list[tuple[int, int, int]] = []
    triangle_brep_edge_segment_parameters: list[tuple[tuple[float, float], ...]] = []
    for triangle in faces.tolist():
        mapped_edges: list[int] = []
        mapped_segment_ids: list[int] = []
        mapped_parameters: list[tuple[float, float]] = []
        for index in range(3):
            first_key = np.asarray(vertices[int(triangle[index])], dtype="<f8").tobytes()
            second_key = np.asarray(vertices[int(triangle[(index + 1) % 3])], dtype="<f8").tobytes()
            edge_key = tuple(sorted((first_key, second_key)))
            records = edge_segment_records.get(edge_key, set())
            if len(records) > 1:
                raise ValueError("CAD B-Rep edge polygon maps one triangle edge to multiple segments")
            if records:
                edge_id, segment_id, t0, t1 = next(iter(records))
            else:
                edge_id, segment_id, t0, t1 = -1, -1, float("nan"), float("nan")
            mapped_edges.append(edge_id)
            mapped_segment_ids.append(segment_id)
            mapped_parameters.append((t0, t1))
        triangle_brep_edge_ids.append(tuple(mapped_edges))
        triangle_brep_edge_segment_ids.append(tuple(mapped_segment_ids))
        triangle_brep_edge_segment_parameters.append(tuple(mapped_parameters))
    triangle_brep_edge_ids_array = np.asarray(triangle_brep_edge_ids, dtype=np.int64)
    triangle_brep_edge_segment_ids_array = np.asarray(triangle_brep_edge_segment_ids, dtype=np.int64)
    triangle_brep_edge_segment_parameters_array = np.asarray(
        triangle_brep_edge_segment_parameters,
        dtype=np.float64,
    )

    xde_face_names: list[str | None] = [None] * face_ordinal
    xde_layers: list[set[str]] = [set() for _ in range(face_ordinal)]
    xde_colors: list[tuple[float, float, float] | None] = [None] * face_ordinal
    xde_paths: list[tuple[str, ...] | None] = [None] * face_ordinal
    xde_assembly_root_count = 0
    if xde_document is not None:
        shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(xde_document.Main())
        color_tool = XCAFDoc_DocumentTool.ColorTool_s(xde_document.Main())
        layer_tool = XCAFDoc_DocumentTool.LayerTool_s(xde_document.Main())

        def label_name(label: Any) -> str | None:
            attributes = TDF_AttributeIterator(label)
            while attributes.More():
                attribute = attributes.Value()
                if attribute.get_type_name_s() == "TDataStd_Name":
                    value = attribute.Get().ToExtString().strip()
                    return value or None
                attributes.Next()
            return None

        def mapped_face_ordinals(source_shape: Any) -> tuple[int, ...]:
            mapped: list[int] = []
            face_explorer = TopExp_Explorer(source_shape, TopAbs_FACE)
            while face_explorer.More():
                ordinal = int(face_map.FindIndex(face_explorer.Current())) - 1
                if ordinal < 0:
                    raise ValueError("XDE shape does not map to the B-Rep face stream")
                mapped.append(ordinal)
                face_explorer.Next()
            return tuple(mapped)

        def inspect_face_label(label: Any) -> None:
            label_shape = shape_tool.GetShape_s(label)
            if label_shape.IsNull() or label_shape.ShapeType() != TopAbs_FACE:
                return
            layer_labels = TDF_LabelSequence()
            has_layers = layer_tool.GetLayers(label, layer_labels)
            layer_names: list[str] = []
            if has_layers:
                for layer_index in range(1, layer_labels.Length() + 1):
                    layer_name = TCollection_ExtendedString()
                    if not layer_tool.GetLayer(layer_labels.Value(layer_index), layer_name):
                        raise ValueError("XDE layer label has no authoritative name")
                    value = layer_name.ToExtString().strip()
                    if not value:
                        raise ValueError("XDE layer name must be nonblank")
                    layer_names.append(value)
            color = Quantity_Color(0.0, 0.0, 0.0, Quantity_TOC_RGB)
            has_color = color_tool.GetColor(label_shape, XCAFDoc_ColorSurf, color)
            name = label_name(label)
            if not layer_names and not has_color and name is None:
                return
            ordinals = mapped_face_ordinals(label_shape)
            if len(ordinals) != 1:
                raise ValueError("XDE face metadata must map to exactly one B-Rep face")
            ordinal = ordinals[0]
            previous_layers = xde_layers[ordinal]
            if previous_layers and previous_layers != set(layer_names):
                raise ValueError("conflicting XDE face layers")
            xde_layers[ordinal].update(layer_names)
            if name is not None:
                previous_name = xde_face_names[ordinal]
                if previous_name is not None and previous_name != name:
                    raise ValueError("conflicting XDE face names")
                xde_face_names[ordinal] = name
            if has_color:
                candidate = (float(color.Red()), float(color.Green()), float(color.Blue()))
                previous_color = xde_colors[ordinal]
                if previous_color is not None and previous_color != candidate:
                    raise ValueError("conflicting XDE surface colors")
                xde_colors[ordinal] = candidate

        free_shapes = TDF_LabelSequence()
        shape_tool.GetFreeShapes(free_shapes)
        for root_index in range(1, free_shapes.Length() + 1):
            root_label = free_shapes.Value(root_index)
            root_name = label_name(root_label)
            subshapes = TDF_LabelSequence()
            shape_tool.GetSubShapes_s(root_label, subshapes)
            for subshape_index in range(1, subshapes.Length() + 1):
                inspect_face_label(subshapes.Value(subshape_index))

            if not shape_tool.IsAssembly_s(root_label):
                continue
            xde_assembly_root_count += 1
            components = TDF_LabelSequence()
            if not shape_tool.GetComponents_s(root_label, components, True):
                raise ValueError("XDE assembly has no authoritative components")
            for component_index in range(1, components.Length() + 1):
                component_label = components.Value(component_index)
                referred_label = TDF_Label()
                if not shape_tool.GetReferredShape_s(component_label, referred_label):
                    raise ValueError("XDE component has no referred shape")
                component_name = label_name(component_label)
                referred_name = label_name(referred_label)
                if root_name is None or component_name is None or referred_name is None:
                    continue
                assembly_path = (root_name, component_name, referred_name)
                for ordinal in mapped_face_ordinals(shape_tool.GetShape_s(component_label)):
                    previous_path = xde_paths[ordinal]
                    if previous_path is not None and previous_path != assembly_path:
                        raise ValueError("ambiguous XDE assembly path for B-Rep face")
                    xde_paths[ordinal] = assembly_path

                referred_subshapes = TDF_LabelSequence()
                shape_tool.GetSubShapes_s(referred_label, referred_subshapes)
                for subshape_index in range(1, referred_subshapes.Length() + 1):
                    subshape_label = referred_subshapes.Value(subshape_index)
                    layer_labels = TDF_LabelSequence()
                    has_layers = layer_tool.GetLayers(subshape_label, layer_labels)
                    subshape = shape_tool.GetShape_s(subshape_label)
                    probe_color = Quantity_Color(0.0, 0.0, 0.0, Quantity_TOC_RGB)
                    has_color = not subshape.IsNull() and color_tool.GetColor(
                        subshape, XCAFDoc_ColorSurf, probe_color
                    )
                    if has_layers or has_color or label_name(subshape_label) is not None:
                        raise ValueError(
                            "located XDE component face metadata requires an explicit "
                            "instance mapping contract"
                        )

    xde_layer_names = tuple(tuple(sorted(names)) for names in xde_layers)
    xde_surface_colors = tuple(xde_colors)
    xde_assembly_paths = tuple(xde_paths)
    xde_layer_coverage = sum(bool(names) for names in xde_layer_names)
    xde_layer_authoritative = xde_layer_coverage > 0
    xde_color_authoritative = any(color is not None for color in xde_surface_colors)
    xde_assembly_authoritative = (
        xde_assembly_root_count > 0
        and bool(xde_assembly_paths)
        and all(path is not None for path in xde_assembly_paths)
    )
    xde_metadata_payload = {
        "face_names": xde_face_names,
        "layer_names": xde_layer_names,
        "surface_colors": xde_surface_colors,
        "assembly_paths": xde_assembly_paths,
        "layer_authoritative": xde_layer_authoritative,
        "physical_group_authoritative": False,
    }
    xde_metadata_hash = sha256(
        json.dumps(xde_metadata_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
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
        face_names=tuple(xde_face_names),
        physical_group_names=(None,) * face_ordinal,
        xde_layer_names=xde_layer_names,
        xde_surface_colors=xde_surface_colors,
        xde_assembly_paths=xde_assembly_paths,
        xde_layer_authoritative=xde_layer_authoritative,
        xde_layer_coverage_count=xde_layer_coverage,
        xde_color_display_metadata_authoritative=xde_color_authoritative,
        xde_assembly_identity_authoritative=xde_assembly_authoritative,
        face_ordinals_authoritative=True,
        face_orientation_authoritative=True,
        seam_connectivity_authoritative=True,
        physical_groups_authoritative=physical_groups_authoritative,
        ordered_triangle_coordinate_sha256=_array_sha256(triangle_coordinates, "<f8"),
        ordered_face_ordinal_sha256=_array_sha256(face_ordinal_array, "<i8"),
        ordered_orientation_sha256=_array_sha256(reversed_array, "u1"),
        seam_connectivity_sha256=_array_sha256(canonical_faces, "<i8"),
        xde_metadata_sha256=xde_metadata_hash,
        triangle_brep_edge_ids=_readonly(triangle_brep_edge_ids_array),
        triangle_brep_edge_segment_ids=_readonly(triangle_brep_edge_segment_ids_array),
        triangle_brep_edge_segment_parameters=_readonly(triangle_brep_edge_segment_parameters_array),
        brep_edge_face_direction_records=tuple(direction_records),
    )
    return CadNativeTriangulation(vertices, faces, provenance)
