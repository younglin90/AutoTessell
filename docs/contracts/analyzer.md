# Agent: Analyzer (분석 에이전트)

## 핵심 철학

**외부 라이브러리에 의존하지 않고 우리 코드로 직접 구현**한다.
trimesh/pyvista/meshio/cadquery/gmsh 등은 **참고용**으로만 사용하며, 필요한 알고리즘·구조는
핵심 부분만 추출해 `core/analyzer/` 내부 파일로 복제·고도화한다.
최종 목표: 외부 라이브러리 없이 Analyzer 가 단독 동작.

---

## 역할

입력 파일을 로딩하고 지오메트리 특성을 분석하여 `geometry_report.json` 을 생성한다.
이 리포트는 Preprocessor 와 Strategist 가 후속 의사결정에 사용하는 **모든 정보의 원천**이다.

---

## 입력 / 출력

- 입력: 사용자가 제공한 CAD/메쉬 파일, CLI 파라미터
- 출력:
  - `geometry_report.json` (Pydantic 스키마 검증)
  - 로딩된 내부 메쉬 객체 (자체 `CoreSurfaceMesh` 구조체)

---

## 라이브러리 → 자체 코드화 로드맵

| 기능 | 현재 의존 | 참고 포인트 | 자체 구현 목표 |
|------|----------|-------------|----------------|
| STL 바이너리/ASCII 파싱 | trimesh | 포맷 스펙 (84-byte header + triangles) | `core/analyzer/readers/stl.py` 순정 Python |
| OBJ/PLY/OFF 파싱 | trimesh/meshio | 포맷 스펙 | `core/analyzer/readers/` 에 각각 |
| 3MF 로딩 | trimesh | 3MF 는 ZIP+XML — 표준 라이브러리로 파싱 | `core/analyzer/readers/threemf.py` |
| STEP/IGES 테셀레이션 | cadquery/OpenCASCADE | OCCT 의 BRepMesh 알고리즘 논문 | 장기 목표 — 일단 외부 utility 호출 유지하되 wrapping |
| watertight/manifold 판정 | trimesh | edge-face adjacency | `core/analyzer/topology.py` 자체 구현 |
| genus / Euler | trimesh | V - E + F = 2 - 2g | `core/analyzer/topology.py` |
| curvature 추정 | pymeshlab | 평균 dihedral angle + face normal variance | `core/analyzer/curvature.py` |
| bounding box / 길이 통계 | numpy | 순수 numpy | 이미 자체 구현 |

진행 방식: 한 번에 하나씩, 각 reader 는 먼저 "우리 코드 + 외부 라이브러리 이중 실행 + 결과 비교 테스트"
후 우리 코드만 남기는 식으로 점진적 전환.

---

## 분석 항목

### 1. 파일 메타데이터

```json
{
  "file_info": {
    "path": "/input/model.step",
    "format": "STEP",
    "file_size_bytes": 1048576,
    "detected_encoding": "binary",
    "is_cad_brep": true,
    "is_surface_mesh": false,
    "is_volume_mesh": false
  }
}
```

### 2. 지오메트리 특성

```json
{
  "geometry": {
    "bounding_box": {
      "min": [0.0, 0.0, 0.0],
      "max": [1.0, 0.5, 0.3],
      "center": [0.5, 0.25, 0.15],
      "diagonal": 1.17,
      "characteristic_length": 1.0
    },
    "surface": {
      "num_vertices": 12450,
      "num_faces": 24896,
      "surface_area": 2.34,
      "is_watertight": true,
      "is_manifold": true,
      "num_connected_components": 1,
      "euler_number": 2,
      "genus": 0,
      "has_degenerate_faces": false,
      "num_degenerate_faces": 0,
      "min_face_area": 1.2e-6,
      "max_face_area": 3.4e-3,
      "face_area_std": 5.6e-4,
      "min_edge_length": 2.1e-4,
      "max_edge_length": 0.015,
      "edge_length_ratio": 71.4,
      "aspect_ratio": 3.2
    },
    "features": {
      "has_sharp_edges": true,
      "num_sharp_edges": 48,
      "sharp_edge_angle_threshold": 30.0,
      "has_thin_walls": false,
      "min_wall_thickness_estimate": 0.02,
      "has_small_features": true,
      "smallest_feature_size": 0.001,
      "feature_to_bbox_ratio": 0.001,
      "curvature_max": 50.0,
      "curvature_mean": 2.3
    }
  }
}
```

### 3. 유동 타입 추정 (`_estimate_flow()`)

형상으로부터 internal / external 를 **추정** (사용자가 override 가능).

```json
{
  "flow_estimation": {
    "type": "internal",
    "confidence": 0.7,
    "reasoning": "단일 폐곡면, genus=0 — 내부 유동 기본값 (override 가능)",
    "alternatives": ["external"]
  }
}
```

추정 규칙 (자체 구현):
- **단일 폐곡면 (genus=0) → `internal` (기본값)** — WildMesh bbox 대칭 도메인에 적합
- 복수 connected component + 내부 공간 → `internal`
- 관 형태 (aspect ratio ↑, 양단 개방) → `internal` (파이프)
- 혈관 분기 (다수 개방 경계) → `internal` (hemodynamics)
- 확신도 낮으면 → CLI 에서 사용자에게 확인 요청
- 사용자가 `--flow external` 명시 시 → 풍동 도메인 (9×5×5 비대칭) 적용

### 4. 문제 진단

```json
{
  "issues": [
    {
      "severity": "warning",
      "type": "non_manifold_edges",
      "count": 3,
      "description": "3 non-manifold 엣지. Preprocessor L1 수리 필요.",
      "recommended_action": "repair"
    }
  ]
}
```

심각도: `critical` / `warning` / `info`

### 5. Tier 호환성 사전 평가

사용자의 **메쉬 타입 선택 (Tet / Hex-dominant / Poly)** 과 품질 레벨 (draft/standard/fine) 조합에 대한 권장 Tier.

```json
{
  "tier_compatibility": {
    "tet_draft":     { "recommended": "tetwild",   "notes": "빠른 검증" },
    "tet_standard":  { "recommended": "netgen",    "notes": "범용" },
    "tet_fine":      { "recommended": "wildmesh",  "notes": "고품질 Tet" },
    "hexdom_draft":  { "recommended": "cfmesh",    "notes": "fast hex-dom" },
    "hexdom_standard":{ "recommended": "cfmesh",   "notes": "기본 선택" },
    "hexdom_fine":   { "recommended": "snappy",    "notes": "BL 자동" },
    "poly_draft":    { "recommended": "voro",      "notes": "voronoi polyhedral" },
    "poly_standard": { "recommended": "voro",      "notes": "" },
    "poly_fine":     { "recommended": "polydual",  "notes": "" }
  }
}
```

---

## 파일 포맷별 로딩 전략 (점진적 자체화)

| 입력 타입 | 단기 (외부 의존) | 장기 (우리 코드) |
|----------|------------------|------------------|
| STL (ASCII/binary) | trimesh | `readers/stl.py` |
| OBJ / PLY / OFF | trimesh | `readers/obj.py`, `ply.py`, `off.py` |
| 3MF | trimesh | `readers/threemf.py` (ZIP + XML 수동) |
| STEP / IGES | cadquery + gmsh fallback | BRepMesh 알고리즘 이식 (장기) |
| Gmsh .msh | meshio | `readers/gmsh_msh.py` |
| VTK / VTU / VTP | pyvista | `readers/vtk.py` (XML + legacy) |
| Fluent .msh | meshio | `readers/fluent.py` |
| CGNS | meshio | HDF5 직접 파싱 (장기) |
| OpenFOAM polyMesh | 자체 파서 (완료) | 이미 `core/utils/polymesh_reader.py` |

---

## 구현 참고사항

- Analyzer 는 **읽기 전용**. 입력 파일을 절대 수정하지 않음.
- 분석 소요 시간: < 10 초 (대용량 STL 100 만+ 삼각형은 샘플링 통계 사용).
- 분석 결과는 `geometry_report.json` 단일 파일에 집약.
- CAD 파일 (STEP/IGES) 은 테셀레이션 없이 추출 가능한 항목 (bbox, 경계 개수) 부터 뽑기.
- 자체 구현 모듈은 반드시 **외부 라이브러리와의 회귀 테스트** 를 동반.

---

## 테스트 시나리오

```bash
python -m auto_tessell analyze sphere.stl
python -m auto_tessell analyze broken_mesh.stl
python -m auto_tessell analyze naca0012.step
python -m auto_tessell analyze existing.msh
auto-tessell input.stl --dry-run
```
