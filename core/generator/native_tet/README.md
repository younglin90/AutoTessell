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
| `validate.py` | Inverted / degenerate tet 검출 + swap 복구 | `fix_inverted_tets` |

추가: `core/utils/aabb.py` — AABB BVH (closest-point / envelope query 공통).

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

- Robust floating-point predicates (Shewchuk) — 수치 안정.
- 4-4 edge flip.
- Full-batch BVH traversal (현재는 per-point stack).
- Thingi10k 규모 (1000+ STL) 자동 벤치.
- Anisotropic sizing tensor.
