"""Native STEP/IGES/BREP reader (v0.4.0-beta53).

OCP (OpenCASCADE Python bindings) 를 **직접** 호출해 BRepMesh 로 tessellate.
cadquery wrapper layer 를 건너뛰어 의존 체인을 축소한다.

OCP 는 cadquery 가 내부에서 사용하는 같은 C++ OpenCASCADE 라이브러리 바인딩.
OCP 가 미설치되면 graceful fallback 을 위해 ImportError 를 raise (file_reader
상위에서 cadquery / gmsh 로 이어간다).

완전 native ISO 10303 STEP parser 는 v1.0 로드맵 (연구급 작업, 수개월).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from core.utils.logging import get_logger

log = get_logger(__name__)


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
        from OCP.STEPControl import STEPControl_Reader  # type: ignore
        from OCP.IGESControl import IGESControl_Reader  # type: ignore
        from OCP.BRepTools import BRepTools  # type: ignore
        from OCP.BRep import BRep_Builder, BRep_Tool  # type: ignore
        from OCP.TopoDS import TopoDS_Shape, TopoDS_Face, TopoDS  # type: ignore
        from OCP.BRepMesh import BRepMesh_IncrementalMesh  # type: ignore
        from OCP.TopExp import TopExp_Explorer  # type: ignore
        from OCP.TopAbs import TopAbs_FACE  # type: ignore
        from OCP.TopLoc import TopLoc_Location  # type: ignore
        from OCP.IFSelect import IFSelect_RetDone  # type: ignore
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
            faces_list.append((
                vert_offset + a - 1,
                vert_offset + b - 1,
                vert_offset + c - 1,
            ))
        vert_offset += n_nodes
        explorer.Next()

    if not vertices_list or not faces_list:
        raise ValueError(f"테셀레이션 결과가 비어있음: {path}")

    V = np.array(vertices_list, dtype=np.float64)
    F = np.array(faces_list, dtype=np.int64)

    log.info(
        "cad_loaded_via_ocp_native",
        path=str(path), fmt=ext,
        num_vertices=V.shape[0], num_faces=F.shape[0],
    )
    return V, F
