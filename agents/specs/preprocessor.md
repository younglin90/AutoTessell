# Agent: Preprocessor (전처리 에이전트)

## 역할

Analyzer의 `geometry_report.json`을 기반으로 입력 지오메트리를 정제한다.
**표면 메쉬를 L1 → L2 → L3 순서로 점진적으로 품질을 개선**하며, 각 단계 후 gate 검사를 통과하면 다음 단계를 건너뛴다.
Generator의 Volume Phase가 사용할 수 있는 watertight + manifold 표면 메쉬를 생산한다.

---

## 입력

- 원본 입력 파일
- `geometry_report.json` (Analyzer 출력)
- CLI 파라미터 (수리/리메쉬 관련)

## 출력

- `preprocessed.stl` (정제된 표면 메쉬, STL binary 포맷)
- `preprocessed_report.json` (수행한 작업 이력 + 도달한 표면 품질 레벨)
- (STEP/IGES 직접 지원 Tier의 경우) 원본 CAD 파일을 그대로 패스스루

---

## 처리 파이프라인 (2-Phase Surface → Gate)

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
│  L1 (Repair):  pymeshfix + trimesh               │
│      │  Gate: watertight + manifold?             │
│      │  Yes → 완료  No → L2                      │
│      ▼                                           │
│  L2 (Remesh):  pyACVD + geogram RVD              │
│      │  Gate: watertight + manifold?             │
│      │  Yes → 완료  No → L3                      │
│      ▼                                           │
│  L3 (AI fix):  MeshAnything (GPU, 최후 수단)      │
│      │  Gate: watertight + manifold?             │
│      │  No → 에러 리포트 (Tier 2 TetWild 강제)    │
└────────┬────────────────────────────────────────┘
         ▼
    preprocessed.stl
    (surface_quality_level: l1_repair | l2_remesh | l3_ai)
```

---

## 단계별 상세

### 0. 포맷 변환

CAD B-Rep 파일을 표면 메쉬로 변환한다.

| 입력 | 변환 방법 | 출력 |
|------|----------|------|
| STEP/STP | cadquery/build123d `exportStl()` 또는 gmsh CLI → STL | STL |
| IGES/IGS | cadquery 또는 gmsh CLI | STL |
| BREP | pythonocc-core | STL |
| OBJ/PLY/OFF/3MF | trimesh.load() → export('stl') | STL |
| Gmsh .msh | meshio → trimesh | STL |
| VTK/VTU/VTP | meshio/pyvista → 표면 추출 → STL | STL |
| Fluent .msh | meshio → 표면 추출 → STL | STL |
| Nastran/Abaqus | meshio → 표면 추출 → STL | STL |

**패스스루 규칙:**
- Tier 0.5 (Netgen)이 선택된 경우: STEP/IGES를 변환하지 않고 원본 그대로 전달
- 패스스루 시에도 CAD 수준 수리 수행 (sewing, tolerance fix 등)

### L1: 표면 수리 (Repair)

`geometry_report.json`의 `issues` 배열을 참조하여 필요한 수리를 수행한다.

| 문제 | 라이브러리 | 수리 방법 |
|------|-----------|----------|
| Non-manifold 엣지 | pymeshfix | `MeshFix.repair()` |
| 열린 구멍 | pymeshfix | 자동 hole filling |
| 중복 면/정점 | trimesh | `merge_vertices()`, `remove_degenerate_faces()` |
| 자기 교차 | pymeshfix | `MeshFix.repair()` |
| 법선 방향 불일치 | trimesh | `fix_normals()` |
| 영 면적 삼각형 | trimesh | `remove_degenerate_faces()` |
| Disconnected component | trimesh | 최대 component만 보존 |

**수리 수행 기준:**
- `issues.severity: critical` → 무조건 수리
- `severity: warning` → 기본 수리, `--no-repair`로 비활성화 가능
- `--force-repair` → 모든 문제 강제 수리

**Gate 검사 후:**
- watertight + manifold → `surface_quality_level: "l1_repair"`, L2 건너뜀
- 실패 → L2 진입

### L2: 표면 리메쉬 (Remesh)

pyACVD Voronoi 기반 균일 리메쉬로 삼각형 품질 향상. 추가로 geogram RVD 리메쉬 적용 가능.

**활성화 조건 (L1 gate 실패 시 자동):**
- `edge_length_ratio > 100`
- `num_faces > 200000`
- `has_degenerate_faces: true`

**pyACVD 파라미터:**
```
--remesh-target-faces INT     # 목표 삼각형 수 (기본: BBox 기반 자동 계산)
--remesh-subdivide INT        # 사전 subdivision 횟수 (기본: 3)
```

**자동 목표 삼각형 수:**
```python
target_faces = max(10000, min(100000, int(surface_area / (element_size ** 2) * 2)))
```

**geogram RVD 리메쉬 (pyACVD 후 추가 적용):**
```python
# geogram은 auto_tessell_core C++ 확장을 통해 호출
import auto_tessell_core as atc
atc.remesh_surface(
    input_stl="l2_pyacvd.stl",
    output_stl="l2_geogram.stl",
    target_edge_length=element_size,
    nb_lloyd_iter=30,
)
```

**pymeshlab으로 추가 품질 개선:**
```python
import pymeshlab
ms = pymeshlab.MeshSet()
ms.load_new_mesh("l2_pyacvd.stl")
ms.meshing_isotropic_explicit_remeshing(targetlen=pymeshlab.AbsoluteValue(element_size))
ms.save_current_mesh("l2_meshlab.stl")
```

**Gate 검사 후:**
- watertight + manifold → `surface_quality_level: "l2_remesh"`, L3 건너뜀
- 실패 → L3 진입 (GPU 필요, 사용자 동의 또는 `--allow-ai-fallback` 필요)

### L3: AI 표면 재생성 (AI Fix, 최후 수단)

두 가지 AI 엔진 중 하나를 사용해 표면 메쉬를 재생성한다.
우선순위: **meshgpt-pytorch** (MIT, 상업 OK) → 실패 시 **MeshAnythingV2** (S-Lab, 비상업)

**공통 제약:**
- GPU 필수. CPU 추론 불가.
- 경계 패치 정보 손실 가능 (feature edge 비보존)
- 출력은 표면 메쉬 전용 (볼륨 메쉬 아님)
- `--allow-ai-fallback` 플래그 또는 config `ai_fallback: true` 필요
- GPU 가용 확인: `torch.cuda.is_available()`

#### L3-A: meshgpt-pytorch (우선 사용)

| 항목 | 내용 |
|------|------|
| 라이선스 | **MIT — 상업적 사용 가능** |
| 설치 | `pip install meshgpt-pytorch` |
| 입력 | vertex + face 텐서 (기학습 모델 또는 fine-tune) |
| 출력 | 표면 삼각 메쉬 |
| GPU | CUDA 필수 (Ampere+ 권장) |
| 성숙도 | 연구용 구현, production 품질 보장 어려움 |

```python
from meshgpt_pytorch import MeshAutoencoder, MeshTransformer
import torch

# 사전학습 모델 로드 (HuggingFace: MarcusLoren/MeshGPT-preview)
transformer = MeshTransformer.from_pretrained("MarcusLoren/MeshGPT-preview")
transformer.eval().cuda()

# 입력 STL → 포인트 샘플링 → 추론
vertices, faces = stl_to_tensors(input_stl)
with torch.no_grad():
    output_mesh = transformer.generate(vertices=vertices, faces=faces)
save_mesh(output_mesh, "l3_meshgpt.stl")
```

#### L3-B: MeshAnythingV2 (L3-A 실패 시 fallback)

| 항목 | 내용 |
|------|------|
| 라이선스 | **S-Lab License 1.0 — 비상업 전용** |
| | 상업적 사용 시 S-Lab(buaacyw) 허가 필요. Phase 2 SaaS 배포 전 반드시 확인. |
| 설치 | git clone + conda (Python 3.10, CUDA 11.8) |
| 입력 | 포인트 클라우드 (.npy, N×6 with normals) 또는 dense mesh |
| 출력 | 표면 메쉬 (최대 1,600 faces) |
| GPU | ~8GB VRAM, CUDA 11.8+, A800/A6000 기준 ~45초/mesh |
| 설치 경로 | `$MESHANYTHING_V2_DIR` 환경변수로 지정 |

```python
import sys, os
ma_dir = os.environ.get("MESHANYTHING_V2_DIR")
if not ma_dir:
    raise RuntimeError("MESHANYTHING_V2_DIR 환경변수 미설정")
sys.path.insert(0, ma_dir)

import torch
if not torch.cuda.is_available():
    raise RuntimeError("MeshAnythingV2: GPU 없음, 건너뜀")

from main import load_model
model = load_model()
point_cloud = stl_to_point_cloud(input_stl)  # N×6 numpy array
output_mesh = model.inference(point_cloud)
output_mesh.export("l3_meshanything.stl")
```

**L3 실행 순서:**
```python
for engine in ["meshgpt", "meshanything"]:
    try:
        result = run_l3_engine(engine, input_stl)
        if gate_check(result):  # watertight + manifold
            return result, "l3_ai"
    except Exception:
        continue
raise RuntimeError("L3 AI 엔진 모두 실패 → TetWild 강제 사용")
```

**Gate 검사 후:**
- watertight + manifold → `surface_quality_level: "l3_ai"`
- 실패 → 에러 리포트, Generator에서 TetWild 강제 사용

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
      {
        "step": "format_conversion",
        "method": "cadquery.exportStl",
        "params": {"linear_deflection": 0.001, "angular_deflection": 15.0},
        "input_faces": null,
        "output_faces": 24500,
        "time_seconds": 2.1
      },
      {
        "step": "l1_repair",
        "method": "pymeshfix",
        "issues_fixed": ["non_manifold_edges(3)", "holes(1)"],
        "input_faces": 24500,
        "output_faces": 24512,
        "gate_passed": false,
        "time_seconds": 0.8
      },
      {
        "step": "l2_remesh",
        "method": "pyacvd+pymeshlab",
        "params": {"target_faces": 30000, "subdivide": 3},
        "input_faces": 24512,
        "output_faces": 30000,
        "gate_passed": true,
        "time_seconds": 1.3
      }
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
# 정상 STL (L1만으로 통과)
auto-tessell preprocess sphere.stl

# 불량 STL (L2까지 필요)
auto-tessell preprocess broken.stl --verbose

# STEP → STL 변환 후 L1
auto-tessell preprocess naca0012.step --cad-linear-deflection 0.0005

# L2 리메쉬 강제 (품질 기준 낮출 때)
auto-tessell preprocess high_res.stl --surface-remesh --remesh-target-faces 50000

# AI fallback 허용 (L3)
auto-tessell preprocess broken.stl --allow-ai-fallback

# Netgen 패스스루 (STEP 원본 유지)
auto-tessell preprocess model.step --tier netgen

# 수리 없이 강제 진행
auto-tessell preprocess bad.stl --no-repair
```
