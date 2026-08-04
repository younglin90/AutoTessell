# Agent: Strategist (전략 에이전트)

## 핵심 철학

**외부 라이브러리에 의존하지 않고 우리 코드로 직접 구현**한다.
Strategist 는 본래 순수 파이썬 로직 중심이라 외부 의존이 거의 없음.
Reynolds 수 추정, cell-size 공식, domain aspect ratio 등은 논문·교과서 참고해 `core/strategist/` 에
모두 우리 코드로 구현한다.

---

## 역할

Analyzer + Preprocessor 출력과 CLI 파라미터를 종합해 **메쉬 생성 전략** 을 수립한다.

- **메쉬 타입 선택 (사용자 우선)** : `tet` / `hex_dominant` / `poly`
- **QualityLevel 선택 (사용자 우선)** : `draft` / `standard` / `fine`
- (타입 × 품질) 조합 → 기본 Tier 매핑
- 도메인 박스 계산, BL 파라미터, cell size, refinement 레벨 결정

> **중요 변경** : Generator ⇄ Evaluator 자동 재시도 루프는 **제거**.
> Evaluator 가 FAIL 을 반환해도 Strategist 는 자동 재시도하지 않음.
> Evaluator 의 recommendation 을 **사용자에게 보여주고, 재시도 여부는 사용자가 판단**.

---

## 입력 / 출력

- 입력:
  - `geometry_report.json` (Analyzer)
  - `preprocessed_report.json` (Preprocessor, `surface_quality_level` 포함)
  - CLI 파라미터 (`--quality`, `--tier`, `--mesh-type`)
  - (재실행 시) 이전 `quality_report.json` — 사용자가 수동으로 Strategist 재호출한 경우만
- 출력: `mesh_strategy.json`

---

## 1. 메쉬 타입 선택

사용자가 `--mesh-type {tet|hex_dominant|poly}` 로 선택. 기본값은 `hex_dominant` (CFD 관점 경계층 품질 우수).

| 메쉬 타입 | 특징 | 대표 Tier |
|-----------|------|----------|
| **tet** | 복잡 형상 강건, isotropic | tetwild, wildmesh (Draft), netgen (Standard) |
| **hex_dominant** | 경계층 품질 우수, 셀 수 효율 | cfmesh (Draft/Standard), snappy (Fine) |
| **poly** | 셀 수 최소, 대 gradient 잘 해소 | voro_poly (Draft), polydual (Standard/Fine) |

---

## 2. QualityLevel

```python
class QualityLevel(str, Enum):
    DRAFT    = "draft"     # 빠른 검증, 30초 내
    STANDARD = "standard"  # 엔지니어링, 수 분
    FINE     = "fine"      # 최종 CFD, 30분+
```

기본값: `standard`. CLI: `--quality draft|standard|fine`.

---

## 3. 메쉬 타입 × QualityLevel → Tier 매핑

| 메쉬 타입 | draft | standard | fine |
|-----------|-------|----------|------|
| **tet** | tetwild (coarse ε) | netgen 또는 wildmesh | wildmesh (tight ε) 또는 tetwild + mmg3d |
| **hex_dominant** | cfmesh (fast) | cfmesh | snappyHexMesh (BL 포함) |
| **poly** | voro_poly | polydual (polyDualMesh) | polydual + 품질 개선 |

사용자가 `--tier` 명시하면 **strict_tier** 모드로 Strategist 가 재매핑하지 않음.

---

## 4. 도메인 설정

### External flow (풍동)

비대칭 도메인 (x 방향 길게):
- 업스트림 (x−): 3L (draft), 5L (standard), 10L (fine)
- 다운스트림 (x+): 5L (draft), 10L (standard), 20L (fine)
- 측면 (y±, z±): 2L (draft), 3L (standard), 5L (fine)

L = characteristic_length (geometry_report).

사용자 override:
```
--domain-upstream FLOAT
--domain-downstream FLOAT
--domain-lateral FLOAT
--domain-scale FLOAT
```

### Internal flow

bbox 기반 대칭 도메인 [−0.6, 0.6]³ 혹은 geometry bbox 그대로.

---

## 5. 셀 크기 결정

```python
cell_size_factor = {"draft": 4.0, "standard": 2.0, "fine": 1.0}[quality_level]
base_cell_size    = (characteristic_length / 50) * cell_size_factor
surface_cell_size = base_cell_size / 4
min_cell_size     = surface_cell_size / 4

# 곡률 기반 보정 (fine 만)
if quality_level == "fine" and curvature_max > 20:
    surface_cell_size *= 0.5
```

CLI override:
```
--element-size, --base-cell-size, --min-cell-size, --base-cell-num
```

---

## 6. Boundary Layer 파라미터

| QualityLevel | BL 활성화 | nLayers | growth | first_thickness |
|--------------|-----------|---------|--------|------------------|
| draft | 비활성 | 0 | - | - |
| standard | 옵션 (`--bl-layers N`) | 3 | 1.2 | y+ 없이 bbox/200 |
| fine | 자동 활성 | 5 | 1.2 | y+=1 기반 Re 추정 |

y+=1 first layer 계산 (fine):
```python
Re = estimate_reynolds(L, velocity_guess)
y_first = L * target_y_plus * (Re ** -0.9) * 6.0
```

메쉬 타입별 BL 적용 전략:
- **tet**: BL 부분도 tet (prism 혼합 없이 모두 tet) — shrink+extrude+subdivide 로 tet prism 층
- **hex_dominant**: 전통적 prism 층 (shrink+extrude+snap+merge+stitch)
- **poly**: prism 층 + polyhedral 전환 혹은 anisotropic poly 셀

---

## 7. 품질 목표

| 지표 | draft | standard | fine |
|------|-------|----------|------|
| max_non_orthogonality | 85° | 70° | 65° |
| max_skewness | 8.0 | 6.0 | 4.0 |
| max_aspect_ratio | 500 | 200 | 100 |
| min_determinant | 0.0001 | 0.001 | 0.001 |
| target_y_plus | - | - | 1.0 |

---

## mesh_strategy.json 스키마

```json
{
  "strategy_version": 3,
  "quality_level": "standard",
  "mesh_type": "hex_dominant",
  "surface_quality_level": "l1_repair",
  "selected_tier": "cfmesh",
  "fallback_tiers": ["snappy"],
  "strict_tier": false,

  "flow_type": "external",
  "domain": {
    "type": "box",
    "min": [-5.0, -3.0, -3.0],
    "max": [10.0, 3.0, 3.0],
    "base_cell_size": 0.04,
    "location_in_mesh": [-4.5, 0.0, 0.0]
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

  "tier_specific_params": {}
}
```

---

## 재시도 정책 (변경 사항)

- **자동 재시도 루프 제거**.
- Generator 실패 시: fallback Tier 로 자동 전환 (동일 메쉬 타입 내 순서대로).
- Evaluator FAIL 시: **사용자에게 recommendation 출력 + 재실행 여부 확인** (`y/N`).
  - 사용자가 `y` 선택 → Strategist 재호출 (이전 quality_report 참조해 파라미터 조정 제안)
  - `N` 선택 → 현재 mesh 유지, 파이프라인 종료

---

## 재호출 시 파라미터 조정 제안 (사용자 요청 시)

Evaluator 의 실패 지표별 제안:

| 실패 지표 | Strategist 제안 |
|----------|----------------|
| non_orthogonality 초과 | snap_iterations/snap_tolerance↑, feature_level↑ |
| skewness 초과 | cell size↓, refinement level↑ |
| negative_volumes | BL 층수↓, growth_ratio↓ |
| BL 미생성 영역 | feature_angle 완화, min_thickness↓ |
| checkMesh 완전 실패 | 동일 메쉬 타입 내 다른 Tier, 또는 QualityLevel 한 단계 낮춤 |

---

## 테스트 시나리오

```bash
auto-tessell strategize --geometry-report geometry_report.json --quality draft --mesh-type tet
auto-tessell strategize --geometry-report geometry_report.json --mesh-type hex_dominant
auto-tessell strategize --geometry-report geometry_report.json --quality fine --mesh-type hex_dominant
auto-tessell strategize --geometry-report geometry_report.json --tier wildmesh    # strict_tier
```
