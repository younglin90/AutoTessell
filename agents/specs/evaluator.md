# Agent: Evaluator (품질 평가 에이전트)

## 역할

Generator가 생성한 메쉬의 품질을 **객관적으로 검증**한다.
OpenFOAM `checkMesh` 결과 파싱과 자체 정량 지표 계산을 수행하며,
**품질 레벨(QualityLevel)별 차등 기준**을 적용해 PASS/FAIL을 판정하고 구체적인 개선 권고사항을 제공한다.

Anthropic harness 패턴 원칙: **생성자가 자기 작업을 평가하면 관대해진다.**
Evaluator는 Generator와 완전히 분리되어 독립적으로 판단한다.

---

## 입력

- `case/constant/polyMesh/` (Generator 출력)
- `generator_log.json` (Generator, `quality_level` 포함)
- `mesh_strategy.json` (Strategist, 목표 품질 기준 참조)
- `geometry_report.json` (Analyzer, 원본 지오메트리 대비 검증)

## 출력

- `quality_report.json` (Strategist에 피드백, 또는 최종 리포트)

---

## 평가 파이프라인

```
1. checkMesh 실행 및 파싱
        │
        ▼
2. 자체 정량 지표 계산
        │
        ▼
3. 지오메트리 충실도 검증
        │
        ▼
4. QualityLevel별 PASS/FAIL 판정 + 피드백 생성
        │
        ▼
   quality_report.json
```

---

## 단계별 상세

### 1. checkMesh 실행 및 파싱

```python
def run_checkmesh(case_dir: str) -> CheckMeshResult:
    result = run_openfoam("checkMesh", case_dir, args=["-allGeometry", "-allTopology"])
    return parse_checkmesh_output(result.stdout)
```

**파싱 대상 항목:**

| 항목 | 추출 방법 |
|------|----------|
| cells | `"cells: N"` |
| faces | `"faces: N"` |
| points | `"points: N"` |
| internal faces | `"internal faces: N"` |
| Max non-orthogonality | `"Max non-orthogonality = N"` |
| Avg non-orthogonality | `"average non-orthogonality = N"` |
| Max skewness | `"Max skewness = N"` |
| Max aspect ratio | `"Max aspect ratio = N"` |
| Min face area | `"Minimum face area = N"` |
| Min cell volume | `"Min volume = N"` |
| Min determinant | `"Min determinant = N"` |
| Negative volumes | `"***Error: N negative volumes"` |
| Highly non-ortho faces | `"Number of severely non-orthogonal ... faces: N"` |
| Failed checks | `"Failed N mesh checks"` |

**checkMesh 전체 통과 판정:**
```
"Mesh OK." → 기본 통과 (추가 정량 평가 진행)
"Failed N mesh checks." → 즉시 FAIL
```

### 2. 자체 정량 지표 계산

checkMesh만으로는 부족한 지표를 pyvista/meshio로 직접 계산한다.

```python
import pyvista as pv

def compute_additional_metrics(case_dir: str) -> dict:
    run_openfoam("foamToVTK", case_dir)
    mesh = pv.read(f"{case_dir}/VTK/case_0.vtk")
    cell_sizes = mesh.compute_cell_sizes()
    return {
        "cell_volume_stats": {
            "min": float(cell_sizes["Volume"].min()),
            "max": float(cell_sizes["Volume"].max()),
            "mean": float(cell_sizes["Volume"].mean()),
            "ratio_max_min": float(cell_sizes["Volume"].max() /
                                   max(cell_sizes["Volume"].min(), 1e-30))
        }
    }
```

### 3. 지오메트리 충실도 검증

```python
def check_geometry_fidelity(case_dir: str, original_stl: str) -> dict:
    import trimesh
    original = trimesh.load(original_stl)
    boundary_mesh = extract_boundary_surface(case_dir)
    hausdorff = compute_hausdorff_distance(original, boundary_mesh)
    return {
        "hausdorff_distance": hausdorff,
        "hausdorff_relative": hausdorff / geometry_report["geometry"]["bounding_box"]["diagonal"],
        "area_deviation_percent": abs(boundary_mesh.area - original.area) / original.area * 100
    }
```

### 4. QualityLevel별 PASS/FAIL 판정

**Hard FAIL 조건 — QualityLevel별 차등 기준:**

| 조건 | draft | standard | fine |
|------|-------|---------|------|
| Negative volumes | > 0 | > 0 | > 0 |
| checkMesh failed checks | > 0 | > 0 | > 0 |
| Min cell volume | ≤ 0 | ≤ 0 | ≤ 0 |
| Min determinant | ≤ 0 | ≤ 0 | ≤ 0 |
| Max non-orthogonality | > 85° | > 70° | > 65° |
| Max skewness | > 8.0 | > 6.0 | > 4.0 |
| Hausdorff relative | > 0.10 (10%) | > 0.05 (5%) | > 0.02 (2%) |

**Soft FAIL 조건 (2개 이상이면 FAIL):**

| 조건 | draft | standard | fine |
|------|-------|---------|------|
| Max non-orthogonality | > 80° | > 65° | > 60° |
| Max skewness | > 6.0 | > 4.0 | > 3.0 |
| Max aspect ratio | > 1000 | > 200 | > 100 |
| Cell volume ratio | > 100000 | > 10000 | > 1000 |
| Surface area deviation | > 20% | > 10% | > 5% |
| BL 미생성 비율 | N/A | > 30% | > 20% |

**판정 로직:**
```python
def evaluate(checkmesh, metrics, fidelity, strategy) -> Verdict:
    quality_level = strategy.quality_level  # draft / standard / fine
    hard_fails = check_hard_fails(checkmesh, metrics, fidelity, quality_level)
    soft_fails = check_soft_fails(checkmesh, metrics, fidelity, quality_level)

    if hard_fails:
        return Verdict.FAIL, hard_fails, generate_recommendations(hard_fails)
    elif len(soft_fails) >= 2:
        return Verdict.FAIL, soft_fails, generate_recommendations(soft_fails)
    elif soft_fails:
        return Verdict.PASS_WITH_WARNINGS, soft_fails, generate_recommendations(soft_fails)
    else:
        return Verdict.PASS, [], []
```

---

## 개선 권고사항 생성

```python
RECOMMENDATION_RULES = {
    "high_non_orthogonality": {
        "recommendations": [
            "snappy_snap_tolerance 증가",
            "snappy_snap_iterations 증가",
            "castellated level 1단계 상향",
        ]
    },
    "negative_volumes": {
        "recommendations": [
            "BL 층 수 축소",
            "BL growth ratio 축소",
            "BL feature angle 축소",
        ]
    },
    "high_skewness": {
        "recommendations": [
            "셀 크기 축소",
            "snap nSolveIter 증가",
            "pyACVD target faces 증가 후 재전처리",
        ]
    },
    "geometry_deviation": {
        "recommendations": [
            "snap tolerance 축소",
            "castellated level 상향",
            "원본 STL 삼각형 수 확인 (L2 리메쉬 재수행 권고)",
        ]
    }
}
```

---

## quality_report.json 스키마

```json
{
  "evaluation_summary": {
    "verdict": "FAIL",
    "quality_level": "standard",
    "iteration": 1,
    "tier_evaluated": "tier05_netgen",
    "evaluation_time_seconds": 12.3,

    "checkmesh": {
      "cells": 345678,
      "faces": 890123,
      "points": 567890,
      "max_non_orthogonality": 73.2,
      "avg_non_orthogonality": 8.7,
      "max_skewness": 3.2,
      "max_aspect_ratio": 45.6,
      "min_determinant": 0.012,
      "negative_volumes": 0,
      "failed_checks": 1,
      "mesh_ok": false
    },

    "additional_metrics": {
      "cell_volume_stats": {
        "min": 3.4e-15, "max": 8.0e-9, "ratio_max_min": 2352941
      }
    },

    "geometry_fidelity": {
      "hausdorff_relative": 0.0017,
      "area_deviation_percent": 2.1
    },

    "hard_fails": [
      {
        "criterion": "max_non_orthogonality",
        "value": 73.2,
        "threshold": 70.0,
        "quality_level": "standard"
      }
    ],

    "soft_fails": [],

    "recommendations": [
      {
        "priority": 1,
        "action": "snap_tolerance 증가",
        "current_value": 2.0,
        "suggested_value": 4.0
      }
    ]
  }
}
```

---

## 터미널 출력 (Rich 포맷)

```
╭──────────────── Mesh Quality Report ────────────────╮
│  Verdict: ❌ FAIL  │  Quality: standard  │  iter 1/3  │
│  Tier: Netgen  │  Cells: 345,678                     │
│                                                      │
│  ┌──────────────────┬────────┬──────────┬─────┐      │
│  │ Metric           │ Value  │ Target   │ OK  │      │
│  ├──────────────────┼────────┼──────────┼─────┤      │
│  │ Max Non-Ortho    │ 73.2°  │ < 70°    │ ❌  │      │
│  │ Max Skewness     │ 3.2    │ < 6.0    │ ✅  │      │
│  │ Negative Volumes │ 0      │ 0        │ ✅  │      │
│  │ Hausdorff Rel.   │ 0.17%  │ < 5%     │ ✅  │      │
│  └──────────────────┴────────┴──────────┴─────┘      │
│                                                      │
│  1. snap_tolerance: 2.0 → 4.0                       │
╰──────────────────────────────────────────────────────╯
```

---

## 테스트 시나리오

```bash
# draft 품질 검증
auto-tessell evaluate --case ./case --geometry-report geometry_report.json --quality draft

# standard (기본)
auto-tessell evaluate --case ./case --geometry-report geometry_report.json

# fine 품질 검증 (엄격)
auto-tessell evaluate --case ./case --geometry-report geometry_report.json --quality fine

# checkMesh 파싱 단위 테스트
pytest tests/test_evaluator.py -v -k "test_parse_checkmesh"
```
