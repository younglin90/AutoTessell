---
type: interface
status: active
updated: 2026-07-26
stability: implemented
source_paths: [core/analyzer/file_reader.py, core/analyzer/readers, core/generator/polymesh_writer.py, core/utils/polymesh_reader.py, core/utils/mesh_exporter.py]
tags: [io, formats, openfoam]
---

# 입출력과 내보내기

## 입력

- Native-first surface: STL(ASCII/binary), OBJ, PLY, OFF
- Trimesh: 3MF, GLB/GLTF, DAE와 fallback
- Meshio: MSH, VTK/VTU/VTP, XDMF, Nastran, Abaqus, CGNS
- CAD: STEP/STP, IGES/IGS, BREP — OCP→CadQuery→Gmsh
- Point cloud: LAS/LAZ — 근사 surface reconstruction

Native reader는 `CoreSurfaceMesh`를 반환하지만 많은 기존 호출자가 `trimesh.Trimesh`를 기대해 compatibility layer가 다시 감싼다.

## OpenFOAM topology

`polymesh_writer.py`는 points, faces, owner, neighbour, boundary를 쓴다. Generic cell-face topology, tet winding 정규화, feature-aware boundary segmentation, optional native topology acceleration을 지원한다. `polymesh_reader.py`는 같은 목록을 NumPy/list로 읽으며 native metrics나 Ofpp 경로를 쓸 수 있다.

## Export

`mesh_exporter.py`는 SU2, Fluent/ANSYS MSH, CGNS, VTU, VTK, VTP, XDMF, Gmsh 2.2/4.x, Nastran, Abaqus, Tecplot, Medit, boundary-only STL/OBJ/PLY를 지원한다. Meshio가 주 compatibility backend이고 VTP는 PyVista, arbitrary polyhedra는 direct polyhedral VTU 경로를 사용한다.

포맷을 쓸 수 있다는 사실이 patch/BC round-trip을 보장하지는 않는다. 포맷별 fixture와 provenance round-trip 검증이 별도로 필요하다.
