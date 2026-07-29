# Native HEX-DOM 고도화 계획 (2026-07-22)

## 1. 목표와 불변 조건

목표는 `native_hex_dominant`를 임의 STL에 강한 CFD용 hex-dominant 엔진으로 고도화하는 것이다. 단기 목표는 순수 all-hex가 아니다. **wall 전용 boundary layer + sparse Cartesian/octree core + 좁은 hybrid transition cavity**가 가장 현실적이고 검증 가능한 구조다.

다음 조건은 전 단계의 hard gate다.

- Python public API, `NativeHexResult`, CLI 및 tier fallback 동작을 유지한다.
- 새 C++/pybind 경로 실패 시 기존 native Python 경로로 돌아간다.
- BL은 최종 patch type이 정확히 `wall`인 면에만 생성한다.
- `inlet`, `outlet`, `symmetry`, `symmetryPlane`, `empty`, `patch`에는 BL을 만들지 않는다.
- 명시적 face 선택도 wall 집합과 교집합을 취한다. non-wall 선택은 거부하고 진단에 기록한다.
- patch 이름, type, 원본 surface provenance를 octree/snap/write/BL 전 과정에서 보존한다.
- 음수 체적과 inverted Jacobian은 0이어야 한다.
- wall/non-wall 경계의 BL side face를 물리적 `wall` patch로 노출하지 않는다. transition cavity 내부 면으로 처리한다.
- 사용자 목표 cell 수는 BL cell까지 포함해 계산한다.

## 2. 현재 상태와 확인 결과

### 2.1 검증 기준

2026-07-22 기준 다음 회귀 묶음은 통과한다.

```text
python3 -m pytest \
  tests/test_native_hex.py \
  tests/test_native_hex_snap.py \
  tests/test_native_hex_octree.py \
  tests/test_native_hex_quality_extension.py \
  tests/test_native_bl_helpers.py \
  tests/test_tier_layers_post_bl_phase2.py -q

158 passed in 26.17s
```

기존 cavity 평가 21건은 20건 PASS/PASS_WITH_WARNINGS, 1건 FAIL이다. 그러나 최초 실패 metric 기준으로 max non-orthogonality 초과가 11건(최대 약 86.7도), Hausdorff 초과가 2건이다. 실행 시간은 median 약 44.3초, p95 약 759초, max 약 1203초로 long-tail 비용이 크다.

cube 2,000-cell native pipeline 기록은 약 4.48초에서 1.33초까지 개선됐고, 2,197 cells, 2,744 points, negative volume 0을 기록한다. 단순 cube 성능은 좋지만 곡면/얇은 간극/극단 형상 일반화의 근거는 부족하다.

### 2.2 현재 경로

주요 파일:

- `core/generator/native_hex/mesher.py`: uniform/adaptive orchestration, snap, quality pass, write
- `core/generator/native_hex/octree.py`: adaptive level 선택과 coarse-cell 생성
- `core/generator/native_hex/snap.py`: triangle/segment 후보 snap, smoothing, sliver 완화
- `core/generator/native_hex/quality.py`: volume/quality 계산과 optional native extension
- `core/generator/tier_layers_post.py`: core mesh 이후 BL 실행
- `core/layers/native_bl.py`: 선택 patch extrusion
- `core/generator/polymesh_writer.py`: owner/neighbour/boundary patch 생성
- `core/utils/boundary_provenance.py`: source surface 추적
- `core/utils/boundary_classifier.py`: patch semantic 추론

현재 adaptive 경로는 이름과 달리 true sparse octree가 아니다. 가장 미세한 Cartesian grid를 먼저 dense array로 만들고 각 위치에 level을 기록한다. 따라서 메모리와 분류 비용이 finest-grid 크기에 비례한다.

### 2.3 핵심 결함

1. **Adaptive finalization 불일치**
   - adaptive 경로는 `write_generic_polymesh(...)` 직후 조기 반환한다.
   - uniform 경로의 feature snap, boundary classifier, 최종 volume/quality 검증, quality report 일부를 우회한다.
   - boolean/source patch provenance도 이 경로에서 소실될 수 있다.

2. **Surface band 분류가 근사적임**
   - octree refinement 거리는 point-to-triangle이 아니라 nearest triangle centroid를 사용한다.
   - cell centroid inside 판정만으로 cut/intersecting cell을 구분한다.
   - 얇은 벽, 좁은 간극, 긴 triangle, 높은 곡률에서 refinement 누락 위험이 있다.

3. **실제 transition template 부재**
   - 2:1 level balance는 있으나 `_TEMPLATE_PATTERNS`가 비어 있고 transition template을 쓰지 않는다.
   - coarse face를 sub-quad로 분해한 generic polyhedral cell로 연결한다.
   - 이는 hex-dominant FV mesh로는 가능하지만 all-hex 품질/위상 보장은 아니다.

4. **Snap 후보가 불완전함**
   - native closest-point kernel은 있으나 triangle/segment midpoint KDTree의 소수 후보에 의존한다.
   - 정확한 closest primitive가 후보군 밖이면 surface error가 남는다.
   - adaptive 경로는 uniform 경로의 feature-edge snap을 공유하지 않는다.

5. **BL wall-only 계약이 입력 단계에서 깨짐**
   - `_collect_wall_faces()` 자체는 명시된 non-wall type을 잘 제외한다.
   - 그러나 `PolyMeshWriter`가 생성 patch를 `wall_0`, `wall_1`, ...로 이름 짓고 모두 `wall`로 기록한다.
   - boundary classifier는 `wall_*` 이름을 geometry보다 먼저 wall로 판정한다.
   - `SourceSurfacePatchClassifier`도 source 이름과 무관하게 type을 `wall`로 반환한다.
   - 결과적으로 inlet/outlet 의미가 write 전에 없어진 경우 모든 외곽 면이 wall로 오인될 수 있다.

6. **BL transition topology가 미완성임**
   - 일부 wall patch만 extrusion하면 wall/non-wall 접합부에 `bl_side`가 생길 수 있다.
   - 이를 최종 boundary wall로 남기면 인공 내부벽이 된다.
   - BL shell과 Cartesian core 사이를 닫힌 cavity로 만들고 transition cell로 채워야 한다.

7. **Cell budget이 wall-only BL을 반영하지 않음**
   - 현재 BL 증분 추정은 전체 boundary face를 세는 경로가 있다.
   - wall face 수, layer 수, corner/ridge 공유 topology를 반영한 budget이 필요하다.

8. **품질 최적화가 국소 규칙 모음임**
   - no-inversion/revert guard는 있으나 scaled Jacobian, non-orthogonality, skewness, surface envelope를 함께 다루는 constrained objective가 없다.

## 3. 선행 연구에서 채택할 결정

| 연구 | 핵심 결과 | 이 프로젝트에 적용할 결정 |
|---|---|---|
| Maréchal, octree all-hex (2009) | balanced/pairing octree, boundary-cut primal mesh의 dualization, buffer layer, final projection | sparse leaf 구조, surface buffer band, projection 전 positive-cell topology 확보 |
| Tong et al., HybridOctree_Hex (2024) | curvature/narrow-region refinement, strong balance, templates, boundary cell removal, Jacobian 개선 | curvature+gap metric, strong 2:1 balance, template은 후순위 all-hex 옵션으로 분리 |
| Gao et al., Feature-Preserving Octree Hex (2019) | scaffold를 둔 locally injective mapping, sharp feature 정렬, positive scaled Jacobian | corner/edge/face constraint가 다른 surface optimizer와 envelope gate 도입 |
| Karamete et al., HexDom (2017) | wall BL을 먼저 만들고 2:1 octree core와 사이의 좁은 cavity를 tet로 채움 | 기본 목표 architecture로 채택: BL-first hybrid, native tet transition |
| Aftosmis et al., Cartesian cut-cell | robust triangle/cartesian intersection과 embedded boundary 분류 | centroid inside 대신 triangle-AABB overlap + exact distance + robust inside를 사용 |
| Gao et al., field-guided polyhedral agglomeration (2017) | singular 영역을 irregular polyhedron으로 흡수하는 robust hex-dominant 구성 | 강제 all-hex보다 제한된 poly transition을 허용하고 품질/개수를 명시 |
| Knupp (2003), Xu et al. (2017), Tong et al. (2025) | Jacobian/condition/edge-angle 기반 untangling, line search, constrained boundary motion | barrier + CFD metric 목적함수, positive-volume line search, 국소 bad-region 최적화 |
| Dyedov et al. (2009) | feature-size 제한, collision-safe offset, variational prism 품질 개선 | local feature size로 layer height 제한, wall normal/orthogonality penalty 사용 |
| Maréchal (2016), Reberol et al. (2023) | ridge/corner multi-normal, layer termination과 all-hex BL topology | wall patch 경계/feature ridge를 명시적으로 분류하고 termination topology를 생성 |
| Ye et al. (2025) | bijective mapping, air mesh, positive-volume line search로 full-layer prism 생성 | 복잡 wall에서는 단순 vertex extrusion 대신 bijective shell deformation을 장기 경로로 사용 |
| Roget et al. (2020) | minimum-distance field 기반 prism front와 Cartesian core 결합 | BL outer front를 core mesher의 내부 경계로 사용하고 gap collision을 distance field로 제한 |

결론: **즉시 all-hex template 체계를 완성하는 것보다 HexDom식 BL-first hybrid가 우선**이다. all-hex octree dual/template 경로는 hybrid 경로가 안정화된 뒤 옵션으로 추가한다.

## 4. 목표 architecture

### 4.1 내부 데이터 계약

Public API는 바꾸지 않고 내부에 다음 상태를 둔다.

```text
BoundaryIntent
  patch_id, source_name, final_name, final_type
  source_face_ids, bl_enabled, provenance_confidence

SurfaceMetricField
  target_h, curvature_h, gap_h, feature_class
  closest_primitive, signed_distance/confidence

HexLeaf
  morton_key, level, bounds, state
  state = inside | outside | cut | bl_cavity

HexDominantMeshState
  points, cell_faces, cell_types
  owner/neighbour, boundary_intents
  quality, provenance, stage_timings
```

`final_type`은 이름으로 재추론하지 않는다. 우선순위는 명시적 boundary metadata, source patch metadata, 제한된 geometry 추론 순이다. 확신할 수 없는 patch는 `patch`가 기본값이며 자동 BL 대상이 아니다.

### 4.2 최종 pipeline

1. **Semantic ingest**
   - 입력 face마다 source patch와 final BC type을 확정한다.
   - wall face bitmap을 생성하고 이후 단계에서 immutable provenance로 전달한다.

2. **Wall-only BL shell**
   - wall bitmap에만 layer를 만든다.
   - quad wall은 hex layer, triangular wall은 prism layer를 허용한다.
   - inlet/outlet/symmetry/empty와 만나는 ridge에는 termination topology를 만든다.
   - outer BL front와 side transition front가 하나의 닫힌 core boundary가 되게 한다.

3. **Sparse Cartesian/octree core**
   - Morton-key leaf map을 사용한다.
   - exact triangle-AABB overlap, point-triangle distance, robust inside classification으로 leaf state를 정한다.
   - curvature, narrow gap, BL outer-front size, 사용자 cell budget으로 target size field를 만든다.
   - face-neighbour strong 2:1 balance를 보장한다.

4. **Transition cavity**
   - surface/BL front와 교차하는 octant를 제거한다.
   - 남은 core와 BL shell 사이의 좁은 manifold cavity를 검증한다.
   - 1차는 native tet/pyramid/poly cell로 채운다.
   - transition cell을 별도 통계로 기록한다.

5. **Constrained mapping and optimization**
   - corner는 고정, feature-edge vertex는 curve에 제한, surface vertex는 원 surface/envelope에 제한한다.
   - 목적함수는 min scaled Jacobian barrier, non-orthogonality, skewness, aspect ratio, surface displacement, BL orthogonality를 결합한다.
   - bad-cell region만 확장해 L-BFGS/국소 Newton 계열로 풀고 positive-volume line search를 사용한다.

6. **Common finalization**
   - uniform/adaptive/hybrid가 동일한 provenance, writer, validator, report 경로를 탄다.
   - 실패 시 단계별 fallback과 원인을 report에 남긴다.

### 4.3 Native target 분리

새 기능은 기능별 C++23 pybind target으로 추가한다.

- `native_hex_octree`: exact distance, triangle-AABB overlap, Morton leaves, balance, adjacency
- `native_hex_surface`: corner/edge classification, candidate search, constrained projection
- `native_hex_opt`: Jacobian/CFD objective, gradients, line search, bad-region solve
- 기존 `native_snap`, `native_hex_quality`는 fallback으로 유지한 뒤 parity가 안정된 기능부터 통합한다.

각 target의 호출 순서는 `new pybind -> existing native/Python implementation -> tier fallback`이다. 예외는 삼키지 말고 진단에 경로와 실패 원인을 기록한다.

## 5. 우선순위 roadmap

### P0. 기준선과 semantic boundary 계약

완료 조건:

- 모든 mesh face가 source patch와 final type을 가진다.
- 이름이 `wall_*`이라는 이유만으로 wall이 되지 않는다.
- wall-only BL unit/integration test에서 non-wall extrusion face가 0이다.
- adaptive/uniform이 동일 schema의 quality/provenance/timing report를 낸다.

### P1. Adaptive/common finalization 통합

완료 조건:

- adaptive early return을 제거하고 common finalizer를 사용한다.
- adaptive에서도 feature snap, boundary classification, negative-volume check, quality report가 실행된다.
- boolean source patch type이 write 후 보존된다.
- 현재 158-test 회귀와 cube/cylinder E2E가 유지된다.

### P2. 정확한 surface band와 sparse octree

완료 조건:

- centroid distance를 exact batch point-triangle distance로 대체한다.
- triangle-AABB overlap으로 cut leaf를 빠짐없이 표시한다.
- dense finest-grid allocation을 sparse Morton leaves로 대체한다.
- strong 2:1 balance와 deterministic leaf ordering을 보장한다.
- 얇은 간극/긴 triangle/곡면 corpus에서 surface miss가 0이다.
- p95 runtime과 peak RSS가 현재 adaptive 기준 대비 각각 50% 이상 감소한다.

### P3. BL-first closed-shell hybrid

완료 조건:

- 선택된 wall 면의 BL coverage가 100%이거나 안전 실패로 전체 case가 명시적으로 fallback된다.
- non-wall BL coverage는 항상 0%다.
- BL outer front + side transition front가 watertight 2-manifold다.
- `bl_side`가 최종 physical wall patch로 남지 않는다.
- native tet transition 후 void, overlap, negative cell이 0이다.
- wall-only BL cell 수를 포함한 최종 cell count가 목표의 80~120% 범위다.

### P4. Feature-preserving constrained optimizer

완료 조건:

- corner/edge/face constraint와 projection envelope가 자동 검증된다.
- 모든 cell의 volume과 Jacobian determinant가 양수다.
- min scaled Jacobian, max non-orthogonality, max skewness가 최적화 전보다 악화되지 않는다.
- 극단 형상 실패 시 전체 mesh를 손상시키지 않고 bad region 또는 이전 valid state로 rollback한다.

### P5. All-hex 선택 경로와 생산 최적화

완료 조건:

- strong-balanced octree transition template/dualization을 optional mode로 제공한다.
- hybrid 기본 경로의 robustness를 희생하지 않는다.
- 100+ STL corpus, sanitizer, 반복 determinism, multi-thread benchmark를 통과한다.
- AGPL/GPL 구현 코드를 복사하지 않고 논문 기반 clean-room 구현임을 기록한다.

## 6. 작업자 첫 3개 coding card

### Card 1: `HEXDOM-WALL1` - boundary intent와 strict wall-only BL

범위:

- `boundary_provenance.py`가 source name뿐 아니라 final patch type을 보존하게 한다.
- `SourceSurfacePatchClassifier`의 무조건 `wall` 반환을 제거한다.
- `PolyMeshWriter`가 모든 생성 patch를 `wall_*`/`wall`로 만드는 정책을 제거한다.
- BL 선택은 `final_type == "wall"`과 요청 face의 교집합만 허용한다.
- wall-only face count로 BL cell budget을 다시 계산한다.

테스트:

- 직육면체 duct: 4 wall + inlet + outlet.
- symmetry/empty 혼합 case.
- 이름에 `wall`이 들어가지만 type이 `patch`인 case.
- source 이름이 `inlet`인데 writer를 거친 case.
- 명시적 set에 non-wall face가 포함된 case: 제외 및 진단 확인.

Acceptance:

- non-wall extrusion 0.
- patch name/type/order 보존.
- 기존 public 함수 signature 변화 없음.
- 기존 wall-only test와 native hex smoke 통과.

### Card 2: `HEXDOM-FINAL1` - uniform/adaptive common finalizer

범위:

- `generate_native_hex()`의 write 이전 결과를 `HexDominantMeshState`와 동등한 내부 구조로 정규화한다.
- adaptive 조기 반환을 없앤다.
- provenance assignment, feature snap, quality validation, report, writer를 공통 함수로 실행한다.
- 실패 단계와 fallback 경로를 report에 추가한다.

테스트:

- 동일 cube를 uniform/adaptive로 실행해 report key parity 확인.
- adaptive boolean/source patch 보존.
- adaptive negative-volume rejection.
- adaptive feature-edge snap 호출/효과 확인.

Acceptance:

- adaptive가 uniform과 동일 hard gate를 통과한다.
- 기존 adaptive cell topology 결과는 의도된 patch/report 차이 외에 유지된다.
- E2E median runtime 회귀가 5% 이하다.

### Card 3: `HEXDOM-DIST1` - exact surface-band native kernel

범위:

- C++23 pybind `native_hex_octree` target을 만든다.
- batch point-to-triangle squared distance와 triangle-AABB overlap을 구현한다.
- BVH/KD 후보는 보수적 broad phase로만 쓰고 exact primitive 계산으로 확정한다.
- `octree.py`의 triangle-centroid refinement를 새 kernel로 대체한다.
- extension import/실행 실패 시 현재 Python 경로로 fallback한다.

테스트:

- 매우 긴 triangle의 endpoint 근처 point.
- acute/sliver triangle.
- triangle이 cell을 가로지르지만 centroid/vertex가 cell 밖인 case.
- zero-area triangle과 empty input.
- C++/Python brute-force parity와 deterministic output.

Acceptance:

- 거리 오차는 double precision tolerance 이내.
- 모든 교차 AABB가 cut으로 표시된다.
- synthetic 100k points/triangles에서 Python brute-force보다 명확히 빠르다.
- thin-gap/cylinder surface error가 baseline보다 악화되지 않는다.

## 7. Test plan

### 7.1 Unit/parity

- boundary intent precedence와 strict wall filter
- exact point-triangle, segment, triangle-AABB kernel parity
- sparse leaf insert/split/neighbour/2:1 balance
- cut-cell manifold extraction
- BL wall/non-wall ridge termination
- Jacobian/gradient finite-difference parity
- native import failure와 Python fallback

### 7.2 Integration

- cube: six wall / duct 4-wall+inlet+outlet / symmetry wedge / 2D empty front-back
- cylinder와 NACA: curved wall, sharp trailing edge
- thin gap, close parallel walls, concave corner, narrow channel
- dual torus와 self-near geometry
- multi-source boolean geometry
- wall patch 일부만 BL 활성화한 case

각 case에서 다음을 검사한다.

- patch type/provenance exact match
- non-wall BL face/cell 0
- selected wall coverage
- watertightness, manifoldness, void/overlap
- negative volume/inverted Jacobian 0
- surface Hausdorff, feature-edge displacement
- non-orthogonality, skewness, aspect ratio, min scaled Jacobian
- requested/actual cell ratio
- 두 번 실행한 topology hash 일치

### 7.3 Robustness

- ASan/UBSan native extension run
- malformed/degenerate STL은 crash 없이 명시적 fallback 또는 오류
- extension을 강제 disable한 Python parity run
- 100+ STL corpus의 tier별 반복 회귀

## 8. Benchmark plan

결과는 commit hash와 함께 JSON/CSV에 기록한다. 전체 시간뿐 아니라 다음 stage를 분리한다.

```text
semantic_classification
surface_metric
octree_build_balance
cut_classification
bl_shell
transition_fill
snap_projection
quality_optimization
polymesh_write
validation
```

기록 항목:

- elapsed wall/cpu time, peak RSS, thread count
- leaf/cut/core/transition/BL cell 수
- requested/actual cells와 ratio
- BL coverage by patch type
- negative cells, min volume, min scaled Jacobian
- max/p95 non-orthogonality, skewness, aspect ratio
- Hausdorff/max feature displacement
- fallback path와 원인

Corpus:

- micro: cube, sphere, cylinder, long triangle surface, thin gap
- CFD semantics: duct, elbow, symmetry wedge, airfoil far-field
- topology stress: torus, dual torus, concave cavity, close shells
- application corpus: 기존 cavity 21건과 프로젝트 100+ STL 회귀

Acceptance policy:

- correctness hard gate 실패 시 속도 개선은 keep하지 않는다.
- non-wall BL은 단 한 면도 허용하지 않는다.
- 새 카드의 E2E median이 baseline보다 5% 넘게 느리면 병목 근거 없이는 keep하지 않는다.
- sparse octree milestone은 adaptive p95와 peak RSS 각각 50% 이상 개선을 목표로 한다.
- 품질 최적화는 min metric 개선과 함께 Hausdorff/envelope를 유지해야 한다.
- benchmark warm-up, 5회 반복, median/p95, 고정 thread/CPU 조건을 사용한다.

### 8.1 HEX-E2E-BENCH 결과 (2026-07-22)

범위: `HEXDOM-WALL1`, `HEXDOM-FINAL1`, `HEXDOM-DIST1` 이후 cube/smoke/adaptive 검증.

명령:

```text
python3 -m pytest tests/test_native_hex.py tests/test_native_hex_snap.py tests/test_native_hex_octree.py -q
python3 scripts/benchmark_native_pipeline.py --only hex --cells 2000 --output-dir /tmp/autotessell_hexdom_e2e_bench_v1
python3 -m pytest tests/test_3tier_hbp_smoke.py::test_hex_dominant_cube_smoke -q
python3 scripts/smoke_native_hex.py 2000
python3 -m pytest tests/test_native_hex_solid_volume.py::test_native_hex_curved_wall_fidelity tests/test_native_hex_solid_volume.py::test_native_hex_no_negative_volumes -q
```

결과:

- focused native hex tests: 58 passed.
- 3-tier hex smoke: 1 passed.
- solid smoke: PASS, cells 2197, time 1.4s, surface 6.000, void 0.000, volume 1.000, degenerate 0.
- curved/negative-volume focused tests: 4 passed.
- pipeline benchmark JSON: `/tmp/autotessell_hexdom_e2e_bench_v1/native_pipeline_20260721T215036Z.json`.
- pipeline benchmark CSV: `/tmp/autotessell_hexdom_e2e_bench_v1/native_pipeline_history.csv`.

Pipeline benchmark record:

```json
{
  "case": "hex",
  "verdict": "PASS",
  "tier": "tier_native_hex",
  "elapsed_seconds": 1.400482,
  "cells": 2197,
  "points": 2744,
  "negative_volumes": 0,
  "max_non_orthogonality": 0.0,
  "max_skewness": 3.6082248264235336e-16
}
```

Adaptive spot check with `adaptive=True`, `n_levels=3`, `target_cells=2000`:

- PASS, elapsed 1.284418s, cells 2197, points 2744, negative volumes 0.
- `native_hex_octree_done` reports `surface_distance_mode=point_triangle_kdtree`.
- No quality regression against uniform cube path.

Observed non-blocking issue:

- Generator pipeline logs `native_tier_patch_stats_unavailable error="'type'"` before later boundary classification succeeds.
- Cause is outside this worker scope: common native tier stats parser expects boundary entries with `type`.
- Keep next fix as shared finalization/reporting card, not HEXDOM-DIST regression.

## 9. 주요 risk와 완화

| Risk | 영향 | 완화 |
|---|---|---|
| STL에 BC semantic이 없음 | inlet/outlet이 wall로 오분류 | sidecar/CLI source metadata 우선; 불명확하면 `patch`, 자동 BL 금지 |
| wall/non-wall BL termination | artificial wall, void, bad prism | closed cavity 계약, ridge template, native tet transition |
| BL-first와 cell budget 충돌 | 목표 cell 수 과다 | wall area/local size/layer count를 core budget 전에 반영 |
| sparse octree 전환 parity | topology/ordering 변화 | deterministic Morton order, old adaptive fallback, 단계별 golden test |
| exact geometry 비용 | 성능 저하 | BVH broad phase + batched SIMD/OpenMP exact narrow phase |
| feature projection inversion | negative cells | scaffold/envelope, positive Jacobian barrier, line search/rollback |
| hybrid evaluator 부족 | 품질 오판 | cell type별 volume/Jacobian/CFD metric을 공통 validator에 추가 |
| 라이선스 오염 | 배포 제약 | AlgoHex/AGPL 코드는 reference-only; 논문 기반 clean-room 구현 |

## 10. 접근 가능한 주요 문헌

1. Maréchal, *Advances in Octree-Based All-Hexahedral Mesh Generation: Handling Sharp Features* (2009): https://team.inria.fr/gamma/files/2021/03/imr18.pdf
2. Tong, Halilaj, Zhang, *HybridOctree_Hex* (2024): https://arxiv.org/abs/2401.05984, https://doi.org/10.1016/j.jocs.2024.102278
3. Gao, Shen, Panozzo, *Feature Preserving Octree-Based Hexahedral Meshing* (2019): https://cims.nyu.edu/gcl/papers/2019-OctreeMeshing.pdf
4. Gao et al., *Robust Hex-Dominant Mesh Generation using Field-Guided Polyhedral Agglomeration* (2017): https://rgl.epfl.ch/publications/Gao2017Robust/
5. Baudouin et al., *A Frontal Approach to Hex-Dominant Mesh Generation* (2014): https://link.springer.com/article/10.1186/2213-7467-1-8
6. Aftosmis et al., Cartesian mesh generation/cut-cell report: https://ntrs.nasa.gov/api/citations/20020076392/downloads/20020076392.pdf
7. Berger et al., *Progress Towards a Cartesian Cut-Cell Method for Viscous Compressible Flow* (2011): https://ntrs.nasa.gov/api/citations/20110010909/downloads/20110010909.pdf
8. Knupp, *A Method for Hexahedral Mesh Shape Optimization* (2003): https://doi.org/10.1002/nme.768
9. Xu, Gao, Chen, *Hexahedral Mesh Quality Improvement via Edge-Angle Optimization* (2017): https://gaoxifeng.github.io/papers/2017/AngleBased_HexOpt.pdf
10. Tong, Zhang, *HexOpt* (2025): https://arxiv.org/abs/2410.11656
11. Dyedov et al., *Variational Generation of Prismatic Boundary-Layer Meshes* (2009): http://europepmc.org/articles/pmc2745959
12. Garimella, Shephard, *Boundary Layer Meshing for Viscous Flows in Complex Domains* (2000): https://oss.jishulink.com/caenet/forums/upload/2006/8/9/7890f921-cf99-426b-b5a0-c99b537847e3.pdf
13. Maréchal, *All Hexahedral Boundary Layers Generation* (2016): https://team.inria.fr/gamma/files/2021/03/imr25.pdf
14. Reberol et al., *Robust Topological Construction of All-Hexahedral Boundary Layer Meshes* (2023): https://www.algohex.eu/publications/robust-boundary-layer/reberol-robust-hex-boundary-layer.pdf
15. Roget et al., *Prismatic Mesh Generation Using Minimum Distance Fields*: https://iccfd.org/iccfd10/papers/ICCFD10-219-Paper.pdf
16. Pietroni et al., *Hex-Mesh Generation and Processing: A Survey* (2022): https://arxiv.org/abs/2202.12670
17. Ye et al., *Robust Full-Layer Prismatic Mesh Generation Based on Bijective Mapping* (2025), 프로젝트 보관본: `docs/references/mesh-quality/robust-full-layer-prismatic-mesh-generation-2025.pdf`, DOI: https://doi.org/10.1016/j.jcp.2025.113744
18. Dyedov et al. 프로젝트 보관본: `docs/references/mesh-quality/variational-prismatic-boundary-layer-meshes-2009.pdf`

## 11. 원문 접근이 막힌 유료 문헌

다음 원문은 조사 시 공식 full text 접근이 막혔다. 구현 전에 확보 가치가 높은 순서다.

1. Karamete et al., *Yet Another Hexahedral Dominant Meshing Algorithm: HexDom* (2017): https://www.sciencedirect.com/science/article/abs/pii/S0168874X17302378
2. Ray et al., *Hex-Dominant Meshing: Mind the Gap!* (2018): https://www.sciencedirect.com/science/article/pii/S0010448518302215
3. Qian, Zhang, *Sharp Feature Preservation in Octree-Based Hexahedral Mesh Generation for CAD Assembly Models* (2010): https://doi.org/10.1007/978-3-642-15414-0_15

## 12. 완료 정의

`native_hex_dominant` 고도화 완료는 다음을 모두 만족할 때다.

- 100+ STL corpus에서 crash/hang 0, hard-gate pass 또는 명시적 fallback 100%.
- wall-only BL: wall coverage 목표 충족, non-wall extrusion 0.
- surface/feature envelope, watertightness, manifoldness, positive cell 보장.
- target cell 수 80~120%를 일반 case에서 충족하고 예외 원인을 보고.
- cube뿐 아니라 curved/thin/concave/boolean 형상에서 품질 gate 통과.
- p95 runtime과 peak RSS가 현재 adaptive 기준보다 실질적으로 개선.
- native extension disable 상태에서도 기존 Python fallback과 public API가 동작.
- stage별 benchmark, provenance, fallback reason이 commit hash와 함께 재현 가능.
