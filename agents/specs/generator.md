# Agent: Generator (메쉬 생성 에이전트)

## 역할

Strategist의 `mesh_strategy.json`에 따라 실제 볼륨 메쉬를 생성한다.
**Draft → Standard → Fine** 품질 레벨 순서로 실행하며, 실패 시 fallback Tier로 자동 전환한다.
최종 결과를 OpenFOAM polyMesh 형식으로 출력한다.

---

## 입력

- `mesh_strategy.json` (Strategist, `quality_level` 포함)
- `preprocessed.stl` (Preprocessor) 또는 원본 CAD 파일 (패스스루)
- CLI 파라미터

## 출력

- `case/constant/polyMesh/` (OpenFOAM polyMesh)
- `generator_log.json` (실행 이력, Evaluator에 전달)

---

## 실행 흐름

```
mesh_strategy.json 읽기 (quality_level 확인)
    │
    ▼
선택된 Tier 실행 시도
    │
    ├── 성공 → OpenFOAM polyMesh 출력 → generator_log.json 기록
    │
    └── 실패 → work_dir 초기화 → fallback Tier 시도
                    │
                    ├── 성공 → ...
                    │
                    └── 모든 Tier 실패 → 에러 리포트 (Tier 상향 또는 quality_level 하향 권고)
```

---

## Volume Tier별 실행 상세

### Draft: TetWild (coarse, ~30초)

빠른 geometry 검증용. epsilon을 크게 설정해 속도 우선.

```python
import pytetwild  # pip install pytetwild

import trimesh as _trimesh
surf = _trimesh.load(str(preprocessed_path))
vertices = surf.vertices
faces = surf.faces

tet_v, tet_f = pytetwild.tetrahedralize(
    vertices,
    faces,
    stop_energy=strategy["tier_specific_params"].get("tetwild_stop_energy", 10.0),
    # edge_len_r는 선택적
)

import meshio
tet_mesh = meshio.Mesh(points=tet_v, cells=[("tetra", tet_f)])
meshio.write("tetwild_result.msh", tet_mesh)
meshio.openfoam.write(case_dir, tet_mesh)
```

**Draft용 기본 파라미터:**
```json
{
  "tetwild_epsilon": 0.02,
  "tetwild_stop_energy": 20.0
}
```

**실패 조건:** pytetwild import 실패, 메모리 초과, 0-volume 셀

### Standard: Netgen (중간 품질, ~수분)

CAD B-Rep 직접 지원. STL도 처리 가능.

```python
import netgen.meshing as nm
from netgen.occ import OCCGeometry

if is_cad_file:
    geo = OCCGeometry(input_path)
else:
    geo = nm.STLGeometry(input_path)

mesh = geo.GenerateMesh(
    maxh=strategy["surface_mesh"]["target_cell_size"],
    minh=strategy["surface_mesh"]["min_cell_size"],
    grading=strategy["tier_specific_params"].get("netgen_grading", 0.3),
    curvaturesafety=strategy["tier_specific_params"].get("netgen_curvaturesafety", 2.0),
    segmentsperedge=strategy["tier_specific_params"].get("netgen_segmentsperedge", 1.0),
)
mesh.Export("mesh.msh", "Gmsh2 Format")
run_openfoam_utility("gmshToFoam", "mesh.msh", case_dir)
```

**실패 조건:** netgen import 실패, STL 지오메트리 거부, gmshToFoam 에러

### Standard: cfMesh (내부/외부 유동, ~수분)

cartesianMesh 기반. Boundary Layer 자동 생성.

```python
def generate_cfmesh_dict(strategy):
    return {
        "surfaceFile":     '"constant/triSurface/surface.stl"',
        "maxCellSize":     strategy["tier_specific_params"].get(
                               "cfmesh_max_cell_size",
                               strategy["surface_mesh"]["target_cell_size"] * 4),
        "minCellSize":     strategy["surface_mesh"]["min_cell_size"],
        "boundaryCellSize": strategy["surface_mesh"]["target_cell_size"],
        "boundaryLayers": {
            "nLayers":        strategy["boundary_layers"]["num_layers"],
            "thicknessRatio": strategy["boundary_layers"]["growth_ratio"],
            "maxFirstLayerThickness": strategy["boundary_layers"]["first_layer_thickness"],
        }
    }

run_openfoam("cartesianMesh", case_dir)
```

**실패 조건:** cfMesh 미설치, 지오메트리 거부

### Fine: snappyHexMesh (외부 유동 + BL, ~30분+)

가장 복잡한 Tier. 3단계 파이프라인.

```
1. blockMesh              기본 hex 도메인 생성
2. surfaceFeatureExtract  STL 특징선 추출
3. snappyHexMesh          castellated → snap → addLayers
```

**blockMeshDict 생성:**
```python
def generate_block_mesh_dict(strategy):
    domain = strategy["domain"]
    base_cell = domain["base_cell_size"]
    nx = int((domain["max"][0] - domain["min"][0]) / base_cell)
    ny = int((domain["max"][1] - domain["min"][1]) / base_cell)
    nz = int((domain["max"][2] - domain["min"][2]) / base_cell)
    # 8개 꼭짓점 + block 정의 반환
```

**snappyHexMeshDict 핵심 파라미터:**
```python
{
    "castellatedMeshControls": {
        "resolveFeatureAngle": strategy["surface_mesh"]["feature_angle"],
        "locationInMesh": strategy["domain"]["location_in_mesh"],
        "features": [{"file": "surface.eMesh", "level": 1}],
        "refinementSurfaces": {"surface": {"level": [2, 3]}}
    },
    "snapControls": {
        "tolerance": strategy["tier_specific_params"].get("snappy_snap_tolerance", 2.0),
        "nSolveIter": strategy["tier_specific_params"].get("snappy_snap_iterations", 5),
    },
    "addLayersControls": {
        "layers": {"surface": {"nSurfaceLayers": strategy["boundary_layers"]["num_layers"]}},
        "firstLayerThickness": strategy["boundary_layers"]["first_layer_thickness"],
        "expansionRatio": strategy["boundary_layers"]["growth_ratio"],
    },
    "meshQualityControls": {
        "maxNonOrtho": strategy["quality_targets"]["max_non_orthogonality"],
        "maxInternalSkewness": strategy["quality_targets"]["max_skewness"],
        "minDeterminant": strategy["quality_targets"]["min_determinant"],
    }
}
```

**실행:**
```python
shutil.copy("preprocessed.stl", f"{case_dir}/constant/triSurface/surface.stl")
run_openfoam("blockMesh", case_dir)
run_openfoam("surfaceFeatureExtract", case_dir)
run_openfoam("snappyHexMesh", case_dir, args=["-overwrite"])
```

**실패 조건:** blockMesh 셀 수 부족, snap 실패, BL layer 축소/제거

### Fine + MMG: TetWild coarse → MMG 후처리 (Tet 대안)

snappyHexMesh 실패 시 TetWild standard + MMG로 대체.

```python
tet_v, tet_f = pytetwild.tetrahedralize(
    vertices, faces,
    stop_energy=strategy["tier_specific_params"].get("tetwild_stop_energy", 10.0),
)
# MMG 품질 후처리
if shutil.which("mmg3d"):
    cmd = ["mmg3d", "result.msh",
           "-hmin", str(params.get("mmg_hmin", min_cell_size)),
           "-hmax", str(params.get("mmg_hmax", target_cell_size)),
           "-hgrad", str(params.get("mmg_hgrad", 1.3)),
           "-hausd", str(params.get("mmg_hausd", 0.01)),
           "-o", "optimized.mesh"]
    subprocess.run(cmd, timeout=1800)
```

---

## OpenFOAM polyMesh 출력 공통

```
case/
├── constant/
│   ├── polyMesh/          (boundary, faces, neighbour, owner, points)
│   └── triSurface/surface.stl
└── system/
    ├── controlDict
    ├── fvSchemes
    └── fvSolution
```

비-OpenFOAM Tier (Draft, Standard Netgen)의 경우 meshio로 변환:
```python
mesh = meshio.read("result.msh")
meshio.openfoam.write(case_dir, mesh)
```

---

## generator_log.json 스키마

```json
{
  "execution_summary": {
    "quality_level": "standard",
    "selected_tier": "tier05_netgen",
    "tiers_attempted": [
      {
        "tier": "tier05_netgen",
        "status": "success",
        "time_seconds": 45.2,
        "mesh_stats": {
          "num_cells": 345678,
          "num_points": 567890,
          "num_faces": 890123,
          "num_boundary_patches": 3
        }
      }
    ],
    "output_dir": "case/constant/polyMesh",
    "total_time_seconds": 45.2
  }
}
```

---

## OpenFOAM 유틸리티 실행 래퍼

```python
import subprocess, os

def run_openfoam(utility: str, case_dir: str, args: list = None) -> subprocess.CompletedProcess:
    of_dir = os.environ.get("OPENFOAM_DIR", "/opt/openfoam13")
    source_cmd = f"source {of_dir}/etc/bashrc"
    cmd_parts = [utility, "-case", case_dir] + (args or [])
    result = subprocess.run(
        ["bash", "-c", f"{source_cmd} && {' '.join(cmd_parts)}"],
        capture_output=True, text=True, timeout=3600
    )
    if result.returncode != 0:
        raise OpenFOAMError(utility, result.returncode, result.stdout, result.stderr)
    return result
```

---

## 테스트 시나리오

```bash
# Draft (빠른 검증, TetWild coarse)
auto-tessell generate --strategy mesh_strategy.json --tier tetwild

# Standard (Netgen)
auto-tessell generate --strategy mesh_strategy.json --tier netgen

# Standard (cfMesh)
auto-tessell generate --strategy mesh_strategy.json --tier cfmesh

# Fine (snappyHexMesh + BL)
auto-tessell generate --strategy mesh_strategy.json --tier snappy

# 전체 파이프라인 (quality_level 기반 자동 Tier 선택 + fallback)
auto-tessell sphere.stl -o ./case --quality standard --verbose
```
