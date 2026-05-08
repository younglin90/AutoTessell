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

## 4-A. tet + BL CFD PASS 기준 (장기 명세)

다양하고 복잡한 face mesh 를 입력으로 받아 `tet + BL` 을 생성할 때, CFD/FVM 에
사용 가능한 volume mesh 인지는 아래 gate 를 모두 통과해야 한다. 이 절은
WildMesh 기반 tet volume + native/SMESH-style BL 를 장기 목표로 하는 평가 기준이다.

최종 판정은 `SurfaceGate`, `VolumeTopologyGate`, `FVMQualityGate`,
`BoundaryLayerGate`, `GeometryFidelityGate`, `BudgetSolverGate` 를 모두 PASS 해야 한다.
Hard fail 항목은 평균값과 무관하게 count 가 0 이어야 한다.

### Gate 0: 입력 surface mesh

Volume mesh 전에 입력 표면 자체가 아래 조건을 만족해야 한다. 실패 시 Generator 가
성공해도 BL collision, feature drift, patch 누락이 반복되므로 `quality_report.json`
에 surface defect count 를 그대로 남긴다.

| 항목 | PASS 기준 |
|------|----------|
| Open edges | 0 |
| Non-manifold edges | 0 |
| Non-manifold vertices | 0 |
| Self-intersections | 0 권장. 존재하면 repair 필요, 최소한 count/report 필수 |
| Duplicate vertices / faces | 0 |
| Degenerate triangles | 0 |
| Flipped / inconsistent winding faces | 0 |
| Connected components | 기대 component 수와 동일 |
| Holes / boundary loops | closed body 기준 0 |
| Patch labels | wall / inlet / outlet / farfield / symmetry 누락 없음 |
| Sharp feature graph | feature edge 추출 가능, 주요 rim/throat/branch edge 누락 없음 |

### Gate 1: volume topology hard fail

아래 항목은 하나라도 발생하면 CFD용 mesh 로 PASS 불가다.

| 항목 | PASS 기준 |
|------|----------|
| Negative volume cells | 0 |
| Zero / near-zero volume cells | 0, `minVol > bbox_diag^3 * 1e-15` 권장 |
| Zero / near-zero face area | 0, `minArea > bbox_diag^2 * 1e-14` 권장 |
| Negative Jacobian / determinant | 0, `minDeterminant >= 0.001` |
| Invalid owner/neighbour | 0 |
| Face shared by >2 cells | 0 |
| Disconnected fluid islands | 0, multi-region 의도 시 명시 예외 |
| Boundary face normal flipped | 0 |
| Patch startFace / nFaces inconsistency | 0 |
| BL prism collapse | 0 |
| Blocked gap / clearance collapse | 0 |
| Cell centroid outside cell | 가능하면 0. 심한 poly/tet defect 는 hard fail 후보 |

### Gate 2: FVM 수치 품질

기본값은 OpenFOAM 계열 표준 설정에 맞춘다. 단일 max 값뿐 아니라 `mean`, `p95`,
`p99`, `fail_count`, `worst_cell_id`, `worst_face_id`, `patch별 breakdown` 을 같이
저장한다.

| Metric | Default PASS | Target |
|--------|--------------|--------|
| Max non-orthogonality | `<= 65 deg` | p99 `<= 55`, p95 `<= 45` |
| Max internal skewness | `<= 4` | p99 `<= 2.5` |
| Max boundary skewness | `<= 20` | p99 `<= 8` |
| Max concavity | `<= 80 deg` | `<= 60 deg` |
| Min face weight | `>= 0.05` | `>= 0.1` |
| Min volume ratio | `>= 0.01` | `>= 0.05` |
| Face interpolation weight | `[0.05, 0.95]` | `[0.1, 0.9]` |
| Face warpage / twist | OpenFOAM flatness pass | max twist `<= 15 deg` |
| Adjacent cell volume ratio | `>= 0.01` | `>= 0.1` |

tet bulk 전용 지표:

| tet bulk metric | PASS 기준 |
|-----------------|----------|
| Radius ratio / tet quality | near-zero sliver 없음 |
| Min dihedral | hard `> 1 deg`, target `> 5 deg` |
| Max tet aspect ratio | hard `< 1000`, target `< 100` |
| p99 tet aspect ratio | target `< 50` |
| Tet orientation | all positive |

### Gate 3: Boundary Layer 전용

tet+BL 의 BL prism/wedge 품질은 bulk tet 품질과 별도로 평가한다. 사용자가 layer 수를
명시한 경우, exact mode 에서는 layer count 감소도 FAIL 로 본다.

| 항목 | PASS 기준 |
|------|----------|
| BL 적용 patch | `body_wall` 또는 명시 wall patch 만 |
| farfield / inlet / outlet / symmetry BL | 0 face |
| Requested layer count | 예: 3 입력 시 selected wall face 전부 3 layer |
| Accepted layer coverage | exact mode 기준 100% |
| First layer height | 입력값 또는 y+ 계산값 대비 오차 `<= 5-10%` |
| Growth ratio | `r_i ~= user_growth_ratio`, 일반 권장 `1.1-1.3` |
| Total thickness | `h1 * (r^N - 1) / (r - 1)` 와 일치 |
| Prism positive volume | 100% |
| Prism determinant | `>= 0.001` |
| Wall-normal alignment | target `<= 30-45 deg` |
| Prism aspect ratio | BL high AR 허용, hard `< 1000`, target p99 `< 300` |
| Side face warpage | max twist `<= 15 deg` |
| BL self collision | 0 |
| BL side stitching gaps | 0 |
| BL-to-bulk transition minVolRatio | `>= 0.01`, target `>= 0.05` |
| Layer Count Reduction | exact mode 에서는 금지. adaptive mode 에서는 감소 vertex/face report 필수 |

### Gate 4: 원본 surface fidelity

입력 표면 `S0` 와 volume mesh 외부 boundary surface `Sh` 를 비교한다. external flow 는
`farfield` 를 제외하고 `body_wall` 만 비교한다.

| 항목 | Default PASS | Strict target |
|------|--------------|---------------|
| Symmetric Hausdorff max relative | `<= 1% bbox` | `<= 0.3%` |
| d95 relative | `<= 0.5% bbox` | `<= 0.1-0.2%` |
| RMS distance relative | `<= 0.2% bbox` | `<= 0.05-0.1%` |
| Signed distance bias | shrink/expand 한쪽 편향 작아야 함 | mean near 0 |
| Normal deviation p95 | `<= 15 deg` | `<= 8 deg` |
| Flipped boundary normals | 0 | 0 |
| Surface area error | `<= 2%` | `<= 0.5-1%` |
| Enclosed volume error | `<= 1%` | `<= 0.3-0.5%` |
| Centroid shift | `<= 0.5% bbox` | `<= 0.1% bbox` |
| Feature edge drift | local edge length 의 `<= 0.5` 또는 bbox `<= 0.2%` | 더 엄격 |

복잡 형상에서는 다음 feature-specific metric 을 추가로 저장한다.

- throat / minimum gap 보존
- inlet/outlet rim 보존
- branch ostium / branch graph 보존
- curvature peak 보존
- section area `A(s)` 보존
- hydraulic diameter `D_h(s)` 보존
- wall distance field 변화

### Gate 5: budget / solver compatibility

| 항목 | PASS 기준 |
|------|----------|
| Final cell count | `<= max_cells` hard, target mode 는 `0.8-1.2 * target_cells` |
| BL layer count | exact mode 에서 사용자 입력과 정확히 동일 |
| Memory estimate | 설정 cap 이하 |
| OpenFOAM polyMesh format | points/faces/owner/neighbour/boundary 파싱 OK |
| Patch types | wall/patch/symmetry 등 solver dictionary 와 일치 |
| Orphan cells / faces | 0 |
| Cell zones / face zones | 필요한 경우 누락 없음 |

### 최종 tet+BL PASS 판정

```python
def evaluate_tet_bl_cfd(surface, topology, fvm, bl, fidelity, budget):
    if not surface.pass_:
        return FAIL
    if topology.hard_fail_count != 0:
        return FAIL
    if not fvm.pass_:
        return FAIL
    if not bl.pass_:
        return FAIL
    if not fidelity.pass_:
        return FAIL
    if not budget.pass_:
        return FAIL
    return PASS
```

`quality_report.json` 은 각 gate 별 `pass`, `hard_fail_count`, `soft_fail_count`,
`worst_entities`, `patch_breakdown`, `recommendations` 를 포함해야 한다.

## 4-B. 초기 face mesh / CAD 형상 보존 PASS 기준 (장기 명세)

이 절은 입력 face mesh 또는 CAD 형상이 volume mesh 결과에서 유지되었는지 판정하는
전용 기준이다. 일반 mesh quality 가 PASS 여도 형상이 shrink, bulge, rim 누락,
patch label 누락, feature edge drift 를 일으키면 CFD setup 은 실패로 본다.

### 비교 대상 정의

- `S0`: 입력 기준 형상.
  - STL/OBJ/PLY/OFF 입력: 입력 triangle surface 자체.
  - CAD 입력: CAD 원본을 evaluator 용 고정 tolerance 로 tessellate 한 reference
    surface. CAD kernel projection 이 가능하면 tessellated `S0` 뿐 아니라 CAD
    surface distance 도 함께 계산한다.
- `Sh`: volume mesh 의 외부 boundary face 만 추출한 surface.
  - tet+BL 에서는 outermost physical wall faces 를 사용한다.
  - external flow 는 `farfield`, `symmetry`, `domain_*`, `bl_internal_domain` 을 제외하고
    `body_wall` 및 물리 inlet/outlet/wall patch 만 비교한다.
  - internal flow 는 wall/inlet/outlet 등 물리 patch 를 모두 비교하되 patch별로 따로
    breakdown 한다.
- 기준 길이:
  - `L = bbox_diag(S0)`.
  - `h0 = median_edge_length(S0)`.
  - `tau_ref = max(cad_tolerance, stl_declared_tolerance, 1e-6 * L)`.
  - coarse STL 에서는 `tau_mesh = max(tau_ref, 0.25 * h0)` 를 보조 허용치로 보고,
    상대 오차 기준과 함께 기록한다. 단 critical feature 는 coarse 예외를 적용하지 않는다.

### Gate G0: 비교 surface 추출 hard fail

| 항목 | PASS 기준 |
|------|----------|
| `Sh` 추출 가능 | true |
| 비교 대상 patch 존재 | 모든 physical patch 존재 |
| excluded patch 혼입 | farfield/domain/internal BL patch 가 body 비교에 들어가지 않음 |
| boundary face normal orientation | flipped physical boundary face 0 |
| physical patch empty | 0 |
| orphan boundary face | 0 |

### Gate G1: geometry distance

거리 평가는 양방향으로 계산한다.

- `d_0_to_h`: `S0` sample point 에서 `Sh` 까지 거리.
- `d_h_to_0`: `Sh` sample point 에서 `S0` 또는 CAD surface 까지 거리.
- `d_sym = max(d_0_to_h, d_h_to_0)` 기반 Hausdorff, d95/d99/RMS.
- signed distance 는 shrink/expansion bias 확인용으로 별도 기록한다.

| Metric | Default PASS | Strict target | Hard FAIL |
|--------|--------------|---------------|-----------|
| Symmetric Hausdorff max | `<= max(0.01 * L, tau_mesh)` | `<= max(0.003 * L, tau_ref)` | `> max(0.02 * L, 2*tau_mesh)` |
| d99 relative | `<= max(0.005 * L, tau_mesh)` | `<= max(0.0015 * L, tau_ref)` | `> max(0.01 * L, 2*tau_mesh)` |
| d95 relative | `<= max(0.003 * L, tau_mesh)` | `<= max(0.001 * L, tau_ref)` | `> max(0.008 * L, 2*tau_mesh)` |
| RMS distance | `<= max(0.0015 * L, tau_ref)` | `<= max(0.0005 * L, tau_ref)` | `> max(0.005 * L, tau_mesh)` |
| Signed mean bias | `abs(mean) <= 0.001 * L` | `<= 0.0003 * L` | one-sided shrink/expand `> 0.005 * L` |
| Local outlier clusters | no connected cluster above d99 threshold | none | critical patch cluster present |

판정 규칙:

- d95/d99 는 area-weighted sampling 으로 계산한다.
- `d_0_to_h` 가 크면 원본 feature 누락 또는 hole 가능성.
- `d_h_to_0` 가 크면 volume boundary bulge / farfield 혼입 / wrong patch 가능성.
- signed mean 이 음수/양수로 크게 치우치면 global shrink/expansion 으로 보고 soft fail 이상.

### Gate G2: surface normal / orientation 보존

| 항목 | Default PASS | Strict target | Hard FAIL |
|------|--------------|---------------|-----------|
| Flipped physical boundary normals | 0 | 0 | > 0 |
| Normal deviation p95 | `<= 15 deg` | `<= 8 deg` | `> 30 deg` |
| Normal deviation p99 | `<= 25 deg` | `<= 15 deg` | `> 45 deg` |
| Patch average normal deviation | `<= 10 deg` | `<= 5 deg` | critical patch `> 20 deg` |
| Wall normal direction consistency | outward/inward convention consistent | same | inconsistent |

CAD 입력에서는 CAD analytic normal 을 우선 사용하고, 없으면 `S0` face/vertex normal 을
사용한다.

### Gate G3: feature edge / critical curve 보존

sharp edge, inlet/outlet rim, throat, branch ostium, CAD seam, patch intersection curve 는
거리 metric 만으로는 놓치기 쉬우므로 graph 기준으로 별도 평가한다.

| 항목 | PASS 기준 |
|------|----------|
| Critical feature edge missing count | 0 |
| Feature edge coverage / recall | `>= 0.99` target, default `>= 0.97` |
| Feature edge precision | `>= 0.97` |
| Feature edge distance p95 | `<= max(0.002 * L, tau_mesh)` |
| Feature edge max distance | `<= max(0.005 * L, tau_mesh)` |
| Rim loop count | 입력과 동일 |
| Rim loop closure | closed loop 유지, open break 0 |
| Minimum gap / throat location drift | `<= 0.005 * L` 또는 local diameter 의 `<= 2%` |
| Patch intersection graph | node/edge 수와 adjacency 동일 |

critical feature 예:

- inlet/outlet rim
- 날개 trailing/leading edge
- pipe branch ostium
- valve throat / minimum clearance
- CAD patch seam
- wall/farfield 또는 wall/symmetry 접합선

### Gate G4: integral geometry 보존

거리 outlier 가 작아도 전체 면적/체적이 달라지면 CFD boundary condition 과 유량이
달라진다.

| 항목 | Default PASS | Strict target |
|------|--------------|---------------|
| Surface area error total | `<= 2%` | `<= 0.5-1%` |
| Surface area error per physical patch | `<= 3%` | `<= 1%` |
| Enclosed volume error | `<= 1%` | `<= 0.3-0.5%` |
| Centroid shift | `<= 0.005 * L` | `<= 0.001 * L` |
| Principal inertia axis angle change | `<= 5 deg` | `<= 2 deg` |
| Bounding box expansion/shrink | each axis `<= 1%` | `<= 0.3%` |

open surface 또는 external flow 의 body surface 처럼 enclosed volume 이 정의되지 않는
경우에는 volume error 대신 patch area, centroid, feature graph 를 hard 기준으로 사용한다.

### Gate G5: topology / patch consistency

| 항목 | PASS 기준 |
|------|----------|
| Connected components | `S0` 와 `Sh` 동일. 의도된 multi-body 는 명시 metadata 필요 |
| Euler characteristic / genus | closed body 기준 동일 |
| Boundary loops | open patch 의 loop count 동일 |
| Holes introduced | 0 |
| Self-intersections in `Sh` | 0 |
| Non-manifold edge/vertex in `Sh` | 0 |
| Duplicate / degenerate boundary faces | 0 |
| Patch labels | 입력 physical patch 모두 보존 |
| Patch adjacency graph | 동일 |
| Patch area near-zero collapse | 0 |

patch label 보존은 CFD 관점에서 hard fail 이다. 예를 들어 inlet 이 wall 로 바뀌거나
farfield 가 body fidelity 비교에 섞이면 geometry fidelity gate 는 FAIL 처리한다.

### Gate G6: CFD-specific section / clearance 보존

관, 혈관, 덕트, 터보기계, 노즐처럼 단면이 물리량을 지배하는 형상은 optional 이 아니라
도메인별 hard gate 로 승격한다.

| 항목 | Default PASS |
|------|--------------|
| Cross-section area `A(s)` error | p95 `<= 2%`, max `<= 5%` |
| Hydraulic diameter `D_h(s)` error | p95 `<= 2%`, max `<= 5%` |
| Minimum diameter / throat area error | `<= 2%` |
| Branch area ratio error | `<= 2%` |
| Clearance / minimum gap sign | gap closure 0 |
| Wall distance field RMS change | `<= 1% * L_local` |

### 최종 형상 보존 PASS 판정

```python
def evaluate_shape_preservation(S0, Sh, cad_ref, patches, features):
    if extraction_hard_fail:
        return FAIL
    if geometry_distance.hard_fail:
        return FAIL
    if normals.flipped_count > 0 or normals.hard_fail:
        return FAIL
    if features.critical_missing_count > 0:
        return FAIL
    if topology.self_intersections > 0 or topology.nonmanifold_count > 0:
        return FAIL
    if patch_consistency.hard_fail:
        return FAIL
    if cfd_sections.enabled and cfd_sections.hard_fail:
        return FAIL
    if count_soft_fails(distance, normals, integral, features) >= 2:
        return FAIL
    return PASS
```

`quality_report.json` 의 `geometry_fidelity` 는 다음 필드를 포함해야 한다.

```json
{
  "geometry_fidelity": {
    "compared_patches": ["body_wall", "inlet", "outlet"],
    "excluded_patches": ["farfield", "bl_internal_domain"],
    "distance": {
      "d_0_to_h": {"rms": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0},
      "d_h_to_0": {"rms": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0},
      "hausdorff_symmetric": 0.0,
      "signed_mean": 0.0
    },
    "normals": {"p95_deg": 0.0, "p99_deg": 0.0, "flipped": 0},
    "features": {
      "critical_missing": 0,
      "coverage": 1.0,
      "distance_p95": 0.0
    },
    "integral": {
      "area_error_pct": 0.0,
      "volume_error_pct": 0.0,
      "centroid_shift_rel": 0.0
    },
    "topology": {
      "components_match": true,
      "genus_match": true,
      "self_intersections": 0,
      "nonmanifold_edges": 0
    },
    "patch_consistency": {
      "missing_patches": [],
      "wrong_type_patches": [],
      "adjacency_graph_match": true
    },
    "verdict": "PASS"
  }
}
```

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
