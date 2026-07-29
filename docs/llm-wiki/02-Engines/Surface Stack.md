---
type: subsystem
status: active
updated: 2026-07-26
stability: implemented
source_paths: [core/analyzer, core/preprocessor, core/utils/surface_nets.py]
tags: [surface, analyzer, repair, remesh]
---

# 표면 처리 스택

## 입력과 분석

`file_reader.py`는 STL/OBJ/PLY/OFF 자체 reader를 먼저 쓰고 실패하면 trimesh로 fallback한다. 3MF·GLB/GLTF·DAE, meshio 기반 MSH/VTK/VTU/XDMF/Nastran/Abaqus/CGNS, LAS/LAZ, STEP/IGES/BREP도 지원한다. CAD는 OCP→CadQuery→Gmsh 순으로 시도한다.

`GeometryAnalyzer`는 파일 정보, bounds, 차원·edge·surface 통계, sharp feature, curvature 추정, issue, flow hint, tier 호환성을 만든다. 대형 mesh는 진단 비용을 제한하기 위해 sampling할 수 있다.

## 전처리 등급

| 등급 | 목적 | 현재 메커니즘 |
|---|---|---|
| L1 | 의도적 remesh 없이 topology 수리 | native dedup, degenerate 제거, winding/normal, manifold/hole repair; legacy `pymeshfix` fallback |
| L2 | tessellation 개선·정규화 | native isotropic split/collapse/flip/smooth, face-remesh policy, quad-dominant/4-RoSy 진단; legacy Vorpalite/pyacvd/PyMeshLab |
| L3 | 일반 repair로 못 살리는 입력 복구 | 선택적 AI repair, aggressive repair, voxel/GWN reconstruction, Surface Nets |

Preprocessor는 empty mesh와 repair가 파괴한 mesh를 감지하고, open surface를 명시적으로 다루며 `PreprocessedReport`를 남긴다. CAD를 직접 받는 tier에는 원본 B-rep을 전달할 수 있다.

L1 repair와 L2 remesh는 다른 계약이다. Repair는 유효한 표현을 복원하고, remesh는 triangulation을 바꿀 수 있지만 surface-error와 feature 계약을 지켜야 한다. Native-tri는 per-operation transaction과 bijective shell로 더 강한 계약을 목표로 하며 아직 기본 L2 경로는 아니다.
