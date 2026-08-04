# Agent: Preprocessor (전처리 에이전트)

## 핵심 철학

**외부 라이브러리에 의존하지 않고 우리 코드로 직접 구현**한다.
pymeshfix / pyACVD / geogram / MeshAnything 등은 **참고용** 으로만 사용하며, 핵심 알고리즘 (hole filling,
voronoi clustering, manifold repair, isotropic remesh) 은 논문·라이브러리 소스를 참고해
`core/preprocessor/` 내부 파일로 복제·고도화한다.
최종 목표: 외부 라이브러리 없이 L1/L2 가 단독 동작, L3 AI 만 외부 의존 유지.

---

## 역할

Analyzer 의 `geometry_report.json` 을 기반으로 입력 지오메트리를 정제한다.
**표면 메쉬를 L1 → L2 → L3 순서로 점진적으로 품질 개선** 하며, 각 단계 후 gate 통과 시 이후 단계를 건너뛴다.
Generator 의 Volume Phase 가 사용할 수 있는 **watertight + manifold** 표면 메쉬를 생산한다.

---

## 입력 / 출력

- 입력: 원본 파일, `geometry_report.json`, CLI 파라미터
- 출력:
  - `preprocessed.stl` (정제된 표면 메쉬, binary)
  - `preprocessed_report.json` (작업 이력 + `surface_quality_level`)
  - STEP/IGES 직접 지원 Tier 는 원본 CAD 패스스루

---

## 라이브러리 → 자체 코드화 로드맵

| 기능 | 현재 의존 | 참고 출처 | 자체 구현 목표 |
|------|----------|-----------|----------------|
| Hole filling | pymeshfix | Attene 2010 "Lightweight approach to repair polygon meshes" | `core/preprocessor/repair/hole_fill.py` |
| Non-manifold 제거 | pymeshfix | edge adjacency 기반 | `core/preprocessor/repair/manifold.py` |
| Self-intersection | pymeshfix | AABB tree + triangle-triangle intersection | `core/preprocessor/repair/self_intersect.py` |
| Face normal 수정 | trimesh | BFS + winding number | `core/preprocessor/repair/normals.py` |
| 중복 정점 merge | trimesh | KDTree 기반 근접 병합 | `core/preprocessor/repair/dedup.py` |
| Voronoi clustering (L2) | pyACVD | Lloyd relaxation + constrained Voronoi | `core/preprocessor/remesh/acvd.py` |
| Centroidal Voronoi (L2) | geogram vorpalite | Liu et al. "Centroidal Voronoi Tessellation" | `core/preprocessor/remesh/cvt.py` |
| Isotropic remesh (L2) | pymeshlab | Botsch & Kobbelt 2004 | `core/preprocessor/remesh/isotropic.py` |

진행 방식: 모듈별로 **duplicate-then-compare** — 외부 라이브러리 + 우리 코드를 동시 실행해 결과가
일치(면 수·watertight·Hausdorff) 하면 외부를 제거.

---

## 처리 파이프라인

```
입력 파일
    │
    ▼
┌─────────────────┐
│ 0. 포맷 변환     │  STEP/IGES/기타 → STL (필요 시)
└────────┬────────┘
         ▼
┌─────────────────────────────────────────────────┐
│  표면 품질 개선 Loop                              │
│                                                  │
│  L1 (Repair):  자체 topology repair              │
│      │  Gate: watertight + manifold?             │
│      │  Yes → 완료  No → L2                      │
│      ▼                                           │
│  L2 (Remesh):  자체 CVT/isotropic remesh         │
│      │  Gate: watertight + manifold?             │
│      │  Yes → 완료  No → L3                      │
│      ▼                                           │
│  L3 (AI fix):  MeshAnything / MeshGPT (GPU)      │
│      │  Gate: watertight + manifold?             │
│      │  No → 에러 리포트 (Generator 에 TetWild 강제) │
└────────┬────────────────────────────────────────┘
         ▼
    preprocessed.stl
    (surface_quality_level: l1_repair | l2_remesh | l3_ai)
```

---

## 단계별 상세

### 0. 포맷 변환

CAD B-Rep → 표면 메쉬.

| 입력 | 단기 변환 | 장기 (자체) |
|------|----------|-------------|
| STEP/IGES/BREP | cadquery + gmsh fallback | OCCT BRepMesh 이식 |
| OBJ/PLY/OFF/3MF | 자체 reader (Analyzer 공유) | 이미 자체 |
| Gmsh .msh | meshio → trimesh | 자체 `readers/gmsh_msh.py` |
| VTK/VTU/VTP | pyvista | 자체 `readers/vtk.py` |
| Fluent/Nastran/Abaqus | meshio | 표면 추출 자체 구현 |

패스스루: Netgen 처럼 CAD 직접 지원 Tier 선택 시 STEP 원본 유지 (sewing/tolerance 만 수리).

### L1: 표면 수리 (Repair)

`geometry_report.issues` 참조해 필요한 수리만 선별 수행.

| 문제 | 자체 구현 계획 |
|------|---------------|
| Non-manifold 엣지 | edge-face adjacency → 3 개 이상 face 공유 엣지 분리 |
| 열린 구멍 | boundary loop 탐지 → fan triangulation 또는 advancing front |
| 중복 면/정점 | KDTree + tolerance 병합 |
| 자기 교차 | AABB tree + 삼각형 교차 검출 + local retriangulate |
| 법선 방향 | BFS + consistent winding (최대 component 기준) |
| 영 면적 삼각형 | area < ε 면 제거 + edge collapse |
| Disconnected component | connected component 분석, 최대만 유지 (또는 옵션) |

수행 기준:
- `severity: critical` → 무조건 수리
- `severity: warning` → 기본 수리, `--no-repair` 로 비활성
- `--force-repair` → 모든 문제 강제

Gate: watertight + manifold → `l1_repair`, L2 skip.

### L2: 표면 리메쉬 (Remesh)

균일한 edge length 와 양호한 삼각형 품질 확보.

활성화 조건 (L1 gate fail 시 자동):
- `edge_length_ratio > 100`
- `num_faces > 200000`
- `has_degenerate_faces: true`

자체 알고리즘 우선순위 (구현 순서):
1. **isotropic remesh** (Botsch & Kobbelt) — edge split/collapse/flip + vertex relocation
2. **CVT / Lloyd relaxation** — voronoi centroid 이동
3. **RVD (Restricted Voronoi Diagram)** — 표면 제약 Voronoi

목표 삼각형 수 자동 계산:
```python
target_faces = max(10000, min(100000,
                              int(surface_area / (element_size ** 2) * 2)))
```

Gate: watertight + manifold → `l2_remesh`, L3 skip.

### L3: AI 표면 재생성 (최후 수단)

GPU 기반. 상업 라이선스 이슈로 **MeshGPT (MIT)** 를 우선, 실패 시 **MeshAnythingV2 (비상업)**.

공통 제약:
- GPU 필수, CPU 불가
- Feature edge 손실 가능
- `--allow-ai-fallback` 플래그 또는 `ai_fallback: true` 필요

L3 는 AI 모델 특성상 자체 구현 범위 밖 — 외부 의존 유지, wrapping 만 정리.

Gate 실패 시 Generator 에 TetWild 강제 플래그.

---

## preprocessed_report.json 스키마

```json
{
  "preprocessing_summary": {
    "input_file": "model.step",
    "input_format": "STEP",
    "output_file": "preprocessed.stl",
    "passthrough_cad": false,
    "surface_quality_level": "l2_remesh",
    "total_time_seconds": 4.2,
    "steps_performed": [
      { "step": "format_conversion", "method": "cadquery_passthrough", "time_seconds": 2.1 },
      { "step": "l1_repair",         "method": "native_repair", "issues_fixed": ["non_manifold(3)","holes(1)"], "gate_passed": false, "time_seconds": 0.8 },
      { "step": "l2_remesh",         "method": "native_isotropic", "params": { "target_faces": 30000 }, "gate_passed": true, "time_seconds": 1.3 }
    ],
    "final_validation": {
      "is_watertight": true,
      "is_manifold": true,
      "num_faces": 30000,
      "min_face_area": 2.3e-6,
      "max_edge_length_ratio": 12.4
    }
  }
}
```

---

## 테스트 시나리오

```bash
auto-tessell preprocess sphere.stl
auto-tessell preprocess broken.stl --verbose
auto-tessell preprocess naca0012.step --cad-linear-deflection 0.0005
auto-tessell preprocess high_res.stl --surface-remesh --remesh-target-faces 50000
auto-tessell preprocess broken.stl --allow-ai-fallback
auto-tessell preprocess model.step --tier netgen   # 패스스루
auto-tessell preprocess bad.stl --no-repair
```
