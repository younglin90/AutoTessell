# Agent: Generator (메쉬 생성 에이전트)

## 핵심 철학

**외부 라이브러리에 의존하지 않고 우리 코드로 직접 구현**한다.
TetWild / WildMesh / snappyHexMesh / cfMesh / Netgen 등은 **참고용** 으로만 사용하며, 알고리즘의 핵심
(envelope-based tet optimization, Delaunay refinement, AMR octree + snap, cartesian cut-cell) 을
논문·오픈소스 읽고 `core/generator/native/` 내부 파일로 복제·고도화한다.

**최종 목표** : 외부 라이브러리 없이 우리만의 `native_tet`, `native_hex`, `native_poly` 엔진이 단독 동작.
**과도기** : 기존 17 Tier 는 fallback 으로 유지, 신규 native 엔진을 기본값으로 전환해 가며 점진적 대체.

---

## 역할

Strategist 의 `mesh_strategy.json` 에 따라 실제 볼륨 메쉬를 생성한다.

- **사용자가 선택한 메쉬 타입 (tet / hex_dominant / poly)** + 품질 레벨에 맞는 엔진 실행
- 실패 시 동일 타입 내 fallback Tier 로 자동 전환
- 결과를 OpenFOAM polyMesh 형식으로 **우리 자체 `PolyMeshWriter`** 로 직접 기록

---

## 3-카테고리 메쉬 타입

### 1. tet (Tetrahedral)

모든 셀이 tetrahedron. 복잡 형상에서 가장 강건하고 구현이 쉬움.
**참고 라이브러리** : TetWild, fTetWild (WildMesh), Netgen, TetGen
**우선 카피 대상** : fTetWild — envelope-based optimization, 빠르고 robust.

| QualityLevel | 1차 엔진 | Fallback |
|--------------|----------|----------|
| draft | tetwild (epsilon 큼) | wildmesh (fast) |
| standard | netgen | wildmesh |
| fine | wildmesh (epsilon 작음) | tetwild + mmg3d |

BL 전략 (tet): **전체 tet 유지** — prism 층도 subdivide 된 tet 로 구성 (wedge 를 tet 3 개로 분할).

### 2. hex_dominant (Hex-dominant)

대부분 hexahedron, 코너/곡면 근처만 polyhedral. CFD BL 품질 최우수.
**참고 라이브러리** : snappyHexMesh, cfMesh (cartesianMesh), classy_blocks
**우선 카피 대상** : snappyHexMesh — octree AMR + snap + addLayers 파이프라인 전체.

| QualityLevel | 1차 엔진 | Fallback |
|--------------|----------|----------|
| draft | cfmesh (fast) | snappy |
| standard | cfmesh | snappy |
| fine | snappy (BL 포함) | cfmesh |

BL 전략 (hex_dominant): **전통적 prism** — shrink + extrude + snap + merge + stitch.

### 3. poly (Polyhedral)

Voronoi dual 기반 다면체. 셀 수 최소, large-gradient 해소 우수.
**참고 라이브러리** : OpenFOAM polyDualMesh, pyvoro-mm, geogram Voronoi
**우선 카피 대상** : polyDualMesh 알고리즘 (tet mesh 의 dual).

| QualityLevel | 1차 엔진 | Fallback |
|--------------|----------|----------|
| draft | voro_poly (pyvoro-mm) | polydual |
| standard | polydual (polyDualMesh) | voro_poly |
| fine | polydual + 품질 개선 | — |

BL 전략 (poly): **prism 층 + polyhedral 전환** 또는 **anisotropic polyhedral** 셀.

---

## 입력 / 출력

- 입력: `mesh_strategy.json`, `preprocessed.stl` 또는 원본 CAD
- 출력:
  - `case/constant/polyMesh/` (boundary, faces, neighbour, owner, points)
  - `generator_log.json` (실행 이력, Evaluator 에 전달)

---

## 실행 흐름

```
mesh_strategy.json 읽기
    │  (mesh_type, quality_level, selected_tier, strict_tier)
    ▼
사용자 선택 Tier 실행
    │
    ├── 성공 → PolyMeshWriter → generator_log.json → 끝
    │
    └── 실패
          │  strict_tier=True  → 즉시 에러 리턴
          │  strict_tier=False → 동일 mesh_type 내 fallback Tier
          ▼
       fallback Tier 실행 (work_dir 초기화 후)
          │
          ├── 성공 → ...
          └── 모두 실패 → 에러 리포트 (사용자에게 mesh_type/quality 변경 제안)
```

**변경 사항** : Evaluator ⇄ Strategist 자동 재시도 제거. Generator 내부의 fallback 만 유지.

---

## 현재 Tier 등록 현황 (v0.3.5)

17 Tier 등록, 모두 동작 (상세는 `open_source_roadmap.md` 참조).

| 메쉬 타입 | 우선순위 Tier | Fallback Tier |
|-----------|---------------|----------------|
| tet | tetwild, wildmesh, netgen | mmg3d, meshpy, jigsaw, core |
| hex_dominant | cfmesh, snappy | hex_classy, gmsh_hex, cinolib_hex, hohqmesh |
| poly | voro_poly | polydual (polyhedral.py), algohex, robust_hex |

---

## Tier 4 (Layers Post) — Boundary Layer

주 볼륨 엔진 이후 BL 추가. 메쉬 타입별 기법:

### tet 메쉬용 BL

- **최종 결과도 tet** (prism 혼합 없음)
- 파이프라인:
  1. 주 tet 엔진으로 기본 볼륨 생성
  2. 자체 구현한 **surface shrink** (native_bl) 로 벽면 안쪽 이동
  3. `extrudeMesh` 로 shrunk↔원래 사이 prism 생성
  4. prism → tet subdivide (각 wedge → 3 tet)
  5. `mergeMeshes + stitchMesh` 로 통합

### hex_dominant 메쉬용 BL

- 전통적 prism 층
- 파이프라인 (shrink + extrude + snap + merge + stitch — 이번 세션에서 완성):
  1. master polyMesh 를 tmp_case 로 복사
  2. placeholder `{wall}_bl_exposed` patch 주입
  3. `extrudeMesh flipNormals=true` → prism block 생성
  4. prism 의 exposed patch 좌표로 master wall vertex snap
  5. master wall 을 `{wall}_bl_fluid` rename (이름 충돌 회피)
  6. `mergeMeshes + stitchMesh -perfect`
  7. empty placeholder patch 제거

### poly 메쉬용 BL

- prism 층을 먼저 만들고 이후 polyhedral 전환
- 또는 anisotropic polyhedral 셀을 벽 근처 배치

### 참고 라이브러리 (점진적 자체화 대상)

- cfMesh `generateBoundaryLayers` — 가장 안정적, 알고리즘 카피 우선
- OpenFOAM `refineWallLayer` — edge_fraction 기반 벽 셀 분할
- OpenFOAM snappy `addLayers` — medial axis 기반 BL
- netgen_bl, gmsh_bl, MeshKit, SU2 HexPress, Salome SMESH

위 라이브러리들의 핵심 로직 (normal smoothing, collision detection, medial axis, layer optimization)
을 `core/layers/native_bl.py` 에 점진적으로 이식.

---

## Native Python BL 생성기 (자체 구현 로드맵)

`core/layers/native_bl.py` — Phase 1 완료, Phase 2 진행 예정:

| Phase | 기능 | 상태 |
|-------|------|------|
| 1 | wall face/vertex 추출, area-weighted normal, thickness 배열, mesh shrink, layer point copy | ✅ 완료 |
| 2 | side face edge-pair 매핑, prism cell topology, polyMesh 쓰기 | 🔧 진행 |
| 3 | collision detection, feature edge 보존, layer smoothing | 🗓️ 예정 |
| 4 | Quality check + retry (local thickness 축소) | 🗓️ 예정 |

---

## OpenFOAM polyMesh 출력 — PolyMeshWriter (자체 구현)

**중요** : OpenFOAM 바이너리 / meshio 변환 없이 **순수 Python 으로 직접** 기록.

```
case/
├── constant/
│   ├── polyMesh/
│   │   ├── points        (vectorField, ASCII)
│   │   ├── faces         (faceList)
│   │   ├── owner         (labelList)
│   │   ├── neighbour     (labelList)
│   │   └── boundary      (polyBoundaryMesh)
│   └── triSurface/surface.stl
└── system/
    ├── controlDict
    ├── fvSchemes
    └── fvSolution
```

`core/utils/polymesh_writer.py` 와 `core/utils/polymesh_reader.py` 가 이미 구현됨 — 지속 고도화.

---

## generator_log.json 스키마

```json
{
  "execution_summary": {
    "mesh_type": "hex_dominant",
    "quality_level": "standard",
    "selected_tier": "cfmesh",
    "strict_tier": false,
    "tiers_attempted": [
      {
        "tier": "cfmesh",
        "status": "success",
        "time_seconds": 5.4,
        "mesh_stats": {
          "num_cells": 42880,
          "num_points": 45231,
          "num_faces": 134562,
          "num_boundary_patches": 3,
          "cell_type_distribution": { "hex": 40000, "poly": 2880 }
        }
      }
    ],
    "boundary_layer_post": {
      "applied": true,
      "engine": "extrude_mesh",
      "num_layers": 3,
      "applied_thickness": 0.0728
    },
    "output_dir": "case/constant/polyMesh",
    "total_time_seconds": 7.8
  }
}
```

---

## OpenFOAM 유틸리티 실행 래퍼

주 볼륨 엔진이 OpenFOAM 을 요구하는 경우에만 사용. 장기적으로 각 엔진의 핵심 로직을 자체 구현해
유틸리티 의존 축소.

```python
def run_openfoam(utility: str, case_dir: str, args: list = None):
    of_dir = os.environ.get("OPENFOAM_DIR", "/opt/openfoam13")
    ...
```

---

## 테스트 시나리오

```bash
auto-tessell run sphere.stl -o ./case --mesh-type tet --quality draft
auto-tessell run sphere.stl -o ./case --mesh-type hex_dominant --quality standard
auto-tessell run sphere.stl -o ./case --mesh-type hex_dominant --quality fine      # + BL
auto-tessell run sphere.stl -o ./case --mesh-type poly --quality standard

# 특정 Tier 강제 (strict_tier)
auto-tessell run sphere.stl -o ./case --tier wildmesh
```
