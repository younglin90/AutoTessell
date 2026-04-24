# `core/generator/native_tet/` — TetWild-lite

AutoTessell 의 자체 tetrahedral mesh generator. fTetWild (Hu et al. 2020,
MPL-2.0) 및 TetGen (Si 2015) 핵심 알고리즘을 Python 으로 독립 재구현.

## 모듈 구성

| 모듈 | 역할 | 주요 함수 |
|------|------|----------|
| `mesher.py` | 진입점 + 파이프라인 | `generate_native_tet` |
| `harness.py` | quality-aware 반복 + 재시도 | `run_native_tet_harness` |
| `features.py` | Sharp edge / corner 검출 (dihedral) | `detect_features` |
| `filter.py` | Boundary-aware sliver filter | `filter_slivers` |
| `insertion.py` | Missing triangle barycenter recovery | `find_missing_triangles`, `recovery_seeds` |
| `bsp_insert.py` | BSP constrained triangle insertion | `bsp_insert_triangles` |
| `smooth.py` | Laplacian + tangent-plane smoothing (벡터화) | `smooth_interior`, `smooth_tangent_surface` |
| `surface_snap.py` | BVH 기반 surface projection | `snap_surface_vertices` |
| `adjacency.py` | face / edge / vertex → tet 맵 | `TetAdjacency` |
| `local_ops.py` | Edge split / collapse / orphan cleanup | `split_long_edges`, `collapse_short_edges`, `compact_unused_vertices` |
| `flip.py` | 2-3 / 3-2 face/edge flip | `flip_faces_23`, `flip_edges_32`, `face_flip_pass` |
| `envelope.py` | ε-envelope surface preservation | `Envelope.build`, `check_operation` |
| `quality.py` | Per-tet shape quality + stop criterion | `tet_shape_quality`, `snapshot`, `should_stop` |
| `adaptive.py` | Curvature 기반 per-vertex target edge | `curvature_sizing` |
| `validate.py` | Inverted / degenerate tet 검출 + swap 복구 | `fix_inverted_tets`, `orientation_signs` |
| `input_check.py` | 입력 surface pre-check (duplicate / zero-area / non-watertight) | `check_input` |
| `bowyer_watson.py` | Incremental Delaunay insertion (cavity 방식) | `bowyer_watson_insert`, `_in_circumsphere` |
| `anisotropic.py` | Per-vertex SPD metric tensor (axis / curvature) | `axis_aligned_metric`, `curvature_aligned_metric`, `edge_length_metric` |

추가:
- `core/utils/aabb.py` — AABB BVH (closest-point / envelope query 공통).
- `core/utils/predicates.py` — tolerance 기반 orient3d / insphere.
- `core/utils/predicates_exact.py` — Python fractions.Fraction 기반 exact-sign
  orient3d / insphere + robust fallback.
- `core/utils/predicates_staged.py` — 3 단계 staged (double → float128 →
  Fraction) orient3d. 평균 double 속도, 불확실 케이스만 exact drop.

## Phase 분류

| Phase | 기능 | 기본 활성 |
|-------|------|-----------|
| A | Feature detect + recovery + boundary sliver + smoothing | `enable_phase_a=True` |
| B | Local ops (split/collapse/flip) + tangent smoothing | `enable_phase_b=False` (opt-in) |
| C | Envelope + snap + quality stop | `enable_phase_c=False` |
| F | BSP constrained insertion (fallback) | `enable_bsp_insertion=False` |

## Quality preset (HARNESS_PARAMS)

| Quality | Phases | 추가 설정 |
|---------|--------|-----------|
| draft | A | 빠름, seed_density=10 |
| standard | A + B | local_ops_iterations=1 |
| fine | A + B + C | envelope_eps=1%, adaptive sizing, 2× iteration |

CLI/GUI 에서 `--quality fine` 선택 시 harness 가 자동 주입.

## 주요 파라미터

- `target_edge_length` / `target_cells`: 절대 edge 길이 또는 목표 cell 수 중 택1.
- `feature_angle_deg` (기본 30): dihedral fold > 이 각도면 feature.
- `sliver_quality_threshold`: interior sliver 컷오프 (기본 0.05).
- `envelope_eps_relative`: bbox 대각선 대비 envelope 폭 (기본 0.1%, fine 에서 1%).
- `max_collapses_per_iter` (200), `cell_drop_rollback_ratio` (0.5): 안전판.

## 벤치 (5 STL)

| STL | Phase A | Phase A+B+C (fine) |
|-----|---------|---------------------|
| cube | 0.03s, q=0.31 | 0.08s, q=0.28 |
| cylinder | 0.42s, q=0.09 | 1.3s, q=0.10 |
| bracket | 0.22s, q=0.05 | 0.5s, q=0.06 |
| gear | 0.73s, q=0.14 | 3.4s, q=0.15 |
| knot | 7.4s, q=0.13 | 213s, q=0.13 |

`tests/stl/native_tet_bench_latest.json`, `native_tet_bench_phaseB.json`.

## 라이선스

fTetWild (Hu et al. 2020, MPL-2.0) §3 의 알고리즘 — triangle insertion,
envelope, edge flip, feature preservation — 아이디어와 논문을 참고해
Python 으로 독립 재구현. 원본 C++ 코드를 복제하지 않았으며, 각 모듈
docstring 에 출처를 명시한다. 부가 참조: TetGen (Si 2015), Shewchuk 1998
predicates, Botsch et al. 2010 mesh processing, Ericson 2005 collision
detection.

## 남은 작업 (향후 rounds)

- **Thingi10k 실제 다운로드 벤치**: 현재는 procedural 12 STL 로 대체.
- **Surface snap 과 B-W insertion 결합**: 이미 BSP → B-W recovery 파이프라인은
  연결됐으나, B-W 이후 envelope snap 을 한 번 더 돌리면 Hausdorff 오차 감소.
- **Conformal CDT (SI 2015 TetGen §4)**: 현 BSP + B-W 는 recovery 를 근사하지만
  PLC 의 edge constraint 를 엄격히 보장하지 않음.

## 완료된 주요 기능 (beta110 → beta450)

- Phase A/B/C/F 전체 파이프라인.
- Edge split / collapse / flip (2-3, 3-2, 4-4).
- BVH (AABB) closest-point + envelope preservation.
- Feature edge / corner detection + lock.
- Curvature-adaptive scalar sizing + anisotropic tensor metric.
- Tolerance + exact-rational predicates.
- Bowyer-Watson incremental insertion.
- Input pre-check (duplicate / zero-area / non-watertight / non-manifold /
  self-intersection heuristic).
- Inverted tet validator + orphan vertex cleanup + cell-drop rollback.
- Progress callback + large-mesh auto-conservative.
- HARNESS_PARAMS quality 자동 Phase B/C 주입.
- target_cells heuristic + target_edge_length 파라미터화.

## 누적 개발 이력 (beta110 → beta380)

28 rounds, ~3,500 LoC, 94 tests (88 non-slow + 6 predicates). 주요 마일스톤:

- beta110 Phase A: feature + filter + recovery + smoothing.
- beta120 Phase B: split / collapse / flip.
- beta125 Phase C: envelope + quality stop.
- beta130: vectorized smoothing + BVH snap.
- beta140: 3-2 flip + adaptive.
- beta160: BSP constrained insertion.
- beta170: feature lock + adversarial bench.
- beta190: 5-STL bench 5/5 success.
- beta200: inverted tet validator.
- beta220: collapse cap + rollback (cell 붕괴 해소).
- beta240–280: edge length / split / collapse / flip numpy 벡터화.
- beta300: BVH batch + boundary cache.
- beta310: HARNESS_PARAMS quality 자동 주입.
- beta320–330: orphan cleanup + target_cells heuristic.
- beta350–360: tolerance predicates.
- beta370: smoothing quality guard (opt-in).
- beta380: large-mesh 자동 보수화.
- beta400: 4-4 edge flip.
- beta410: progress_cb + 4-4 flip tests.
- beta420: input pre-check (duplicate / zero-area / non-watertight / non-manifold).
- beta440: AABB self-intersection heuristic.
- beta450: Rounds 35-38 — Bowyer-Watson · exact predicates · anisotropic
  metric · procedural bench matrix.
- beta470: shared-stack BVH.
- beta480: B-W wired as BSP recovery fallback.
- beta490-500: metric-aware split/collapse + mesher wire.
- beta510-540: staged predicates (double→float128→Fraction).
- beta560: snap-after-BW.
- beta570-590: CDT edge-recovery check + midpoint insertion pipeline.
- beta600-610: subdivision mode + revert guard.
- beta630: enable_edge_recovery flag + fine preset auto-enable.
- beta640: __init__ docstring update.

### 55 rounds 완료 기준 테스트 현황

129 passed (non-slow) + 1 slow (5-STL Phase B 비교 bench). 전체 모듈
테스트 커버리지:
  test_native_tet / harness / phaseA / B / C / D / E / F / G / J / bench
  + test_predicates / _exact / _staged
  + test_bowyer_watson / anisotropic / cdt_check / edge_recovery
  + test_native_tet_input_check / matrix_bench.
