# Agent: Strategist (전략 에이전트)

## 역할

Analyzer와 Preprocessor의 출력, CLI 파라미터, 그리고 Evaluator의 피드백(재시도 시)을 종합하여 **메쉬 생성 전략**을 수립한다.
**품질 레벨(QualityLevel: draft / standard / fine)**과 **볼륨 Tier**를 선택하고, 도메인 구성 및 파라미터를 결정한다.

Anthropic harness 패턴에서 Planner에 해당하며, Evaluator 피드백을 받아 **전략을 반복 수정**하는 역할도 수행한다.

---

## 입력

- `geometry_report.json` (Analyzer)
- `preprocessed_report.json` (Preprocessor, `surface_quality_level` 포함)
- CLI 파라미터 (`--quality`, `--tier`)
- `quality_report.json` (Evaluator, 재시도 시에만)

## 출력

- `mesh_strategy.json` (Generator 실행 지시서)

---

## QualityLevel 열거형

```python
class QualityLevel(str, Enum):
    DRAFT    = "draft"     # 빠른 검증, 30초 내, geometry 확인용
    STANDARD = "standard"  # 엔지니어링 목적, 수 분 내
    FINE     = "fine"      # 최종 CFD 제출용, 30분+
```

기본값: `standard`. CLI: `--quality draft|standard|fine`

---

## 전략 결정 로직

### 1. 품질 레벨 → 볼륨 Tier 매핑

| QualityLevel | 1차 Tier | Fallback 순서 |
|-------------|---------|--------------|
| draft | tier2_tetwild (epsilon=1e-2) | tier05_netgen → 실패 시 에러 |
| standard | tier05_netgen 또는 tier15_cfmesh | tier2_tetwild → tier0_core |
| fine | tier1_snappy 또는 tier15_cfmesh | tier05_netgen → tier2_tetwild |

### 2. Tier 선택 세부 규칙 (standard / fine)

```
CAD B-Rep (STEP/IGES)?
    └─ Yes → tier05_netgen (B-Rep 직접 처리)

외부 유동 + watertight?
    └─ Yes + fine   → tier1_snappy (BL 자동 생성)
    └─ Yes + standard → tier15_cfmesh 또는 tier05_netgen

내부 유동 + watertight?
    └─ Yes → tier15_cfmesh 또는 tier05_netgen

불량 표면 (surface_quality_level = l3_ai)?
    └─ Yes → tier2_tetwild 강제 (고관용 모드)

단순 형상 + draft?
    └─ Yes → tier2_tetwild (coarse epsilon)
```

### 3. 도메인 설정 (외부 유동)

외부 유동인 경우 STL BBox 기반으로 외부 도메인을 자동 계산한다.

```
기본 도메인 비율:
  업스트림 (x-)  : 10L
  다운스트림 (x+): 20L
  측면 (y±, z±) : 5L

L = characteristic_length (geometry_report에서 획득)
```

**사용자 override:**
```
--domain-upstream FLOAT       # 업스트림 배수 (기본: 10)
--domain-downstream FLOAT     # 다운스트림 배수 (기본: 20)
--domain-lateral FLOAT        # 측면 배수 (기본: 5)
```

### 4. 셀 크기 결정 (QualityLevel 연동)

```python
# QualityLevel별 셀 크기 배율
cell_size_factor = {"draft": 4.0, "standard": 2.0, "fine": 1.0}[quality_level]

base_cell_size = (characteristic_length / 50) * cell_size_factor
surface_cell_size = base_cell_size / 4
min_cell_size = surface_cell_size / 4

# 곡률 기반 보정 (fine에만 적용)
if quality_level == "fine" and curvature_max > 20:
    surface_cell_size *= 0.5
```

### 5. Boundary Layer 파라미터 (fine에만 자동 활성화)

```python
# draft/standard: BL 비활성화 (기본)
# fine: BL 자동 활성화
if quality_level == "fine":
    target_y_plus = 1.0
    Re = estimate_reynolds(characteristic_length, flow_velocity_estimate)
    y_first = characteristic_length * target_y_plus * (Re ** -0.9) * 6.0
    bl_layers = 5
    bl_growth_ratio = 1.2
```

### 6. 품질 목표 (QualityLevel별)

| 지표 | draft | standard | fine |
|------|-------|---------|------|
| max_non_orthogonality | 85° | 70° | 65° |
| max_skewness | 8.0 | 6.0 | 4.0 |
| max_aspect_ratio | 500 | 200 | 100 |
| min_determinant | 0.0001 | 0.001 | 0.001 |
| target_y_plus | N/A | N/A | 1.0 |

---

## mesh_strategy.json 스키마

```json
{
  "strategy_version": 2,
  "iteration": 1,
  "quality_level": "standard",
  "surface_quality_level": "l1_repair",
  "selected_tier": "tier15_cfmesh",
  "fallback_tiers": ["tier05_netgen", "tier2_tetwild"],

  "flow_type": "external",
  "domain": {
    "type": "box",
    "min": [-10.0, -5.0, -5.0],
    "max": [20.0, 5.0, 5.0],
    "base_cell_size": 0.04,
    "location_in_mesh": [-9.0, 0.0, 0.0]
  },

  "surface_mesh": {
    "input_file": "preprocessed.stl",
    "target_cell_size": 0.01,
    "min_cell_size": 0.0025,
    "feature_angle": 150.0,
    "feature_extract_level": 1
  },

  "boundary_layers": {
    "enabled": false,
    "num_layers": 0,
    "first_layer_thickness": 0.0,
    "growth_ratio": 1.2,
    "max_total_thickness": 0.0,
    "min_thickness_ratio": 0.1,
    "feature_angle": 130.0
  },

  "refinement_regions": [],

  "quality_targets": {
    "max_non_orthogonality": 70.0,
    "max_skewness": 6.0,
    "max_aspect_ratio": 200.0,
    "min_determinant": 0.001,
    "target_y_plus": null
  },

  "tier_specific_params": {},

  "previous_attempt": null
}
```

---

## 재시도 전략 (Evaluator 피드백 반영)

Evaluator가 FAIL을 반환하면, Strategist는 `quality_report.json`을 읽고 전략을 수정한다.

### 수정 규칙

| Evaluator 피드백 | Strategist 대응 |
|-----------------|----------------|
| `max_non_orthogonality > threshold` | snap tolerance 증가, castellated level 상향 |
| `max_skewness > threshold` | 셀 크기 축소, 리파인먼트 추가 |
| `negative_volumes > 0` | BL 파라미터 완화 (층수 감소, 성장비 축소) |
| `BL 미생성 영역` | BL feature angle 완화, min thickness 축소 |
| `checkMesh 완전 실패` | 다음 fallback Tier로 전환 |
| `모든 Tier 실패` | quality_level을 한 단계 낮추고 재시도 (fine→standard→draft) |

### iteration 필드

```json
{
  "iteration": 2,
  "previous_attempt": {
    "tier": "tier1_snappy",
    "quality_level": "fine",
    "failure_reason": "max_non_orthogonality=73.2",
    "evaluator_recommendation": "snap_iterations 증가"
  },
  "modifications": [
    "snappy_snap_iterations: 5 → 8",
    "boundary_layers.feature_angle: 130 → 100"
  ]
}
```

---

## 테스트 시나리오

```bash
# draft (빠른 검증)
auto-tessell strategize --geometry-report geometry_report.json --quality draft

# standard (기본)
auto-tessell strategize --geometry-report geometry_report.json

# fine (최종 CFD)
auto-tessell strategize --geometry-report geometry_report.json --quality fine

# Tier 강제 지정
auto-tessell strategize --geometry-report geometry_report.json --tier snappy

# 재시도 (Evaluator 피드백 반영)
auto-tessell strategize \
  --geometry-report geometry_report.json \
  --quality-report quality_report.json \
  --iteration 2
```
