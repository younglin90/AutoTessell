---
type: subsystem
status: active
updated: 2026-07-26
stability: implemented
source_paths: [core/layers/native_bl.py, core/generator/tier_layers_post.py, core/layers/tet_bl_subdivide.py, core/layers/poly_bl_transition.py]
tags: [boundary-layer, native-bl, wall]
---

# 경계층

경계층은 `tier_layers_post.py`가 선택하는 엔진 독립 post-generation 단계다. `BLConfig`는 layer 수, first height, growth, collision, wall patch, quality policy를 담고 `NativeBLResult`와 Phase-2 schema가 근거를 downstream으로 전달한다.

## Native BL

`native_bl.py`는 현재 `polyMesh`를 읽고 wall face를 선택해 area-weighted vertex normal, sharp feature, collision distance, geometric layer thickness를 계산하고 prism-like layer를 넣는다. Hex wall, tet-wall cavity, front component, shell coverage, transition tet, determinant/non-ortho/skew/shape 검사와 local rollback 경로가 있다.

안전의 핵심은 wall provenance, collision/gap 제약, boundary orientation, layer별 persistence evidence, anti-inversion이다. 파일이 큰 이유는 여러 bounded cavity replacement와 진단도 포함하기 때문이다.

## 후속 변환과 외부 경로

- `tet_bl_subdivide.py`: prism을 식별해 all-tet 계약에 맞게 결정론적으로 세분화
- `poly_bl_transition.py`: cell type 분류, native-poly/hybrid dual transition, guarded interface smoothing, topology merge
- `tier_layers_post.py`: cfMesh/OpenFOAM, Netgen, Gmsh, pyHyp, MeshKit, SU2/Hexpress, extrusion helper 라우팅

Layer 성공은 cell 수 증가가 아니라 요청 layer 수, wall-face provenance, surface fidelity, positive volume, persistence로 판정한다.
