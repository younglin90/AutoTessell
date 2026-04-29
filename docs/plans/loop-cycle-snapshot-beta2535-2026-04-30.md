# /loop 자동 고도화 사이클 — 스냅샷 (2026-04-30, beta2535)

## 세션 통계

**192 카드** (beta2367-beta2535) 완료. 본 스냅샷은 beta2527-2535 (9 카드).

## 추가 카드 (beta2527-2535)

| beta | 모듈 | 변경 |
|------|------|------|
| 2527 | laplacian.py vert_neighbors | 두 set-build → lexsort + group + dedup |
| 2528 | insertion.py find_missing_triangles | set[tuple] + Python loop → packed int + np.isin |
| 2529 | validate.py affected gather | nested ti × 4-vert → tets[bad].ravel() |
| 2530 | anisotropic.py curvature_aligned_metric | per-vert Gram-Schmidt → batched einsum + 3D matmul |
| 2531 | poly quality.py UF roots | [_find for i in range(n)] → path-doubling |
| 2532 | isotropic.py valence | nested f×v Python → np.bincount |
| 2533 | filter.py covered gather | nested kept × 4-vert → boolean indexing |
| 2534 | bowyer_watson.py cavity boundary | dict[tuple] + Python loop → packed int + unique count |
| 2535 | sliver_merge.py remap+degenerate | (a) [_find for x in flat] → path-doubling, (b) [len(set(row))==3] → sorted-row dup-mask |

## 누적 효과 (beta2367 → beta2535)

| 영역 | 시작 | 현재 | 개선 |
|------|------|------|------|
| **벡터화 모듈 합계** | — | **73** | hot-loops 제거 |

## 73 벡터화 모듈 (분류, 누적)

### Tet algorithm (32, +4)
- 기존 28 (CVT3D, Stellar 4 sites, AMIPS CSR, TetAdjacency 3 dicts, bowyer_watson nbrs, cavity_retri v2t, chunked _chunk_bounds, cdt_check (3), cdt_recovery surface_edges, anisotropic vertex normal, laplacian (face_owners, bad faces), face_recovery face_set, features edge_tri, input_check edge topology, surface_conformal (2), local_ops v2t, flip.py (3), mesher (2), sliver_merge edge_map, plane_coverage)
- **+laplacian.py vert_neighbors (×2 sites)** beta2527
- **+insertion.py find_missing_triangles** beta2528
- **+validate.py affected gather** beta2529
- **+anisotropic curvature_aligned_metric** beta2530
- **+filter.py covered gather** beta2533
- **+bowyer_watson cavity_boundary** beta2534
- **+sliver_merge remap + degenerate** beta2535

### Poly algorithm (4, +1)
- 기존 3 (aniso_cvt 곡률+Lloyd inner ×2, voronoi edge_to_faces)
- **+quality.py UF path-doubling** beta2531

### Hex algorithm (9, 변동 없음)

### BL algorithm (5, 변동 없음)

### Preprocessor (9, +1)
- 기존 8 (quadric_decimate ×3, native_remesh ×3, native_repair ×2, Möller fix)
- **+isotropic valence bincount** beta2532

### Analyzer / utilities (5, 변동 없음)

## 사용 패턴 빈도 (총 73)

- **lexsort + group-boundary**: 25 (+1 — vert_neighbors)
- **packed-key np.unique / np.isin**: 12 (+2 — find_missing, BW cavity)
- **flat sort + bincount-offset / bincount**: 14 (+1 — isotropic valence)
- **np.add.at scatter**: 8
- **broadcast 3D ops / matmul**: 7 (+2 — Gram-Schmidt, einsum)
- **np.minimum.at scatter-min**: 1
- **path-doubling (UF)**: 3 (+2 — poly quality, sliver_merge)
- **boolean / fancy indexing**: 2 (+2 — validate, filter affected/covered)
- **np.indices**: 1
- **single fwrite (I/O)**: 1
- **sorted-row dup mask**: 1 (+1 — sliver_merge degenerate)

## 회귀 status (beta2535)

- 75 broader regression (cvt3d / SI / hex / poly / phaseB / amips / cdt / chunked).
- 154+ broader regression (확장 시).
- 22 cli_flags tests.
- 234 GUI tests.
- 67 cvt3d_aniso_cvt.

## 결론

이번 9-card batch (beta2527-2535) 는 saturation 후 발견한 잔여 hot-loop 들에 대한 "deep saturation recovery" 사이클이다.

**73 hot-loop 벡터화 누적** (60+ 사이트). 6개 표준 패턴 적용.

Cycle 219 부터 saturation 진입 후, cycle 220+ 부터 conservative scan 으로 9개 추가 hot-loop 발견 (laplacian 두 vert_neighbors, insertion find_missing, validate affected gather, anisotropic Gram-Schmidt, poly quality UF, isotropic valence, filter covered, BW cavity boundary, sliver_merge dual). 모두 numerical equivalence 검증 + 31~75 regression PASS.

남은 commercial parity 격차 (변동 없음):
- BL aspect 11.5k → 1k: cumulative cascading scale 의 mathematical 한계
- tet quality D → C: Klingner §4 swap-based sliver removal 알고리즘 추가 필요

이는 algorithmic redesign 또는 C++/CUDA path 가 필요한 작업.

## 남은 candidate (vectorization, low priority)

다음의 loop 들은 검토 후 아래 사유로 보류:
- `face_recovery.py:84` — `n_rec` branch 가 dead code (face_set construction 과 등가) — 정정은 correctness 영역
- `cdt_recovery.py:143`, `mesher.py:771,878` — 순차 알고리즘
- `dual.py:311`, `voronoi.py:319/456` — variable-length face fan triangulation
- `octree.py:340-342,515,743` — 계층적 templating, side-effects
- `kdtree.py:203` — expanding-radius cell search
- `predicates_staged.py:237` — exact arithmetic with Fractions
- `hole_fill.py:133` — ear-clipping with mutable polygon
- `normals.py:48` — flood-fill BFS
- `geometry.py:61/126` — 이미 batched memory bounds
- `flip.py:5/7-iter dim loops` — 너무 작음
