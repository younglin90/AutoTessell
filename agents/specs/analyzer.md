# Agent: Analyzer (분석 에이전트)

## 역할

입력 파일을 로딩하고 지오메트리의 특성을 분석하여 `geometry_report.json`을 생성한다.
이 리포트는 Preprocessor와 Strategist가 후속 의사결정에 사용하는 **모든 정보의 원천**이다.

---

## 입력

- 사용자가 제공한 CAD/메쉬 파일 (30+ 포맷 지원)
- CLI 파라미터 (있을 경우)

## 출력

- `geometry_report.json` (Pydantic 스키마로 검증)
- 로딩된 표면 메쉬 객체 (trimesh.Trimesh 또는 meshio.Mesh)

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
      "edge_length_ratio": 71.4
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

### 3. 유동 타입 추정

Analyzer는 지오메트리의 형상으로부터 유동 타입을 **추정**한다 (사용자가 override 가능).

```json
{
  "flow_estimation": {
    "type": "external",
    "confidence": 0.85,
    "reasoning": "단일 폐곡면, genus=0, 외부 유동 물체로 추정",
    "alternatives": ["internal"]
  }
}
```

추정 규칙:
- 단일 폐곡면 + genus=0 → 외부 유동 (높은 확신)
- 복수 connected component + 내부 공간 → 내부 유동
- 관 형태 (aspect ratio 높음, 양단 개방) → 내부 유동 (파이프)
- 혈관 분기 (다수 개방 경계) → 내부 유동 (hemodynamics)
- 확신도 낮으면 → CLI에서 사용자에게 확인 요청

### 4. 문제 진단

```json
{
  "issues": [
    {
      "severity": "warning",
      "type": "non_manifold_edges",
      "count": 3,
      "description": "3개의 non-manifold 엣지 감지. Preprocessor에서 수리 필요.",
      "recommended_action": "repair"
    },
    {
      "severity": "info",
      "type": "high_face_count",
      "count": 500000,
      "description": "표면 삼각형 수 과다. 리메쉬 권장.",
      "recommended_action": "remesh"
    }
  ]
}
```

심각도 레벨:
- `critical`: 메쉬 생성 불가 (e.g., 열린 표면 + 외부 유동)
- `warning`: 품질 저하 예상 (e.g., non-manifold 엣지)
- `info`: 최적화 기회 (e.g., 과다 삼각형)

### 5. Tier 호환성 사전 평가

품질 레벨(draft/standard/fine)별 권장 Tier를 포함한다.

```json
{
  "tier_compatibility": {
    "draft": {
      "recommended_tier": "tier2_tetwild",
      "notes": "TetWild coarse epsilon — 빠른 geometry 검증용"
    },
    "standard_netgen": {
      "compatible": true,
      "notes": "CAD B-Rep 직접 처리, 범용 Tet 메쉬"
    },
    "standard_cfmesh": {
      "compatible": true,
      "notes": "Hex-dominant, BL 자동, 내부/외부 유동"
    },
    "fine_snappy": {
      "compatible": true,
      "notes": "외부 유동 최적, BL 자동 생성, 시간 많이 소요"
    },
    "fine_tetwild_mmg": {
      "compatible": true,
      "notes": "불량 지오메트리에서 fine 품질 달성 시 MMG 후처리"
    }
  }
}
```

---

## 파일 포맷별 로딩 전략

| 입력 타입 | 로딩 방법 | 비고 |
|----------|----------|------|
| STL/OBJ/PLY/OFF/3MF | `trimesh.load()` | 직접 표면 메쉬 |
| STEP/IGES/BREP | `cadquery`/`build123d` 또는 `gmsh` CLI | B-Rep → 테셀레이션 필요 |
| Gmsh .msh | `meshio.read()` | 표면/볼륨 메쉬 |
| VTK/VTU/VTP | `meshio.read()` 또는 `pyvista.read()` | |
| Fluent .msh | `meshio.read()` 또는 `fluentMeshToFoam` | |
| CGNS | `meshio.read()` | HDF5 기반 |
| Nastran/Abaqus | `meshio.read()` | 구조해석 메쉬 변환 |
| OpenFOAM polyMesh | 직접 파싱 | boundary 추출 |

---

## 구현 참고사항

- Analyzer는 **읽기 전용**이다. 입력 파일을 절대 수정하지 않는다.
- 분석 소요 시간은 파일 크기에 비례하나, 대부분 < 10초를 목표로 한다.
- 대용량 STL (100만+ 삼각형)의 경우 샘플링 기반 통계를 사용한다.
- 모든 분석 결과는 `geometry_report.json` 단일 파일에 집약한다.
- CAD 파일 (STEP/IGES)의 경우, 테셀레이션 없이도 분석 가능한 항목을 먼저 추출한다.

---

## 테스트 시나리오

```bash
# 정상 STL
python -m auto_tessell analyze sphere.stl

# 불량 STL (non-manifold)
python -m auto_tessell analyze broken_mesh.stl

# CAD 파일
python -m auto_tessell analyze naca0012.step

# 기존 메쉬 변환
python -m auto_tessell analyze existing.msh

# 분석만 수행 (메쉬 생성 없이)
auto-tessell input.stl --dry-run
```