# Agent: Evaluator (품질 평가 에이전트)

## 핵심 철학

**외부 라이브러리에 의존하지 않고 우리 코드로 직접 구현**한다.
OpenFOAM `checkMesh` 의 모든 지표 계산 공식·판정 로직을 **카피하여 우리 Python 코드로 직접 구현**한다.
**NativeMeshChecker** (`core/evaluator/native_checker.py`) 가 기본, OpenFOAM 유틸리티는 교차 검증용.

**최종 목표** : 외부 라이브러리 없이 `NativeMeshChecker` 단독으로 PASS/FAIL 판정.

---

## 역할

Generator 가 생성한 메쉬 품질을 **객관적으로 검증**. QualityLevel 별 차등 기준으로 PASS/FAIL 판정.

**변경 사항** : Strategist 에게 자동 피드백하는 **자동 재시도 루프 제거**.
FAIL 시 사용자에게 recommendation 출력 후 **재시도 여부를 사용자에게 질문** (`y/N`).

---

## 입력 / 출력

- 입력:
  - `case/constant/polyMesh/`
  - `generator_log.json` (mesh_type, quality_level 포함)
  - `mesh_strategy.json` (목표 품질 기준 참조)
  - `geometry_report.json` (Analyzer, 원본 대비 검증)
- 출력: `quality_report.json` (최종 리포트)

---

## 평가 파이프라인

```
1. NativeMeshChecker 실행 (checkMesh 카피)
    │
    ▼
2. 추가 정량 지표 (자체 계산)
    │
    ▼
3. 지오메트리 충실도 (Hausdorff, surface area)
    │
    ▼
4. QualityLevel 별 PASS/FAIL 판정
    │
    ▼
5. PASS → quality_report.json 저장, 종료
   FAIL → recommendation 출력 + 사용자에게 "재실행할까요? (y/N)"
```

---

## 1. NativeMeshChecker — checkMesh 자체 구현

`core/evaluator/native_checker.py` 에서 OpenFOAM `checkMesh` 공식 그대로 포팅.

### 구현 완료 지표

| 지표 | 계산 공식 |
|------|----------|
| cells / faces / points / internal faces | polyMesh 직접 읽기 |
| Max / Avg non-orthogonality | 이웃 두 셀 centroid-connecting vector 와 face normal 의 각도 (`|cos|` abs) |
| Max skewness | centroid-connecting vector 와 face centroid 의 offset 비율 |
| Max aspect ratio | cell bbox edge 최대/최소 비율 |
| Min face area | polygon 면적 합 |
| Min cell volume | face-pyramid 합 divergence theorem |
| Min determinant | per-cell 부피 일관성 검증 |
| Negative volumes | volume < 0 카운트 |
| Highly non-ortho count | threshold 초과 face 수 |

### 이중 실행 + 교차 검증

당분간 `--checker-engine auto` 기본값은 OpenFOAM `checkMesh` 우선, native fallback.
**점진적 전환** : native 가 OpenFOAM 결과와 일치하는지 회귀 테스트 추가 → 일치 확인되면 native 기본값.

```python
def run_checker(case_dir, engine="auto"):
    if engine == "native":
        return NativeMeshChecker(case_dir).run()
    if engine == "openfoam" or (engine == "auto" and openfoam_available()):
        try:
            return parse_checkmesh_output(run_openfoam("checkMesh", case_dir))
        except Exception:
            return NativeMeshChecker(case_dir).run()  # fallback
    return NativeMeshChecker(case_dir).run()
```

---

## 2. 추가 정량 지표 (자체 계산)

외부 의존 없이 numpy + 자체 polyMesh reader 로 직접:

```python
def compute_additional_metrics(case_dir):
    poly = read_polymesh(case_dir)  # core/utils/polymesh_reader.py
    vols = compute_cell_volumes(poly)
    return {
        "cell_volume_stats": {
            "min":  float(vols.min()),
            "max":  float(vols.max()),
            "mean": float(vols.mean()),
            "ratio_max_min": float(vols.max() / max(vols.min(), 1e-30)),
        }
    }
```

---

## 3. 지오메트리 충실도

Hausdorff 거리 자체 구현 (KDTree) + surface area deviation.

```python
def check_geometry_fidelity(case_dir, original_stl, bbox_diag):
    original = load_stl(original_stl)                   # 자체 reader
    boundary = extract_boundary_surface(case_dir)       # 자체 추출
    h = hausdorff_kdtree(original.vertices, boundary.vertices)  # scipy cKDTree
    return {
        "hausdorff_distance": h,
        "hausdorff_relative": h / bbox_diag,
        "area_deviation_percent": abs(boundary.area - original.area) / original.area * 100,
    }
```

---

## 4. QualityLevel 별 판정

### Hard FAIL (1개라도 있으면 FAIL)

| 조건 | draft | standard | fine |
|------|-------|----------|------|
| Negative volumes | > 0 | > 0 | > 0 |
| checkMesh failed checks | > 0 | > 0 | > 0 |
| Min cell volume | ≤ 0 | ≤ 0 | ≤ 0 |
| Min determinant | ≤ 0 | ≤ 0 | ≤ 0 |
| Max non-orthogonality | > 85° | > 70° | > 65° |
| Max skewness | > 8.0 | > 6.0 | > 4.0 |
| Hausdorff relative | > 10% | > 5% | > 2% |

### Soft FAIL (2개 이상이면 FAIL)

| 조건 | draft | standard | fine |
|------|-------|----------|------|
| Max non-orthogonality | > 80° | > 65° | > 60° |
| Max skewness | > 6.0 | > 4.0 | > 3.0 |
| Max aspect ratio | > 1000 | > 200 | > 100 |
| Cell volume ratio | > 100000 | > 10000 | > 1000 |
| Surface area deviation | > 20% | > 10% | > 5% |
| BL 미생성 비율 | N/A | > 30% | > 20% |

### 판정 로직

```python
def evaluate(checker, metrics, fidelity, strategy) -> Verdict:
    q = strategy.quality_level
    hard  = check_hard_fails(checker, metrics, fidelity, q)
    soft  = check_soft_fails(checker, metrics, fidelity, q)
    if hard:
        return Verdict.FAIL, hard, recommendations(hard)
    if len(soft) >= 2:
        return Verdict.FAIL, soft, recommendations(soft)
    if soft:
        return Verdict.PASS_WITH_WARNINGS, soft, recommendations(soft)
    return Verdict.PASS, [], []
```

---

## 5. 사용자 상호작용 (신규)

### PASS

```
✅ PASS  (quality=standard, tier=cfmesh, 42880 cells)
결과: ./case/constant/polyMesh/
```

### FAIL

자동 재시도 없음. 사용자 결정:

```
❌ FAIL
  • max_non_orthogonality = 73.2° (target < 70°)
  • max_skewness = 7.5 (target < 6.0)

권고:
  1. snap_tolerance 2.0 → 4.0
  2. snap_iterations 5 → 10
  3. feature_extract_level 1 → 2

재시도 하시겠습니까? [y/N]:
```

- `y` → Strategist 재호출 (권고 파라미터 반영)
- `N` → 현재 mesh 유지, 종료

CLI flag 로 비대화형 모드도 지원:
- `--auto-retry {off|once|continue}` — off (기본, 사용자 확인), once (한 번만), continue (예전 루프 동작 복원)

---

## quality_report.json 스키마

```json
{
  "evaluation_summary": {
    "verdict": "FAIL",
    "quality_level": "standard",
    "mesh_type": "hex_dominant",
    "tier_evaluated": "cfmesh",
    "evaluation_time_seconds": 12.3,
    "checker_engine_used": "native",

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
      "cell_volume_stats": { "min": 3.4e-15, "max": 8.0e-9, "ratio_max_min": 2352941 }
    },

    "geometry_fidelity": {
      "hausdorff_relative": 0.0017,
      "area_deviation_percent": 2.1
    },

    "hard_fails": [
      { "criterion": "max_non_orthogonality", "value": 73.2, "threshold": 70.0, "quality_level": "standard" }
    ],
    "soft_fails": [],

    "recommendations": [
      { "priority": 1, "action": "snap_tolerance 증가", "current_value": 2.0, "suggested_value": 4.0 }
    ],

    "user_decision": null
  }
}
```

`user_decision` 필드: `retry` / `accept` / `null` (대화형 미진행).

---

## 터미널 출력 (Rich 포맷)

```
╭──────────────── Mesh Quality Report ────────────────╮
│  Verdict: ❌ FAIL  │  Quality: standard              │
│  Mesh: hex_dominant │  Tier: cfmesh │ Cells: 345,678 │
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
│  권고:                                                │
│    1. snap_tolerance: 2.0 → 4.0                      │
│    2. snap_iterations: 5 → 10                        │
│                                                      │
│  재시도 하시겠습니까? [y/N]                           │
╰──────────────────────────────────────────────────────╯
```

---

## 테스트 시나리오

```bash
auto-tessell evaluate --case ./case --geometry-report geometry_report.json --quality draft
auto-tessell evaluate --case ./case --quality fine --checker-engine native
auto-tessell evaluate --case ./case --auto-retry off      # 기본: 사용자 확인
auto-tessell evaluate --case ./case --auto-retry once     # 한 번만 자동 재시도
pytest tests/test_evaluator.py -v -k "test_native_checker"
```
