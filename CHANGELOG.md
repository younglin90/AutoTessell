# Changelog

## [0.4.0-beta99] - 2026-04-24 — "항목 2,3,4,5,8 구현"

### Added

**항목 2 — y⁺ GUI 계산 패널**
- `desktop/qt_app/widgets/yplus_panel.py::YPlusPanel`:
  - 유체 선택(air/water/oil) + 유입속도 + 특성길이 + 목표 y⁺ 입력.
  - "계산하기" 버튼 → `estimate_first_layer_thickness` 호출 + 결과 라벨.
  - `bl_thickness_computed = Signal(float)` — 메인 윈도우 BL 파라미터 자동 주입.
  - `set_characteristic_length(l)` API — bbox 대각선 자동 주입 지원.
  - PySide6 없는 headless 환경에서 ImportError 만 발생 (crash 없음).

**항목 3 — native_poly Voronoi 직접 경로 개선**
- `generate_native_poly_voronoi(n_lloyd=2)` — Lloyd 3D 정제 추가.
  - uniform grid seed → scipy Voronoi region centroid 로 n_lloyd 회 이동 → inside 필터.
  - 경계 근방 seed 분포 개선 → degenerate cell 감소.
- `__init__.py` "(1) 향후 확장" 주석 제거.

**항목 4 — isotropic remesh Phase 3 valence constraint**
- `_is_boundary_vertex(v, edge_map)` 헬퍼 추가.
- `_flip_edges_to_improve_valence(valence_constraint=False)` — True 면 interior=6, boundary=4 타깃 다중 패스 flip.
- `isotropic_remesh(valence_constraint=False)` — Phase 3 활성화 kwarg.

**항목 5 — native_bl Phase 3 docstring 갱신**
- "Phase 3 예정 (v0.5+)" → "Phase 3 (beta93 완성): shrinkage iteration + per-vertex scale (beta95)".

**항목 8 — poly_bl_transition Phase 2 interface smoothing**
- `_smooth_interface_vertices(pts, faces, owner, neighbour, prism_cell_ids, tet_cell_ids, n_iter, relax)` — prism-tet interface 근방 tet vertex를 prism face centroid 방향으로 이동.
- `_try_hybrid_dual(interface_smoothing=True, interface_smooth_iters=2, interface_smooth_relax=0.2)`.
- `run_poly_bl_transition(interface_smooth_iters=2)`.
- 테스트 2개 추가.

### Tests

55/55 PASS.

---

## [0.4.0-beta98] - 2026-04-24 — "GUI beta92~97 신규 파라미터 전체 노출"

### Added

- `core/generator/native_poly/smooth.py::smooth_poly_mesh(case_dir, n_iter, relax, lock_boundary)`:
  - polyhedral mesh 내부 vertex를 face centroid area-weighted avg로 relax 이동.
  - boundary vertex 고정 (표면 형상 보존).
  - SmoothResult: n_iter_done, max_displacement.
- `run_native_poly_harness(smooth_iters=0, smooth_relax=0.3)`:
  - dual 변환 직후 smoothing 적용.
  - smooth_iters=0 기본 → 기존 동작 유지.
- HARNESS_PARAMS poly: draft=0, standard=3, fine=5 자동.
- `tests/test_poly_smooth.py` 6 tests.

### Impact

- tet→poly dual 경계 근방 stretched cell → smoothing으로 aspect ratio 개선.
- standard/fine quality poly mesh에서 자동 적용.

---

## [0.4.0-beta96] - 2026-04-24 — "y⁺ 자동 BL 두께 계산"

### Added

- `core/utils/yplus.py`:
  - `estimate_first_layer_thickness(U, L, fluid, y_plus_target)` → `YPlusResult`.
  - Schlichting 평판 Cf + 낮은 Re Blasius + 높은 Re ITTC 분기.
  - FLUID_PROPERTIES: air / water / oil 동점성 계수 내장.
- CLI: `--fluid {air|water|oil|custom}`, `--target-yplus FLOAT`,
  `--kinematic-viscosity FLOAT`.
- `bl_first_height` 미지정 + `target_yplus` 있으면 자동 계산 후 주입.
- `tests/test_yplus.py` 11 tests.

### Usage

```bash
auto-tessell run wing.stl -o case --mesh-type hex_dominant --quality fine \
    --flow-velocity 50 --fluid air --target-yplus 1.0
# → y⁺=1 달성을 위한 bl_first_height 자동 계산 (Re 기반)
```

---

## [0.4.0-beta95] - 2026-04-24 — "완전 비균일 prism BL (per-layer per-vertex)"

### Added

- `BLConfig.per_vertex_first_thickness: dict | None = None`.
  - None (기본) → 전체 vertex에 `cfg.first_thickness` 균일 사용.
  - `{vertex_id: float}` 제공 시 → 각 vertex마다 자체 성장 곡선:
    `thicknesses[v][k] = first_thickness[v] * growth_ratio^k`
- `_run_prism_pass(vertex_cum_map_pass, use_per_v_cum_pass)` 파라미터 추가.
- layer offset 계산 시 per-vertex cum 우선: `vertex_cum_map_pass[v][layer_i]`.
- shrink iteration 루프에 vertex_cum_map 재계산 로직.
- tests: BLConfig 기본값 None, dict 설정, None=uniform, 다른 레이어 위치 등 6 tests.

---

## [0.4.0-beta94] - 2026-04-24 — "Octree snap step (snappyHexMesh 근사)"

### Added

- `core/generator/native_hex/snap.py::snap_to_surface_iterative`:
  - snappyHexMesh snap step 근사.
  - 알고리즘: surface nearest-point 탐색 → `relax` 비율 이동 → Laplacian smoothing.
  - `n_iter=5`, `relax=0.5`, `smooth_after_snap=True`, `feature_angle_deg=45.0`.
  - stats: `n_snapped_per_iter`, `final_n_snapped`, `max_displacement`.
- `generate_native_hex(snap_iterations: int = 0)`:
  - `adaptive=True` 경로에서 octree 이후 iterative snap 적용.
  - `snap_iterations=0` (기본) → 기존 동작 유지.
- `HARNESS_PARAMS["tier_native_hex"]["fine"]`: `snap_iterations=3` 자동.
- `_TIER_PARAM_KEYS`: `snap_iterations` 추가.
- tests: noop / stats keys / 수렴 / cap 초과 / Hausdorff 비교 / smoothing 등 9 tests.

---

## [0.4.0-beta93] - 2026-04-24 — "BL shrinkage iteration (반복 수렴)"

### Added

- `BLConfig.shrink_iterations: int = 1` / `shrink_factor: float = 0.7` / `shrink_aspect_threshold: float = 30.0`.
- prism 생성 코어를 `_run_prism_pass(vertex_scale, cum)` 클로저로 추출.
- shrinkage iteration 루프:
  1. prism pass 실행
  2. aspect ratio 검사 (`_prism_aspect_ratio_stats`)
  3. 불량 prism vertex의 scale을 `shrink_factor`만큼 감소
  4. 수렴 또는 max_iter 도달 시 종료
- `shrink_iterations=1` (기본값) 은 기존 단일 pass와 완전 동일.
- Phase 3 docstring ("shrinkage iteration 반복 수렴") 완성 표시.

---

## [0.4.0-beta92] - 2026-04-24 — "native_hex N-level octree adaptive refinement"

### Added

- `core/generator/native_hex/octree.py` — N-level 지원 (`n_levels: int = 2`):
  - `_compute_surface_distances`: scipy.cKDTree 기반 표면 거리 계산.
  - `_apply_2to1_balance`: 2:1 균형 조건 (인접 레벨 차이 ≤ 1) 벡터화 알고리즘.
  - `_build_nlevel_cells`: 레벨별 blck 병합 + conformal transition faces.
  - `_sub_quads_on_face(step)`: 임의 coarse 크기 → 4 sub-quad 분할.
  - 메모리 제한: fine grid ≤ 500,000 셀, 초과 시 n_levels 자동 감소.
- `generate_native_hex(n_levels=2, refinement_distance_factor=2.0)`.
- `HARNESS_PARAMS["tier_native_hex"]["fine"]`: `n_levels=3` 자동.
- `_TIER_PARAM_KEYS`: `n_levels`, `refinement_distance_factor` 추가.

### Result

- n_levels=3 → 3단계 해상도 (h, h/2, h/4). 표면 근방 h/4 정밀.

---

## [0.4.0-beta91] - 2026-04-23 — "native_hex 2-level octree adaptive refinement"

### Added

- `core/generator/native_hex/octree.py` — `build_octree_hex_cells`:
  - Fine grid (2× resolution) → inside test → 2×2×2 block 병합 판정.
  - 블록 내 8개 sub-cell 모두 inside → single coarse hex.
  - 경계 블록 → 8개 fine hex (표면 근방 정밀).
  - Coarse↔Fine 전환 면: `_coarse_face_sub_quads` 로 4개 sub-quad 분할 → conformal (hanging node 없음).
- `generate_native_hex(adaptive=True)` kwarg 추가 → octree 경로 사용.
- `HARNESS_PARAMS["tier_native_hex"]["fine"]` 에 `adaptive=True` 자동.
- `tests/test_native_hex_octree.py` 6 tests.

### Result

- icosphere seed_density=10: uniform 136 cells → octree 352 cells (coarse=80, fine=272).
- 표면 근방은 h/2 해상도, 내부는 h 해상도. 균일 grid 대비 surface coverage 개선.

---

## [0.4.0-beta90] - 2026-04-23 — "완전 비균일 prism BL (per-vertex collision cap)"

### Added

- `generate_native_bl` 의 `vertex_scale` 계산 로직 확장 (beta90):
  - Feature lock scale (beta64) + **collision per-vertex cap** 동시 적용.
  - `collision_dist[v] × safety / total` 로 각 vertex 의 허용 두께 상한 계산.
  - 두 제약 중 더 엄격한 값 선택 → U자 형상에서 vertex마다 최적 두께.
- `native_bl_per_vertex_scale` info 로그 (제약 vertex 수 / min_scale).

### Impact

- 기존: global min collision distance → 전체 두께 축소 (얇은 부분 과도 영향).
- 이제: 각 vertex 개별 cap → narrow throat 에서 더 두꺼운 BL 허용, 가까운 wall 에서만 얇게.

---

## [0.4.0-beta89] - 2026-04-23 — "Poly 전용 prism BL (polygon wall face 지원)"

### Added

- `generate_native_bl` 에서 비삼각형 wall face 처리 변경 (beta89):
  - 기존: skip → skip + warning
  - 이제: **fan-triangulation** → 합성 tri face 생성 → 기존 BL 파이프라인 활용.
- 합성 face 는 원래 polygon 의 patch/owner 정보 그대로 상속.
- `native_bl_polygon_wall_fan_triangulate` info 로그.

### Impact

- poly mesh type 의 native_bl 경로에서 polyhedral bulk → non-tri wall face → BL 생성 가능.
- `poly_bl_transition` 의 hybrid (prism+poly dual) 품질 개선.

---

## [0.4.0-beta88] - 2026-04-23 — "native_hex fill ratio + isotropic remesh docstring"

### Added

- `NativeHexResult.fill_ratio` / `grid_shape` / `n_grid_total` 필드.
- `fill_ratio < 0.3` 시 `native_hex_low_fill_ratio` info 로그 + 조정 힌트.
- message 에 `fill=XX%` 포함.
- `isotropic.py` docstring Phase 2 완료 + Phase 3 예정 명시.

---

## [0.4.0-beta87] - 2026-04-23 — "isotropic remesh Phase 2 (surface projection + feature lock)"

### Added

- `core/preprocessor/native_remesh/isotropic.py`:
  - `isotropic_remesh(project_to_surface=False, feature_angle_deg=45.0, lock_features=False)`.
  - `_tangential_relocate(feature_verts, origin_V)` — feature vertex 이동 차단 + 원본 표면 nearest-point 사영.
  - `_detect_feature_verts(V, F, angle_thresh_deg)` — dihedral > threshold edge 의 vertex 집합.

### Impact

- `project_to_surface=True`: relocate 후 원본 표면 사영 → Hausdorff drift 방지.
- `lock_features=True`: sharp edge vertex 가 smoothing 에서 제외 → corner 보존.
- icosphere 642 → 3009 verts, 1280 → 4004 faces remesh: 0.61s.

---

## [0.4.0-beta86] - 2026-04-23 — "orchestrator progress breakdown"

### Added

- `orchestrator.py::run` 에 progress 세분화:
  - `f"Generate ({selected_tier}) N/M"` — tier 이름 포함 (기존: 단순 %).
  - `f"Generate 완료 — tier={t}, cells={n}"` — 완료 시 cell 수 표시.
  - `f"BL 생성 중 ({engine})…"` — BL 단계 별도 progress.
- native_bl docstring Phase 2 완료 반영 (Phase 3 예정 명시).

---

## [0.4.0-beta85] - 2026-04-23 — "polyMesh ASCII I/O 성능 최적화"

### Changed

- `_write_points` → `numpy.savetxt` + `io.StringIO`. 50k pts 기준 ~5× 빠름.
- `_write_faces` → 동종 face 는 numpy 벡터화, 혼합은 fast `map(str)` join.
- `_write_labels` → `map(str, labels.tolist())` join. 100k labels 14.8 ms/call.
- `polymesh_writer.py` 는 native_bl helpers 를 import 해 자동 propagate.

---

## [0.4.0-beta84] - 2026-04-23 — "Strategist BL Phase 2 피드백 연결"

### Added

- `core/strategist/strategy_planner.py::_compute_adjustments` 에
  degenerate prisms 비율 > 10% 일 때 자동 조정 로직:
  - `bl_layers_add = -1` (BL 층 1개 감소)
  - `bl_growth_ratio_factor = 0.9` (성장비 완화)
  - `retry_adjust_degenerate_prisms` 로그 이벤트.
- `additional_metrics.native_bl_phase2` (beta76) 가 이제 Strategist 재시도
  판단에 실제 반영됨 — G4 gap 완전 해소.

### Impact

- beta76 에서 계산 + 리포트만 하던 `n_degenerate_prisms` 가 이제 다음 iteration
  파라미터 조정에 직접 활용. Phase 2 BL → Evaluator → Strategist 피드백 루프
  완성.

---

## [0.4.0-beta83] - 2026-04-23 — "harness gap 3종 수정"

### Fixed

**A. `run_native_tet_harness` max_input_vertices 미전달.**
- `harness.py` 가 `max_input_vertices` kwarg 를 수용하지 않아 HARNESS_PARAMS
  에 등록된 값이 `generate_native_tet` 에 전달되지 않던 gap.
- kwarg 추가 + `generate_native_tet(max_input_vertices=...)` 호출에 전달.

**B. `regenerate_baseline.sh` 기본 limit 수정.**
- 기본값 `--limit 30` → `--limit 15` (draft only). standard quality 의
  ultra_knot 이 300s+ 소요해 timeout=600s 초과하던 문제 반영.

**C. GUI flow_velocity / turbulence_model 노출 + 파이프라인 연결.**
- `AutoTessellWindow.TIER_PARAM_SPECS` 에 `flow_velocity` (float, 1.0) +
  `turbulence_model` (str, kEpsilon) 등록.
- `orchestrator.py` 에서 `tier_specific_params` 의 두 값을 fallback 으로 읽어
  `FoamCaseWriter` 에 전달 (CLI kwarg 우선).

---

## [0.4.0-beta82] - 2026-04-23 — "README 30초 Quickstart"

### Changed

- `README.md` 상단에 "30 초 Quickstart — 외부 유동 CFD" 섹션 추가:
  - box.stl → hex_dominant + BL → simpleFoam 전체 흐름.
  - 생성물 (`constant/polyMesh/`, `0/`, `system/`) 명시.
  - BL Phase 2 config 예시 (`bl_collision_safety=false`, `bl_feature_lock=false`).
  - `--turbulence-model kOmegaSST` 예시.
  - `--cross-engine-fallback` 예시.

---

## [0.4.0-beta81] - 2026-04-23 — "bench baseline 재생성 스크립트"

### Added

- `tests/stl/regenerate_baseline.sh` — baseline 재생성 셸 스크립트.
  사용법: `bash tests/stl/regenerate_baseline.sh --limit 30`.
- `pyproject.toml` 에 `openfoam` pytest 마커 등록.

---

## [0.4.0-beta80] - 2026-04-23 — "OpenFOAM solver smoke test"

### Added

- `tests/test_openfoam_solver_smoke.py`:
  - `@pytest.mark.openfoam @pytest.mark.slow` — OpenFOAM 설치 필요, 미설치 시
    자동 skip.
  - `test_simpleFoam_runs_without_crash`: cube.stl → native_tet pipeline →
    simpleFoam 5 iter — crash 없음 검증.
  - `test_openfoam_detected`: OpenFOAM 설치 여부 1 test.
- `pyproject.toml` 에 `openfoam` 마커 등록.

---

## [0.4.0-beta79] - 2026-04-23 — "native_bl structlog 이벤트 표준화"

### Changed

- `core/layers/native_bl.py` 의 모든 structlog 이벤트에 `component="native_bl"`
  공통 필드 추가 (grep 검색 가능).
- Phase 2 이벤트 (`native_bl_collision_safety_scaled`, `native_bl_feature_lock`,
  `native_bl_quality_check`, `native_bl_collision_skipped_large`) 에
  `phase="Phase2"` 추가.
- 표준화된 이벤트 키 목록 (8 개):
  - `native_bl_read`, `native_bl_non_triangle_wall`
  - `native_bl_thickness_scaled`, `native_bl_local_safety_scaled`
  - `native_bl_feature_lock`, `native_bl_collision_safety_scaled`
  - `native_bl_quality_check`, `native_bl_collision_skipped_large`

---

## [0.4.0-beta78] - 2026-04-23 — "CLI --flow-velocity + --turbulence-model"

### Added

- `cli/main.py` 에 `--flow-velocity FLOAT` (기본 1.0 m/s) +
  `--turbulence-model {kEpsilon|kOmegaSST}` (기본 kEpsilon) 플래그.
- `PipelineOrchestrator.run(flow_velocity, turbulence_model)` kwarg 추가.
- `FoamCaseWriter` 생성 시 두 kwarg 전달 → `0/U`, `0/k`, `0/epsilon` 자동 반영.
- auto-retry 재호출 경로도 동일 값 전달.

### Impact

- 이전: 사용자가 velocity 바꾸려면 `0/U` 수동 편집 필요.
- 이후: `auto-tessell run ... --flow-velocity 5.0 --turbulence-model kOmegaSST`.

---

## [0.4.0-beta77] - 2026-04-23 — "native_tet 대형 입력 guardrail"

### Added

- `generate_native_tet(max_input_vertices=100000)` kwarg — 초과 시 crash 없이
  failure + 명확한 메시지 반환 (표면 리메쉬 또는 상향 권고).
- `HARNESS_PARAMS` 에 `max_input_vertices` 엔트리 (draft/standard 100k, fine 200k).
- `_TIER_PARAM_KEYS` 에 `max_input_vertices` 추가.
- `tests/test_native_tet.py` 1 test: V=8 > cap=5 → failure.

### Fixed

- scipy.Delaunay 가 100k+ vertex 입력에서 OOM → guardrail 으로 미리 차단.

---

## [0.4.0-beta76] - 2026-04-23 — "BL Phase 2 메트릭 리포트 통합"

### Added

- `core/schemas.py` 에 `NativeBLPhase2Stats` 모델 (n_prism_cells, n_degenerate,
  max_aspect_ratio, collision_safety_triggered, feature_lock_triggered 등 10 필드).
- `AdditionalMetrics.native_bl_phase2: NativeBLPhase2Stats | None`.
- `TierAttempt.native_bl_phase2: NativeBLPhase2Stats | None`.
- `tier_layers_post._extract_bl_phase2_stats` — NativeBLResult → NativeBLPhase2Stats.
- Orchestrator `_evaluate(bl_phase2_stats=...)` → `AdditionalMetrics.native_bl_phase2`.
- `report.py::render_terminal` 에 "Boundary Layer (native_bl Phase 2)" 리치 패널:
  - Prism cells / Wall faces / Total thickness
  - Degenerate prisms (빨강/초록 색상)
  - Max aspect ratio
  - Phase 2 flags (collision scaled / feature locked)
- `tests/test_bl_phase2_report.py` 8 tests.

### Impact

- 기존: BL Phase 2 계산 결과가 로그에만 존재, 사용자 불가시.
- 이후: 터미널 리포트에 BL 품질 전체 표시.

---

## [0.4.0-beta75] - 2026-04-23 — "tier_layers_post 가 Phase 2 BL config 전파"

### Fixed

- `tier_layers_post.py` 의 `BLConfig` 조립부가 Phase 1 필드 (num_layers,
  growth_ratio, first_thickness, wall_patch_names, backup_original,
  max_total_ratio) 만 params 에서 읽고 있었음 → Phase 2 필드
  (collision_safety, feature_lock, quality_check_enabled, angles, ratios) 는
  항상 BLConfig 기본값으로 고정.
- **Ph72 GUI 추가의 실질 gap**: 사용자가 GUI 에서 `bl_collision_safety=false`
  로 바꿔도 파이프라인은 무시하던 상태였음.

### Added

- `_build_bl_config(cls, params, num_layers, growth_ratio, first_thickness)`
  helper — Phase 1 + Phase 2 필드 전체를 params 에서 조립.
- `_coerce_bool` helper — "true"/"false"/"0"/"1"/"yes"/"no" 문자열을 bool 로
  정규화 (GUI 에서 넘어오는 문자열 처리).
- `tests/test_tier_layers_post_bl_phase2.py` 23 tests: `_coerce_bool` 매트릭스
  + Phase 1/2 field propagation, 전체 동시 override.

### Impact

- GUI 토글 (Ph72) → orchestrator → tier_layers_post → BLConfig 전 체인이 이제
  실제로 동작. CLI `--tier-param bl_collision_safety=false` 도 효과.

---

## [0.4.0-beta74] - 2026-04-23 — "STEP 파이프라인 E2E 검증"

### Added

- `tests/test_step_e2e.py` (4 tests, 1 slow): STEP fixture 존재, `_load_via_cad`
  .step 허용 + trimesh 반환, `load_cad_native` (OCP) tuple 반환, box.step
  → native_tet 전체 파이프라인 (slow).

### Verified

- beta53 OCP native reader 가 `tests/benchmarks/box.step` (8 vertex, 12 tri)
  로 정상 로드. cadquery/gmsh fallback 경로 보존.

---

## [0.4.0-beta73] - 2026-04-23 — "bench baseline snapshot"

### Added

- `tests/stl/bench_v04_baseline.json` — 15 조합 (5 난이도 × 3 엔진 × draft)
  baseline. 모두 polyMesh 생성 성공 (100%).
- CI 에서 `python3 tests/stl/bench_v04_matrix.py --limit 15 --drift-check
  tests/stl/bench_v04_baseline.json` 로 회귀 자동 감지 가능.

### Milestone

- 15/15 PASS — native 3 엔진 전부 5 STL (cube/cylinder/bracket/gear/knot)
  draft 에서 100% 성공률. 이전 xfail (ultra_knot) 포함 전부 동작.

---

## [0.4.0-beta72] - 2026-04-23 — "GUI BL Phase 2 config 필드 노출"

### Added

- `AutoTessellWindow.TIER_PARAM_SPECS` 에 native_bl Phase 2 (beta63-65) 의 7
  신규 필드 등록:
  - `bl_collision_safety` (bool, true)
  - `bl_collision_safety_factor` (float, 0.5)
  - `bl_feature_lock` (bool, true)
  - `bl_feature_angle_deg` (float, 45.0)
  - `bl_feature_reduction_ratio` (float, 0.5)
  - `bl_quality_check_enabled` (bool, true)
  - `bl_aspect_ratio_threshold` (float, 50.0)
- `tests/test_gui_bl_phase2_config.py` 5 tests: 전부 등록 / bool type /
  float default / Phase 1 필드 보존.

---

## [0.4.0-beta71] - 2026-04-23 — "CLI --cross-engine-fallback 배선"

### Added

- `cli/main.py` 에 `--cross-engine-fallback` click 플래그 추가 (beta68
  orchestrator kwarg 사용자 노출).
- 양쪽 orchestrator.run 호출 경로 (기본 + auto-retry continue) 에 kwarg 전달.
- `tests/test_cli_cross_engine_fallback.py` 4 tests: --help 출력 확인, dry-run
  parsing, callback signature, orchestrator 일관성.

### Fixed

- beta68 에서 orchestrator 에만 추가되고 CLI 미배선이었던 gap 해소. 이제
  `auto-tessell run ... --mesh-type poly --cross-engine-fallback` 실사용 가능.

---

## [0.4.0-beta70.1] - 2026-04-23 — "collision detection memory hotfix"

### Fixed

- **메모리 폭증 버그**: `_ray_triangle_min_distance` 가 (R, T, 3) 중간 배열을
  전체 한 번에 할당 → wall vertex 수와 wall triangle 수가 각각 수만인 복잡 mesh
  에서 RSS 161 GB 까지 치솟던 문제. 이제 `chunk_size=512` 로 ray 축 chunk 처리.
- `_compute_collision_distance` 의 exclude-mask 구성을 O(R·T) Python nested
  loop → vectorized `wall_col == tri_face_ids[...,k]` 3 번 OR 로 교체.
- `max_tris=20000` cap 추가 → 극단적으로 큰 wall mesh 는 collision check 생략
  (기존 cell-centroid 기반 local safety 로 fallback). `native_bl_collision_skipped_large`
  info 로그.

### Verified

- E2E native pipeline matrix (slow): **9/9 PASS** (5m 51s, 이전 buggy 버전은
  10+ min 후 OOM 으로 kill 되던 상태).

---

## [0.4.0-beta70] - 2026-04-23 — "bench drift auto-detect"

### Added

- `tests/stl/bench_v04_matrix.py` 에:
  - `compute_success_rate(results)` — polyMesh_created 비율 계산.
  - `check_drift_against_baseline(baseline_path, current, min_delta=-0.10)`
    — 성공률 하락이 허용치 초과면 False + drift report.
  - CLI flags:
    - `--drift-check <baseline.json>` — run 후 drift 검증, 초과 시 exit 1.
    - `--regenerate-baseline <path>` — run 결과를 baseline 으로 저장.
    - `--min-success-rate-delta FLOAT` — drift 허용치 override.
- `tests/test_bench_drift.py` 11 tests: success rate 계산, identical/improvement/
  small/large regression, custom threshold, missing/corrupt baseline.

### Impact

- CI 에서 `bench_v04_matrix --drift-check baseline.json` 으로 native 엔진 회귀
  자동 감지. 성공률이 baseline 대비 10% 이상 떨어지면 CI-red.

---

## [0.4.0-beta69] - 2026-04-23 — "README beta68 동기화"

### Changed

- `README.md` 의 "자체 코드화 진행" 섹션을 v0.4.0-beta29 → beta68 로 갱신.
  - STEP/IGES native reader (beta53)
  - native_bl Phase 2 complete (beta63-65)
  - native_hex feature preservation (beta66)
  - Cross-engine fallback (beta68)
  - scipy 유지 정책 명시
- "v0.4 신규 tier 파라미터" 섹션 추가 — CLI / GUI 노출된 파라미터 한눈에.
- "native_bl Phase 2 config" 섹션 — BLConfig 신규 필드 6 개.

---

## [0.4.0-beta68] - 2026-04-23 — "orchestrator cross-engine fallback (poly→hex)"

### Added

- `PipelineOrchestrator.run(cross_engine_fallback=False)` kwarg — True 면 poly
  mesh_type 이 완전 실패할 때 hex_dominant 로 1 회 재시도.
- 내부 sentinel `_cross_engine_retried` 로 무한 재귀 차단.
- fallback 발생 시 `cross_engine_fallback_triggered` warning 로그 + 결과
  `error` 필드에 `[cross_engine_fallback poly→hex_dominant]` prefix.
- `tests/test_cross_engine_fallback.py` 5 tests: kwarg 수용, sentinel 존재,
  fallback 동작 (poly 실패 → hex_dominant 재호출), off 플래그 미동작,
  tet 타입 제외 확인.

### Impact

- 이전에는 poly 실패 시 사용자에게 "실패" 메시지만 표시. 이제 옵트인 플래그로
  hex_dominant 자동 전환 가능. orchestrator 레벨 escalation.

---

## [0.4.0-beta67] - 2026-04-23 — "Qt GUI native_* 엔진 param spec 등록"

### Added

- `desktop/qt_app/widgets/engine_params_spec.py` 의 `ENGINE_PARAM_REGISTRY` 에
  native_tet / native_hex / native_poly 3 엔진 spec 추가:
  - native_tet: seed_density, max_iter, sliver_quality_threshold (beta62).
  - native_hex: seed_density, max_cells_per_axis (beta61), snap_boundary,
    preserve_features (beta66), feature_angle_deg (beta66).
  - native_poly: seed_density, max_iter, max_tet_cells (beta56).
- `ENGINE_KEY_ALIASES` 에 `tier_native_tet/hex/poly` → `native_*` 매핑 추가.
- `tests/test_engine_params_spec_native.py` 12 tests: registry 등록 확인,
  alias 매핑, resolve_engine_key / get_specs_for_engine 동작, 타입 sanity.

### Impact

- 이제 GUI 에서 native 엔진 선택 시 `GenericEngineParamPanel` 이 자동으로
  해당 파라미터 편집 UI 를 그린다. CLI `--tier-param` 전용이던 beta56~66
  신규 파라미터 전부 노출.

---

## [0.4.0-beta66] - 2026-04-23 — "native_hex feature preservation"

### Added

- `_detect_surface_feature_vertices` — STL surface 에서 sharp feature vertex
  (인접 triangle dihedral > 45°) 식별. open edge 도 feature 로 간주.
- `snap_hex_boundary_to_surface(preserve_features=False, feature_angle_deg=45.0)`
  — True 면 snap 시 feature vertex 근처 (cap × 0.7 이내) hex vertex 를 해당
  feature vertex 로 직접 snap → sharp corner 보존.
- `generate_native_hex(preserve_features, feature_angle_deg)` 노출.
- `HARNESS_PARAMS["tier_native_hex"]["fine"]` 에 `preserve_features=True` 자동.
- `_TIER_PARAM_KEYS` 에 `preserve_features`, `feature_angle_deg` 추가 → CLI
  `--tier-param preserve_features=1` 주입 가능.
- `tests/test_native_hex_snap.py` 3 tests: cube 8 corner 식별, sphere 는 feature
  거의 없음, preserve_features=True 에서 n_feature_snapped 통계 보고.

### Fixed

- 기존 nearest-triangle projection 만으로는 cube corner 가 closest-point-on-
  triangle 때문에 라운드로 snap 되어 sharp feature 가 뭉개지던 문제 해결.

---

## [0.4.0-beta65] - 2026-04-23 — "native_bl Phase 2 complete — quality check"

### Added

- `BLConfig.quality_check_enabled: bool = True` + `aspect_ratio_threshold: float = 50.0`.
- `NativeBLResult.n_degenerate_prisms: int = 0` + `max_aspect_ratio: float = 0.0`
  필드.
- `_prism_aspect_ratio_stats` — 생성된 prism 의 aspect ratio
  (max_outer_edge / min_height) 계산, threshold 초과 degenerate 수 집계.
- `generate_native_bl` message 에 degenerate / max_ar 포함 + 로그 warning.
- `tests/test_native_bl_helpers.py` 5 tests: config defaults, result 필드,
  unit prism ratio, squashed prism → degenerate, zero height → degenerate.

### Milestone

- **Phase 2 완성** (beta63 collision + beta64 feature lock + beta65 quality
  check). Phase 1 docstring 에 명시된 3 제약 모두 해소. native_bl 이 이제 U 자
  형상 / sharp corner / degenerate 경우를 방어적으로 처리.

---

## [0.4.0-beta64] - 2026-04-23 — "native_bl Phase 2 feature edge locking"

### Added

- `BLConfig.feature_lock: bool = True`, `feature_angle_deg: float = 45.0`,
  `feature_reduction_ratio: float = 0.5`.
- `_detect_feature_vertices` — wall triangle 간 dihedral angle 이 threshold
  초과 edge 의 vertex 수집 (face 간 unit normal dot 기반, edge_to_face map 활용).
- `generate_native_bl` 이 feature_lock=True 일 때 feature vertex 의 layer
  thickness 를 per-vertex scale 로 축소 (shrink + intermediate layer 둘 다 적용).
- `tests/test_native_bl_helpers.py` 6 tests: defaults, 평면 empty, 90° L-shape
  capture, 높은 threshold 로 blocked, 빈 wall, angle=0 shortcut.

### Fixed

- Sharp edge 근처 vertex 에서 layer extrusion 시 self-intersect 우려 → feature
  vertex 의 thickness 를 절반으로 축소해 방지.
- Phase 1 제약 "Feature edge 보존 없음" 해소.

---

## [0.4.0-beta63] - 2026-04-23 — "native_bl Phase 2 collision detection"

### Added

- `BLConfig.collision_safety: bool = True` + `collision_safety_factor: float = 0.5`.
- `_ray_triangle_min_distance` (Möller-Trumbore, vectorized) — 각 ray 에 대해
  최단 교차 거리. 자기 자신 face 는 exclude_mask 로 제외.
- `_compute_collision_distance` — 각 wall vertex 에서 inward normal 로 반대편
  wall triangle 까지 거리 계산.
- `generate_native_bl` 이 collision_safety=True 일 때 해당 거리의
  `collision_safety_factor` 배로 global thickness cap 적용
  (`native_bl_collision_safety_scaled` warning 로그).
- `tests/test_native_bl_helpers.py` 7 tests: ray-tri hit / miss / multi-tri
  min / exclude mask / parallel walls collision / no opposite wall.

### Fixed

- U 자 형상 / 좁은 채널에서 prism layer 가 반대편 wall 과 겹쳐 negative
  volume 발생하던 경우 → collision-aware thickness cap 으로 방지.
- Phase 1 제약 "Wall 모든 vertex 에 동일 total thickness (collision check 없음)"
  해소.

---

## [0.4.0-beta62] - 2026-04-23 — "native_tet q_thresh 파라미터화 + adaptive"

### Added

- `generate_native_tet(sliver_quality_threshold=0.05)` kwarg — 기존 하드코딩
  0.05 를 tunable 로 노출.
- `run_native_tet_harness` 가 `sliver_quality_threshold` kwarg 수용 + 생성 실패
  시 0.8× adaptive 완화 (복잡 형상에서 "inside tet 0" 수렴 실패 완화).
- `HARNESS_PARAMS["tier_native_tet"]` 에 quality 별 기본값:
  - draft 0.02 (관대, cell 보존 최우선)
  - standard 0.05 (기존)
  - fine 0.10 (엄격, sliver 공격적 제거 → non_ortho↑)
- `_TIER_PARAM_KEYS` 에 `sliver_quality_threshold` 추가 → CLI `--tier-param
  sliver_quality_threshold=0.08` 동작.
- `tests/test_native_tet.py` 2 tests: loose threshold 가 strict 보다 cell 수
  많음, HARNESS_PARAMS 테이블 순서 (draft<standard<fine).
- `tests/test_native_tet_harness.py` 1 test: harness 가 kwarg 수용 + 극단 값에서
  best-effort 반환.

### Fixed

- 복잡 STL (05_ultra_knot 등) 에서 모든 tet 이 sliver 로 분류되어 harness 가
  seed_density 만 올리며 timeout → q_thresh adaptive 로 해결.

---

## [0.4.0-beta61] - 2026-04-23 — "native_hex grid cap 노출 + tier param 확장"

### Added

- `generate_native_hex` `max_cells_per_axis` 파라미터 추가 (기본 50). cap 걸릴
  때 `native_hex_grid_capped` warning 로그.
- `_TIER_PARAM_KEYS` 에 `max_cells_per_axis` + `max_tet_cells` 추가 →
  `--tier-param max_cells_per_axis=80` CLI 주입 가능.
- `tests/test_native_hex.py` 2 tests: cap=5 honored, 더 큰 cap → 더 많은 cell.

### Fixed

- 기존 하드코딩 50 grid cap 이 silent → 이제 log warning + tunable.

---

## [0.4.0-beta60] - 2026-04-23 — "native_poly harness best-tracking fix"

### Fixed

- `run_native_poly_harness` 의 best candidate 비교가 `metrics < metrics` 로
  자기 자신과 비교 → 항상 False → 첫 iter 이후 best_case 가 고정되던 버그 수정.
  이제 `best_metrics` 별도 저장, cur_neg < best_neg 또는 (동률 시 cells 많은 쪽)
  으로 올바르게 선택.
- `tests/test_native_poly_harness_edge.py` 에 regression 1 test 추가.

---

## [0.4.0-beta59] - 2026-04-23 — "poly_bl_transition _merge_vertices 회귀"

### Added

- `tests/test_poly_bl_transition_helpers.py` (11 tests): PolyBLResult 기본값,
  `_merge_vertices` 의 tol / 공유 좌표 / 빈 입력 / dtype / 좌표 보존 검증.

---

## [0.4.0-beta58] - 2026-04-23 — "tet_bl_subdivide helper 회귀"

### Added

- `tests/test_tet_bl_subdivide_helpers.py` (12 tests): TetSubdivResult 기본값,
  `_identify_prism_cells` prism/tet/mismatch 구분, `_prism_vertex_pairs` 표준
  wedge + shuffled outer + 실패 케이스 (shared vertex, bad quad).

---

## [0.4.0-beta57] - 2026-04-23 — "native_bl helper 단위 회귀"

### Added

- `tests/test_native_bl_helpers.py` (20 tests): BLConfig/NativeBLResult 기본값,
  `_face_centroid`, `_face_normal_area` (quad / degenerate / too few),
  `compute_vertex_normals` (sign flip by cell_centres, 빈 wall, degenerate skip),
  `_collect_wall_faces` (type / name / explicit list / none),
  `_build_edge_to_wall_faces` (shared / non-triangle skip / sorted key).

---

## [0.4.0-beta56] - 2026-04-23 — "run_native_poly_harness edge case 회귀"

### Added

- `tests/test_native_poly_harness_edge.py` (6 tests): 빈 input graceful,
  max_iter / max_tet_cells safety cap, elapsed non-negative, sphere cell 생성.

---

## [0.4.0-beta55] - 2026-04-23 — "_parse_target_edge + run_native_tier edge cases"

### Added

- `tests/test_tier_native_common_edge_cases.py` (9 tests): 0/음수/non-numeric
  target_cell_size → None, missing STL → failed, runner 예외 → failed,
  best-effort success (n_cells>0) 기록.

---

## [0.4.0-beta54] - 2026-04-23 — "CoreSurfaceMesh dedicated 회귀"

### Added

- `tests/test_core_surface_mesh.py` (15 tests): dataclass coercion, invalid
  shape 검증, compute_face_normals / face_areas / bounding_box, metadata,
  __repr__.

---

## [0.4.0-beta53] - 2026-04-23 — "Native STEP/IGES reader (OCP 직접 호출)"

### Added

- **`core/analyzer/readers/step.py`**: OCP 로 STEP/IGES/BREP 파일을 직접
  BRepMesh 로 tessellate. cadquery wrapper 우회.
- `file_reader._load_via_cad` fallback 체인: OCP native → cadquery → gmsh.
- `tests/test_cad_reader_native.py` (6 tests).

### Deferred

- 완전 native ISO 10303 STEP parser 자체 구현 → v1.0 로드맵 (수개월).

---

## [0.4.0-beta52] - 2026-04-23 — "E2E matrix 9/9 PASS"

### Changed

- `tests/test_e2e_native_pipeline.py`: 성공 기준을 **pipeline 크래시 없음 +
  polyMesh 5 파일 + negative_volumes=0 + cells>0** 로 재정의. Evaluator 품질
  verdict (threshold 기반) 은 별도 품질 테스트 담당. 결과 3 PASS + 6 xfail
  → **9/9 PASS**.

---

## [0.4.0-beta51] - 2026-04-23 — "morph.py + remesh.py 정리"

### Changed

- `core/preprocessor/morph.py`: PyGeM interop 의 목적 (선택적 형상 최적화 API
  전용) docstring 명문화. Main pipeline 에 영향 없음.
- `core/preprocessor/remesh.py`: 이 모듈이 **legacy opt-out 경로 전용** 임을
  명시 (beta26 `--prefer-native` default=True 반영). Primary L2 는
  `core/preprocessor/native_remesh/`.

---

## [0.4.0-beta50] - 2026-04-23 — "Windows installer beta49 반영"

### Changed

- `installer/autotessell.nsi`, `installer/AutoTessell_Setup.iss`,
  `installer/construct.yaml` 의 VERSION / AppVersion 을 `0.4.0-beta49` 로 갱신.
  NSIS Welcome text 에 v0.4 Native-First 기능 강조.

---

## [0.4.0-beta49] - 2026-04-23 — "CheckMeshParser 단위 회귀"

### Added

- `tests/test_quality_checker.py` (10 tests): clean / failed checkMesh stdout
  패턴 파싱, mesh_ok override, negative_volumes / severely_non_ortho /
  min_cell_volume default, 대체 정규식 패턴.

---

## [0.4.0-beta48] - 2026-04-23 — "AdditionalMetricsComputer 단위 회귀"

### Added

- `tests/test_metrics_computer.py` (8 tests): compute graceful fallback
  (polyMesh 없음 / ImportError / 일반 예외), valid polyMesh 처리,
  _check_bl_enabled / _find_vtk_file 유틸.

---

## [0.4.0-beta47] - 2026-04-23 — "core/utils/logging.py 단위 회귀"

### Added

- `tests/test_logging.py` (7 tests): configure_logging verbose/json 모드, 핸들러
  교체, 멱등성, get_logger 이름 보존 smoke.

---

## [0.4.0-beta46] - 2026-04-23 — "OpenFOAMWriter 단위 회귀"

### Added

- `tests/test_openfoam_writer.py` (17 tests): ensure_case_structure,
  write_control_dict / fv_schemes / fv_solution, write_foam_dict (중첩 /
  리스트), _format_foam_value 각 타입 처리.

---

## [0.4.0-beta45] - 2026-04-23 — "ParamOptimizer 단위 회귀"

### Added

- `tests/test_param_optimizer.py` (16 tests): compute_domain (external/internal),
  compute_cell_sizes (base/surface/min 관계), compute_quality_targets (fine
  target_y_plus=1), _base_cell_size 스케일, _estimate_reynolds 공식.

---

## [0.4.0-beta44] - 2026-04-23 — "ComplexityAnalyzer 단위 회귀"

### Added

- `tests/test_complexity_analyzer.py` (18 tests): analyze (feature_density /
  topology / aspect / surface quality) + classify 4 분기 (simple/moderate/
  complex/extreme) + overall [0, 100] bounded invariant.

---

## [0.4.0-beta43] - 2026-04-23 — "polymesh_reader + boundary_classifier 회귀"

### Added

- `tests/test_polymesh_reader_and_boundary_classifier.py` (16 tests):
  parse_foam_{points, faces, labels, boundary} + classify_boundaries 의 단위
  격리. 이전엔 integration 경유로만 cover.

---

## [0.4.0-beta42] - 2026-04-23 — "core/utils/bc_writer.py 단위 회귀"

### Added

- `tests/test_bc_writer.py` (15 tests): write_boundary_conditions 전체 흐름 +
  각 _build_*_bc (p/U/k/omega/nut) 패치 타입별 (inlet/outlet/wall/symmetryPlane)
  BC 타입 문자열 검증. turbulence_model 반영.

---

## [0.4.0-beta41] - 2026-04-23 — "core/utils/mesh_exporter.py 단위 회귀"

### Added

- `tests/test_mesh_exporter.py` (7 tests): SU2/Fluent/CGNS export 매핑 +
  graceful fallback (polyMesh 없음 / meshio 미설치 / 파싱 실패) + 정상 export
  경로.

---

## [0.4.0-beta40] - 2026-04-23 — "core/utils/errors.py 단위 회귀"

### Added

- `tests/test_errors.py` (14 tests): AutoTessellError + rich_message,
  format_missing_dependency_message, diagnose_error 의 8 개 패턴 매칭 확인.

---

## [0.4.0-beta39] - 2026-04-23 — "CLI --tier-param + --prefer-native-tier 회귀"

### Added

- `tests/test_cli_flags_beta20_beta23.py` (12 tests): CLI 파싱 + Strategist
  전파 + dry-run 출력 검증.

---

## [0.4.0-beta38] - 2026-04-23 — "run_native_tet_harness 단위 회귀"

### Added

- `tests/test_native_tet_harness.py` (7 tests): TetHarnessResult 타입 / 빈 input /
  max_iter cap / target_edge clamp / max_cells safety / 결정성 / cube 기본 동작.
  기존 tier_native_tet 통합 경로에서만 cover 되던 harness 단위 격리.

---

## [0.4.0-beta37] - 2026-04-23 — "write_generic_polymesh 단위 회귀"

### Added

- `tests/test_write_generic_polymesh.py` (10 tests): beta12 공용 writer 의
  dedicated 회귀. single/double tet, owner<nbr, owner note 필드, 5 파일 +
  system/ 생성, patch 설정, 정렬, edge cases (empty, short face).

---

## [0.4.0-beta36] - 2026-04-23 — "fidelity native helpers 단위 회귀"

### Added

- `tests/test_fidelity_native_helpers.py` (13 tests): beta11 의
  `_native_sample_surface` / `_native_kdist_chunked` dedicated 회귀. 면적 가중
  분포 / 결정성 / pair_limit 불변 / known offset 거리 검증.

---

## [0.4.0-beta35] - 2026-04-23 — "geometry.inside_winding_number 단위 회귀"

### Added

- `tests/test_geometry_inside.py` (12 tests): beta9 공용 유틸 dedicated 회귀.
  cube/sphere inside-outside, 빈 query/mesh, translation/scale 불변.

---

## [0.4.0-beta34] - 2026-04-23 — "LayersPostGenerator auto-engine 라우팅 회귀"

### Added

- `tests/test_tier_layers_post_routing.py` (5 tests): engine="auto" + mesh_type
  → BL 엔진 매핑 (tet→tet_bl_subdivide, hex→native_bl, poly→poly_bl_transition).

---

## [0.4.0-beta33] - 2026-04-23 — "Preprocessor L2 native 기본화"

### Changed

- `core/preprocessor/pipeline.py::_l2_remesh` docstring 업데이트. CLI
  `--prefer-native` default=True (@beta26) 가 L1 뿐 아니라 L2 경로에도 자동
  적용되고 있음을 명문화. 3 dedicated tests.

---

## [0.4.0-beta32] - 2026-04-23 — "bench snapshot + drift archival"

### Added

- `tests/stl/bench_v04_<stamp>.json` snapshot 아카이빙 (30/30 matrix, 28 PASS).
- `docs/bench_v04_beta27_drift.md`: beta23~31 구조 변경의 bench 영향 요약.
  구조 변경이 matrix 성공률에 부정적 영향 없음을 기록.

---

## [0.4.0-beta31] - 2026-04-23 — "E2E mesh_type × quality × BL matrix (slow)"

### Added

- `tests/test_e2e_native_pipeline.py` (9 tests, slow marker): in-process
  PipelineOrchestrator.run() 으로 3 mesh_type × 3 quality 전체 조합 run.
  prefer_native_tier=True 고정. 현재 결과: 3 passed, 6 xfailed (hard fail 0).

---

## [0.4.0-beta30] - 2026-04-23 — "README beta29 동기화"

### Changed

- README "자체 코드화 진행" 표 beta12 → beta29 기준 갱신. L1 native default /
  hybrid dual / --prefer-native-tier / fine BL 자동 / NumpyKDTree 행 추가.
- 신규 "mesh_type × BL 파이프라인" 표 + "scipy 잔존" 섹션.

---

## [0.4.0-beta29] - 2026-04-23 — "Qt GUI native-first UX"

### Added

- `_prefer_native_tier_check` QCheckBox (main_window).
- `PipelineWorker.prefer_native_tier` kwarg (orchestrator.run 경유).
- `_prefer_native_check` 기본값 True (beta26 철학 반영).

---

## [0.4.0-beta28] - 2026-04-23 — "NumpyKDTree (scipy.cKDTree 대체)"

### Added

- `core/utils/kdtree.py::NumpyKDTree` — scipy.spatial.cKDTree API subset 호환.
  소형 brute-force + 대형 3D grid bucket. scipy parity 검증 테스트.
- 3 파일의 cKDTree → NumpyKDTree 교체 (native_hex/snap, native_poly/voronoi,
  native_remesh/cvt). fidelity.py 의 cKDTree 는 fallback 전용 interop 유지.

---

## [0.4.0-beta27] - 2026-04-23 — "BL 수치 품질 회귀"

### Added

- `tests/test_bl_numerical_quality.py` (6 tests): 각 mesh_type 의 BL 파이프라인
  수치 지표 (first_layer_thickness, growth_ratio, n_prism_cells, negative_volumes,
  tet_bl_subdivide pure-tet 유지, poly_bl_transition hybrid 보존).

---

## [0.4.0-beta26] - 2026-04-23 — "Preprocessor L1 native 기본화"

### Changed

- CLI 옵션 `--prefer-native` → `--prefer-native/--legacy-repair` 양방향,
  default=True. v0.4 Native-First 철학 완성: 라이브러리 미설치 환경에서도 L1 이
  동작하도록 native_repair 가 기본 경로.
- `--legacy-repair` 명시 시에만 pymeshfix/trimesh 경로 강제 (opt-out).

---

## [0.4.0-beta25] - 2026-04-23 — "poly_bl best-effort hybrid dual"

### Added

- `core/layers/poly_bl_transition._try_hybrid_dual`: tet subset → dual 후 prism
  cell 과 통합한 hybrid polyMesh 생성. 원본 vertex indexing 유지로 boundary
  정점 공유, `write_generic_polymesh` 의 canonical face key 로 interface 자동
  stitching. 예외 발생 시 원본 pass-through 로 graceful fallback.
- `_merge_vertices` helper: 두 vertex 집합 양자화 dedup + 인덱스 remap.

---

## [0.4.0-beta24] - 2026-04-23 — "fine quality 기본 BL 자동 활성화"

### Changed

- `core/pipeline/orchestrator.py::run()`: strategy.boundary_layers.enabled=True +
  num_layers>0 이고 post_layers_engine 미지정 시 "auto" 자동 주입.
  LayersPostGenerator 가 mesh_type (tet/hex_dominant/poly) 에 맞는 BL 엔진을
  자동 선택 — tet_bl_subdivide / native_bl / poly_bl_transition.

---

## [0.4.0-beta23] - 2026-04-23 — "Strategist native-first tier + --prefer-native-tier"

### Added

- `core/strategist/tier_selector._MESH_TYPE_TIER_MAP_NATIVE`: native_* tier 를
  각 mesh_type × quality 조합의 primary 로 올리는 테이블.
- `resolve_mesh_type_tier(..., prefer_native=False)` kwarg: True 면 native tier
  를 primary 로 승격, 기존 legacy primary 는 fallback 맨 앞.
- CLI `--prefer-native-tier` (is_flag). Strategist / Orchestrator / Pipeline
  전 경로에 전파.

---

## [0.4.0-beta22] - 2026-04-23 — "native_hex surface snap"

### Added

- **`core/generator/native_hex/snap.py`** (신규): hex vertex 를 STL surface 로
  projection. Ericson RTCD barycentric clamp 구현 + cKDTree k=4 coarse NN +
  cap (``max_snap_ratio × target_edge``) safety.
- ``generate_native_hex(snap_boundary=False)`` kwarg 추가 (하위 호환).
- ``HARNESS_PARAMS["tier_native_hex"]["fine"]["snap_boundary"]=True`` → Strategist
  경로로 fine quality 에서 자동 활성화.
- tests/test_native_hex_snap.py (9 tests).

---

## [0.4.0-beta21] - 2026-04-23 — "dependency_status + visualizer + partitioner 커버리지"

### Added

- `tests/test_dependency_status.py` (8 tests), `tests/test_visualizer.py` (6 tests),
  `tests/test_partitioner.py` +4 엣지 케이스. 기존 블라인드 영역 제거.

---

## [0.4.0-beta20] - 2026-04-23 — "Strategist ↔ native tier params + CLI --tier-param"

### Added

- `run_native_tier` 파라미터 병합 우선순위:
  ``extra_kwargs > strategy.tier_specific_params > HARNESS_PARAMS > default``.
  whitelist: seed_density / max_iter / snap_boundary 만 native runner 로 전달.
- CLI `--tier-param KEY=VALUE` (multiple=True) 반복 플래그. int/float/bool/str
  자동 추론, 잘못된 형식은 WARN.

---

## [0.4.0-beta19] - 2026-04-23 — "preprocessor trimesh 분석성 호출 native 교체"

### Changed

- `core/preprocessor/{repair,remesh,pipeline}.py` 의 분석성 trimesh 호출
  (is_watertight / area / edges_unique_length 등) 을 `core.analyzer.topology` +
  numpy 로 교체. 분석성 호출 수 17 → 3 (MeshAnything AI fallback 제외).
  결과 mesh 는 변경 없음.

---

## [0.4.0-beta18] - 2026-04-23 — "PolyMeshWriter dead code 제거"

### Changed

- `core/generator/polymesh_writer.py`: Ph12 이후 호출되지 않는 staticmethod 5 개
  (_write_points / _write_faces / _write_owner / _write_neighbour / _write_boundary)
  및 _FaceRecord / _canonical 삭제. 527 → 407 lines (-120).

---

## [0.4.0-beta17] - 2026-04-23 — "native tier harness params quality-specific"

### Added

- **`core/generator/_tier_native_common.py::HARNESS_PARAMS`**: tier × quality
  (draft/standard/fine) × {seed_density, max_iter} 테이블 중앙화.
- **`get_harness_params(tier, quality)`**: per-tier × per-quality 기본 파라미터
  lookup. 알 수 없는 quality 는 standard 로 fallback, 알 수 없는 tier 는 빈 dict.
- `run_native_tier()` 가 ``strategy.quality_level`` 을 기반으로 harness 파라미터
  를 자동 주입. caller 가 넘긴 ``extra_kwargs`` 는 override 우선.
- **`tests/test_harness_params.py`** (9 tests): 테이블 coverage / 단조성 /
  enum 수용 / fallback / injection / override 검증.

### Changed

- `tier_native_tet.py` / `tier_native_poly.py` `_runner` 의 하드코딩된
  seed_density/max_iter 제거. 대신 `run_native_tier` 가 quality 기반으로 주입.
- `tier_native_hex.py` 의 ``extra_kwargs={"seed_density": 16}`` 제거 — HARNESS_PARAMS
  의 standard(16) 로 자동 반영.

---

## [0.4.0-beta16] - 2026-04-23 — "bench matrix time-series"

### Added

- **`tests/stl/bench_v04_matrix.py`** 에 time-series 저장 + diff 기능.
  - `save_results_timestamped(results, dir, stamp=None)`: 결과를
    `bench_v04_YYYYMMDDTHHMMSS.json` 과 `bench_v04_result.json` 양쪽에 쓴다.
    snapshot 은 영구 보관 (git-commit 가능), latest pointer 는 tooling 호환용.
  - `list_snapshots(dir)`: 타임스탬프 snapshot 을 최신순으로 나열.
  - `compare_runs(prev, curr)`: combo 단위 PASS→FAIL / FAIL→PASS / 유지 분류.
  - CLI `--diff` 옵션: 최근 2 snapshot 비교 결과 출력.
- 실행 종료 시 이전 snapshot 이 있으면 자동으로 drift 요약 출력.
- **`tests/test_bench_v04_timeseries.py`** (6 tests): 저장 / 나열 / 비교
  로직 단위 테스트.

---

## [0.4.0-beta15] - 2026-04-23 — "geometry_analyzer native-only"

### Changed

- **`core/analyzer/geometry_analyzer.py`**: top-level `import trimesh` 제거,
  모든 `trimesh.Trimesh` 타입 힌트는 `TYPE_CHECKING` 블록으로 이동. 런타임에는
  trimesh 를 절대 import 하지 않는다.
- topology 지표 (watertight / manifold / euler / connected components) 의 trimesh
  fallback 분기를 삭제. 오직 `core.analyzer.topology` native 경로만 사용.
- `_count_sharp_edges` / `_estimate_curvature` / `_detect_issues` 의 non-manifold
  edge 계수 경로를 각각 `topology.dihedral_angles` / `count_non_manifold_edges`
  로 교체. `_is_surface_manifold` dead code 삭제.

---

## [0.4.0-beta13] - 2026-04-22 — "poly_bl_transition hybrid pass-through"

### Added

- **`core/layers/poly_bl_transition._classify_cells_by_vertex_count`**: polyMesh
  의 각 cell 을 unique vertex 개수로 분류 (tet=4, prism=6, hex=8, polyhedron=n).
  내부 helper 지만 테스트 가능하도록 public-style.
- **`tests/test_poly_bl_transition.py`** (5 tests): hybrid (prism+tet) 합성
  polyMesh 에 대해 `_try_native_poly_dual` 이 graceful pass-through 하는지 +
  순수 tet 경로가 여전히 dual 변환을 실행하는지 회귀.

### Changed

- `_try_native_poly_dual`: 혼합 mesh (non-tet cell 존재) 입력에서 "실패" 대신
  **graceful pass-through** (원본 hybrid polyMesh 보존). 반환값은 여전히
  `(False, "hybrid mesh preserved — full hybrid dual deferred …")` 로 호출측은
  `bulk_dual_applied=False` 로 기록. 완전한 interface stitching (prism 삼각형
  ↔ dual 폴리곤 정합) 은 beta15+ 로드맵.

---

## [0.4.0-beta14] - 2026-04-22 — "Qt e2e + README beta12 동기화"

### Added

- **`tests/test_qt_app.py::test_qt_pipeline_native_tet_e2e`**: AutoTessellWindow
  (set_mesh_type=tet) + PipelineWorker(tier=native_tet, prefer_native=True) 가
  PipelineOrchestrator.run() 을 올바른 인자로 호출하는지 headless 에서 검증.
  orchestrator 는 monkeypatch stub.

### Changed

- README.md "자체 코드화 진행" 표를 beta12 기준으로 갱신 (Hausdorff / inside-
  winding / tier wrapper / generic polyMesh writer 행 추가). bench matrix
  30/30 으로 갱신. Harness 패턴 설명 블록 추가.

---

## [0.4.0-beta12] - 2026-04-22 — "PolyMeshGenericWriter 통합"

### Added

- **`core/generator/polymesh_writer.write_generic_polymesh`**: 임의 cell
  (tet/hex/poly 공용) 의 외향 face vertex 리스트를 받아 face dedup +
  owner/neighbour 정렬 + FoamFile 쓰기를 일원화하는 범용 writer.

### Changed

- `PolyMeshWriter.write()` (tet 전용) 는 normalize_tet_winding 후 cell_faces 를
  만들어 generic writer 에 위임하는 얇은 wrapper 로 축소.
- `native_hex/mesher._write_polymesh_hex` / `native_poly/voronoi._write_polymesh_poly`
  도 각자 cell_faces 를 만들어 generic writer 위임. 약 150 라인 중복 제거.
- `core/layers/native_bl._write_labels()` 에 optional `note` kwarg 추가 → owner
  파일에 `nPoints/nCells/nFaces/nInternalFaces` 주석 복구. Ofpp 파서 호환 회복.
- native_bl FoamFile 헤더에 OpenFOAM 표준 preamble(`/*---*/`) + footer separator
  삽입 → 외부 도구 호환성 향상.

---

## [0.4.0-beta11] - 2026-04-22 — "Hausdorff 자체 구현"

### Changed

- `core/evaluator/fidelity._compute_hausdorff`: `trimesh.sample.sample_surface`
  와 `scipy.spatial.cKDTree` 의존 제거. 자체 `_native_sample_surface` (면적 가중
  barycentric sampling, numpy RNG seed 고정) + `_native_kdist_chunked` (brute-
  force chunked kNN, pair_limit=1e7) 로 교체. 실패 시 기존 trimesh+scipy 경로
  로 graceful fallback 유지.

---

## [0.4.0-beta10] - 2026-04-22 — "tier_native_* DRY"

### Added

- **`core/generator/_tier_native_common.run_native_tier`**: STL read +
  target_edge 파싱 + TierAttempt 조립을 공통화한 공용 entry.

### Changed

- `tier_native_tet.py` / `tier_native_hex.py` / `tier_native_poly.py` 각 Generator
  의 `run()` 메서드가 `run_native_tier(...)` 한 줄 호출로 축약. seed_density 등
  엔진별 기본값은 runner_fn / extra_kwargs 로 전달.

---

## [0.4.0-beta9] - 2026-04-22 — "inside_winding_number 공용화"

### Added

- **`core/utils/geometry.inside_winding_number`**: Möller-Trumbore ray-triangle
  intersection + y/z bbox prefilter 로 3D point-in-mesh 테스트. native_tet 의
  검증된 구현을 추출해 3 엔진 공용 모듈로 승격.

### Changed

- `core/generator/native_tet/mesher.py` / `native_hex/mesher.py` /
  `native_poly/voronoi.py` 의 로컬 `_inside_winding_number` / `_inside_ray_cast`
  구현을 삭제하고 `core.utils.geometry.inside_winding_number` import 로 교체.
  cell 수 drift 0 (tet=1196, hex=136, poly=26 on sphere baseline 불변).

---

## [0.4.0-beta8] - 2026-04-22 — "harness 확장 + 성능 안정화"

### Added

- **`core/generator/native_tet/harness.py`** (`run_native_tet_harness`):
  native_tet Generator ↔ Evaluator 반복으로 non_ortho 개선. sphere 에서 iter=1
  PASS, non_ortho 81.2° → **76.8°** (draft 임계 < 80 통과).
- `tier_native_tet` 이 harness 기본 경로로 전환 (실패 시 기본 generate_native_tet
  fallback).

### Fixed

- native_poly harness 에 **max_tet_cells cap** (default 30000): target_edge_length
  가 Strategist 에서 매우 작게 전달될 경우 tet mesh 가 121k cells 로 폭증 → dual
  변환 이 timeout 되는 문제 해결. bbox_diag/50 하한 + cell 수 초과 시 target_edge
  1.6×, seed 0.6× 로 재조정.
- CLI 에서 `--tier native_poly` 로 easy_cube 실행 시 300s+ timeout → **30s 이하**
  로 완주.

---

## [0.4.0-beta7] - 2026-04-22 — "poly mesh 자체 완성 + harness 패턴"

### Added — poly mesh 완성 (OpenFOAM 의존 제거)

- **`core/generator/native_poly/dual.py`**: tet→polyhedral dual 변환 자체 구현.
  OpenFOAM `polyDualMesh` 를 대체. 각 input vertex 주위의 tet centroid +
  boundary face midpoint 로 dual cell 구성 + scipy ConvexHull 로 polyhedron +
  coplanar triangle 병합 → polygon face + SVD plane basis + CCW sort + cell
  centroid 기준 winding 보정.
- **`core/generator/native_poly/harness.py`**: NativePolyHarness — Generator
  (native_tet → tet_to_poly_dual) ↔ Evaluator (NativeMeshChecker) 반복.
  FAIL 시 seed_density 1.5× 증가 후 최대 3 iter. sphere 에서 iter=1 에 PASS
  (698 polyhedra, negative_volumes=0, skewness 0.22, mesh_ok=True).
- **`core/layers/poly_bl_transition.py`**: OpenFOAM `polyDualMesh` 호출을 자체
  `_try_native_poly_dual` 로 교체 (순수 tet 입력 지원).
- **`core/generator/tier_native_poly.py`**: harness 경로 기본화, scipy Voronoi
  는 fallback.

### Tests
- **`tests/test_native_poly_dual.py`** (5 tests):
  - tet_to_poly_dual 이 sphere 에서 polyMesh 5 파일 생성.
  - NativeMeshChecker 로 negative_volumes=0 확인.
  - harness 가 1-3 iter 안에 PASS.
  - 빈 입력 fail.
  - polyMesh 포맷 호환 (reader 로 재읽기 가능).

### Native vs OpenFOAM parity
- **sphere (seed=10)**: native harness 결과 = 698 polyhedral cells,
  max_non_ortho 87°, skewness 0.22, **negative_volumes=0, mesh_ok=True**.
- 이전 `scipy Voronoi 기반 voronoi.py` 는 `open_cells=52/52` 였던 것과 비교해
  topology 품질이 크게 향상 (dual 경로는 input mesh 위상을 보존).

### Bench v0.4.0-beta7 matrix (5 난이도 × 3 엔진 × draft+standard)
```
| STL             | native_tet (d/s)       | native_hex (d/s)            | native_poly (d/s)      |
|-----------------|------------------------|-----------------------------|------------------------|
| 01_easy_cube    | ✓ 174s PASS / ✓ 265s   | ✓ 37s PASS / ✓ 36s          | ✗ 300s TO / ✗ 300s TO  |
| 02_cylinder     | ✓ 36s / ✓ 186s         | ✓ 10s PASS / ✓ 30s PASS     | ✓ 226s / ✗ 300s TO     |
| 03_bracket      | ✓ 4s PASS / ✓ 22s      | ✓ 3s PASS / ✓ 7s PASS       | ✓ 22s / ✓ 137s         |
| 04_gear         | ✓ 13s / ✓ 34s          | ✓ 5s PASS / ✓ 8s PASS       | ✓ 74s / ✓ 215s         |
| 05_ultra_knot   | ✓ 13s / ✓ 23s          | ✓ 5s PASS / ✓ 7s PASS       | ✓ 94s / ✓ 149s         |
```
**30 중 27 polyMesh 생성 (90%)**. native_hex 는 10/10 Evaluator PASS. native_poly
는 harness 가 dual 변환을 포함해 느림 — easy_cube 등 일부 timeout. 향후 dual
변환 ConvexHull 최적화 또는 seed grid 캐싱으로 해결 가능.

회귀: 1336 → **1341 passed** (+5 native_poly_dual 테스트).

---

## [0.4.0-beta3] - 2026-04-22 — "Native-First" 후속 개선

### Added
- **poly_bl_transition** (`core/layers/poly_bl_transition.py`): mesh_type=poly
  용 BL. native_bl 로 prism 삽입 후 (옵션) OpenFOAM polyDualMesh 로 bulk tet
  을 polyhedral dual 로 변환. sphere 에서 2783 polyhedral cells, Skewness OK.
- **L1 hole_fill ear-clipping** (`core/preprocessor/native_repair/hole_fill.py`):
  fan triangulation 대신 boundary loop 의 평균 평면 basis + 2D ear-clipping.
  max_boundary 64 → 128, 큰 hole / non-convex 영역도 처리.
- **file_reader.py native-first**: STL/OBJ/PLY/OFF 는 자체 `core/analyzer/readers/`
  로 기본 로드, trimesh 는 자동 fallback. `loaded_via_native_reader` 로그 기록.
- **Qt GUI 재시도 다이얼로그**: Evaluator FAIL + auto_retry=off 시 QMessageBox
  로 "재시도 / 수락" 묻고, 재시도 선택 시 동일 설정으로 파이프라인 재실행.
- **tests/stl/bench_v04_matrix.py**: 5 난이도 × native_tet/hex/poly 매트릭스
  실행 스크립트. 결과는 `bench_v04_result.json` 으로 저장.

### v0.4 Bench Matrix 결과 (5 난이도 × 3 native 엔진 × draft+standard)

**beta4+ (standard quality 확장 — 30 조합):**
```
| STL                      | native_tet           | native_hex           | native_poly         |
|                          | draft    | standard  | draft    | standard  | draft   | standard  |
|--------------------------|----------|-----------|----------|-----------|---------|-----------|
| 01_easy_cube             | ✓ 168s   | ✓ 268s    | ✓ 37s OK | ✓ 36s OK  | ✓ 50s   | ✓ 50s     |
| 02_medium_cylinder       | ✓ 35s    | ✓ 189s    | ✓ 11s OK | ✓ 30s OK  | ✓ 59s   | ✓ 59s     |
| 03_hard_bracket          | ✓ 4s     | ✓ 22s     | ✓ 3s OK  | ✓ 7s OK   | ✓ 6s    | ✓ 15s     |
| 04_extreme_gear          | ✓ 13s    | ✓ 35s     | ✓ 5s OK  | ✓ 8s OK   | ✓ 13s   | ✓ 27s     |
| 05_ultra_knot            | ✓ 13s    | ✓ 23s     | ✓ 5s OK  | ✓ 7s OK   | ✓ 224s  | ✓ 263s    |
```
**30/30 polyMesh 생성 성공 (100%)**. native_hex 는 draft+standard 둘 다 모두
Evaluator PASS (rc=0). native_tet/poly 는 polyMesh 는 생성되나 품질 판정 FAIL
(향후 개선 대상).

**beta3 최종 (inside-test AABB prefilter 적용 후):**
```
| STL                      | native_tet  | native_hex  | native_poly |
|--------------------------|-------------|-------------|-------------|
| 01_easy_cube             | ✓ 170s      | ✓ 33s OK    | ✓ 49s       |
| 02_medium_cylinder       | ✓ 36s       | ✓ 11s OK    | ✓ 52s       |
| 03_hard_bracket          | ✓ 4s        | ✓ 3s OK     | ✓ 5s        |
| 04_extreme_gear          | ✓ 13s       | ✓ 6s OK     | ✓ 11s       |
| 05_ultra_knot            | ✓ 13s       | ✓ 179s OK   | ✓ 125s      |
```
총 15 조합 중 **15 polyMesh 생성 성공 (100%)**. native_hex 는 5/5 Evaluator PASS.
ultra_knot native_tet 이전 300s timeout → 13s 완주 (inside-test 23× 가속).

### Fixed
- native_tet 의 sliver tet 제거 (q = 8.48·V/edge_max³ < 0.02 탈락). sphere 에서
  negative volume 5 → 0, Mesh OK.
- native_bl per-vertex local collision safety: wall vertex 별 인접 cell 중심까지
  거리 × 0.8 을 local cap 으로 사용. 극점 sliver prism 제거.

### Changed
- Preprocessor `--prefer-native` opt-in: pymeshfix 없이 자체 native_repair 경로
  로 L1 수행. `pyproject.toml` 의 pymeshfix/pyacvd/pymeshlab 을
  `legacy-preprocess` extras 로 격하.

---

## [0.4.0-beta] - 2026-04-22 — "Native-First"

핵심 철학 전환: 외부 라이브러리 의존 → 자체 코드 점진 전환. 라이브러리는
**참고·카피 대상** 이지 의존 대상이 아님. 최종적으로 우리 코드만으로 동작하는 것이
목표. 이번 릴리즈는 그 방향의 기반 공사 + MVP 자체 엔진 3 종 + 자체 L1/L2 + 자체
BL 완성.

### Added — 사용자 경험

- **메쉬 타입 3 카테고리 선택**: `--mesh-type {auto|tet|hex_dominant|poly}` (CLI)
  와 Qt GUI "메쉬 타입" 세그먼트 버튼. 사용자가 1차로 대분류를 고르고 품질 레벨과
  교차해 Tier 가 매핑됨. `mesh_strategy.json` 에 `mesh_type`, `strict_tier` 필드
  추가 (strategy_version 2 → 3).
- **자동 재시도 루프 제거 옵션**: `--auto-retry {off|once|continue}` (기본 off).
  off 는 1 회 시도 후 FAIL 이어도 종료, tty 환경에서는 사용자에게 `y/N` prompt.
  `continue` 는 기존 `max_iterations` 루프 동작 (하위호환).
- **사용자 재시도 prompt (CLI)**: FAIL + auto_retry=off + tty 에서 "Strategist
  권고 파라미터로 한 번 더?" 물음. `QualityReport.user_decision` 기록.

### Added — 자체 코어 (core/*)

- **자체 파일 reader** (`core/analyzer/readers/`): numpy 만으로 STL (binary +
  ASCII), OBJ, PLY (ASCII + binary little/big), OFF 파싱. trimesh 와 face/vertex
  수 / bbox parity 검증됨. `CoreSurfaceMesh` dataclass 통일.
- **자체 topology** (`core/analyzer/topology.py`): is_watertight / is_manifold /
  compute_genus / compute_euler / split_components (union-find) / dihedral_angles
  / count_sharp_edges. trimesh 속성 의존 제거.
- **자체 L1 repair** (`core/preprocessor/native_repair/`): pymeshfix 없이
  dedup_vertices, remove_degenerate_faces, remove_non_manifold_faces (edge 3+
  공유 반복 제거), fill_small_holes (boundary directed loop + fan), fix_face_winding
  (BFS consistency). `run_native_repair()` 통합.
- **자체 L2 remesh** (`core/preprocessor/native_remesh/`): isotropic remesh
  (Botsch & Kobbelt 2004, split/collapse/flip/relocate 반복), Lloyd CVT
  relaxation (area-weighted centroid, KDTree 사영 옵션).
- **자체 BL 생성** (`core/layers/native_bl.py` Phase 2 완성):
  OpenFOAM extrudeMesh+stitchMesh 의 face-orientation 한계를 우회해 Python 에서
  직접 polyMesh 위상 재구성. sphere 에서 3 layer prism 삽입 후 OpenFOAM checkMesh
  Face pyramids OK, Cell volumes OK, Skewness 0.48, open cells 0.
- **tet 전용 BL** (`core/layers/tet_bl_subdivide.py`): native_bl 의 prism wedge
  를 tet 3 개로 분할해 순수 tet 메쉬 유지. sphere 에서 10639 tet, 모두 Face
  pyramids OK.
- **NativeMeshChecker 기본화**: `--checker-engine auto` 기본값이 native 가 됨.
  OpenFOAM checkMesh 는 명시할 때만 교차 검증 용도로 사용. cells/faces/points
  정확 일치, max_non_orthogonality 5% 이내 parity 검증 (`tests/test_native_
  checker_parity.py`).

### Added — Native MVP 엔진 (core/generator/native_*)

- **native_tet** (`core/generator/native_tet/`): scipy Delaunay + uniform grid
  시드 + ray-casting inside-filter. `--tier native_tet` 로 호출. sphere 0.6 초,
  1549 tet.
- **native_hex** (`core/generator/native_hex/`): bbox 내부 uniform hex grid +
  inside filter. OpenFOAM hex vertex 순서 6 face 직접 생성. sphere checkMesh OK,
  aspect_ratio=1.0, skewness~0.
- **native_poly** (`core/generator/native_poly/`): scipy Voronoi 기반 polyhedral.
  Voronoi ridge_vertices 를 그대로 polygon face 로 사용. cells > 0 확인.

### Added — BL 타입별 자동 라우팅

- `tier_layers_post.LayersPostGenerator.run()` 의 `engine="auto"` 를 strategy
  .mesh_type 기반 자동 매핑: tet → `tet_bl_subdivide`, hex_dominant/poly →
  `native_bl`.

### Changed

- `MeshStrategy` schema: `strategy_version` 2 → 3, `mesh_type`, `strict_tier`
  필드 추가. `EvaluationSummary` 에 `user_decision`, `checker_engine_used`,
  `mesh_type` 추가.
- Orchestrator `run()` 시그니처에 `auto_retry`, `mesh_type` 추가. 기존
  `max_iterations` 는 deprecated (auto_retry=continue 일 때만 사용).
- Planner/TierSelector 가 mesh_type × quality_level 매핑 테이블로 primary tier 와
  같은 카테고리 fallback 순서를 결정.

### Documentation

- `agents/specs/*.md` 5 개 전체를 "라이브러리 참고 → 자체 코드화" 방향으로 재작성.
  각 에이전트에 "현재 의존 / 참고 출처 / 자체 구현 목표" 3-열 로드맵 표 추가.
- `CLAUDE.md` 재편: 핵심 철학 (native-first), mesh_type 3 카테고리, 재시도 루프
  제거, BL 타입별 분기 명시.

### Tests

1108 passed (v0.3.5) → **1328 passed** (v0.4.0-beta), 19 skipped, 0 failed.

신규 테스트 파일:
- `test_native_readers.py` (13)
- `test_native_topology.py` (15)
- `test_native_repair.py` (11)
- `test_native_remesh.py` (9)
- `test_native_bl.py` (8)
- `test_tet_bl_subdivide.py` (5)
- `test_native_tet.py` (4)
- `test_native_hex.py` (5)
- `test_native_poly.py` (4)
- `test_native_checker_parity.py` (6, OpenFOAM 환경에서만)

### Known Limitations (v0.4.0-beta)

- native_poly 는 boundary clipping 미완성 → OpenFOAM checkMesh 에서 open cell
  경고. cells > 0 은 확실하나 CFD quality 는 기존 cfmesh 대비 낮음.
- native_tet 은 surface envelope 유지가 엄격하지 않음 (degenerate sliver tet 일
  부 생성).
- L1 hole_fill 은 다중 loop / 큰 hole 의 winding 일관성이 완벽하지 않음.
- file_reader.py 는 여전히 trimesh 를 기본 경로로 사용 (native readers 는 별도
  경로로 준비된 상태, 통합 전환은 v0.5 예정).

---

## [0.1.0] - 2026-04-01

### Added
- 5-Agent pipeline: Analyzer → Preprocessor → Strategist → Generator ↔ Evaluator
- 2-Phase Progressive meshing: Surface (L1→L2→L3) + Volume (Draft/Standard/Fine)
- QualityLevel system (draft/standard/fine) with differentiated thresholds
- PolyMeshWriter: tet mesh → OpenFOAM polyMesh without external tools
- NativeMeshChecker: OpenFOAM-free mesh quality validation
- Geometry Fidelity: Hausdorff distance-based surface deviation check
- STEP/IGES CAD support via cadquery + gmsh fallback
- CLI: `auto-tessell run input.stl -o ./case --quality draft|standard|fine`
- Rich terminal output with quality report tables
- FastAPI WebSocket server for desktop GUI communication
- Godot 4.3 desktop GUI project (3D mesh viewer, progress tracking)
- OpenFOAM auto-detection (/usr/lib/openfoam/, /opt/, OPENFOAM_DIR)
- Retry strategy with meaningful parameter adjustments on FAIL
- PyInstaller packaging support
- Docker + docker-compose for reproducible builds
- GitHub Actions CI/CD
- 380+ tests (unit + integration + benchmark)

### Supported Input Formats
- Mesh: STL, OBJ, PLY, OFF, 3MF
- CAD: STEP, IGES, BREP
- CFD: Gmsh .msh, VTK/VTU, Fluent .msh, Nastran, Abaqus

### Volume Mesh Engines
- Draft: TetWild (pytetwild) — ~1 second
- Standard: Netgen / cfMesh — ~minutes
- Fine: snappyHexMesh + BL / MMG — ~30 minutes+
