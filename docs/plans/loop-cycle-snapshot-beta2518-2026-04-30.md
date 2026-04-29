# /loop 자동 고도화 사이클 — 스냅샷 (2026-04-30, beta2518)

## 세션 통계

**165 카드** (beta2367 - beta2518) 완료. 본 스냅샷은 beta2515-2518 (4 카드).

## 최근 카드 (beta2515-2518)

| beta | 모듈 | 변경 |
|------|------|------|
| 2515 | flip.py face_map fallback | lexsort + group-boundary |
| 2516 | flip.py edge_map fallback | lexsort + group-boundary |
| 2517 | native_bl _curvature_adaptive neighbours | triangle fast path + scatter |
| 2518 | native_bl _relative_first_thickness | triangle fast path + scatter |

## 누적 효과 (beta2367 → beta2518)

| 영역 | 시작 | 현재 | 개선 |
|------|------|------|------|
| **tet 셀 수 (mesh #1)** | 2 | 1453 | 726× 회복 |
| **BL aspect (mesh #1)** | 580k | 11.5k | 50× 감소 |
| **BL prism (mesh #1)** | 0 (ex) | 4287 | 완전 회복 |
| **CLI flags 신규** | — | 11 | 100% env→CLI parity |
| **GUI 위젯 신규** | — | 7 | full GUI parity |
| **벡터화 모듈** | — | **56** | hot-loops 제거 |

## 56 개 벡터화 모듈 (누적 분류)

### Tet 알고리즘 (24)
1. CVT3D Lloyd inner loop
2. Stellar split monotone (`_tet_quality_batch`)
3. Stellar SLIM Newton vert_min_q (np.minimum.at)
4. Stellar edge_incident_cache
5. Stellar face_incident_cache
6. AMIPS CSR 1-ring (2 sites)
7. TetAdjacency.build (3 dicts)
8. bowyer_watson _tet_neighbors
9. cavity_retri v2t
10. chunked _chunk_bounds (np.indices)
11. cdt_check _tet_triangles, _tet_edges
12. cdt_check 2× check_edge_recovery
13. cdt_recovery _surface_edge_set
14. anisotropic vertex normal scatter
15. laplacian face_owners
16. laplacian bad faces dedup
17. face_recovery face_set
18. features edge_tri
19. input_check edge topology
20. surface_conformal 2× faces sets
21. local_ops v2t
22. flip.py face_map fallback
23. flip.py edge_map fallback
24. mesher vertex normal + Laplacian

### Poly 알고리즘 (2)
25. aniso_cvt _surface_principal_curvatures
26. aniso_cvt aniso_cvt_seeds (KDTree batch)

### Hex 알고리즘 (8)
27. snap _detect_surface_feature_vertices
28. snap _build_vertex_neighbors_from_triangles
29. snap snap_to_feature_edges vert_cells
30. mesher face_map + boundary_verts
31. mesher edge_nbrs
32. mesher boundary triangulation
33. mesher _validate_hex bulk volume
34. (이전) snap edge_map vectorized + KD-tree pre-filter

### BL 알고리즘 (3)
35. native_bl _detect_feature_vertices
36. native_bl _curvature_adaptive_thickness neighbours
37. native_bl _relative_first_thickness neighbours

### Preprocessor (8)
38. quadric_decimate _vertex_quadrics
39. quadric_decimate _enumerate_edges + _build_v2f
40. native_remesh _detect_self_intersections AABB pre-filter
41. native_remesh face_split UUU7 Laplacian adjacency
42. native_remesh isotropic feature detect
43. native_remesh isotropic _build_edge_map
44. native_repair _aabb_overlap_pairs
45. native_repair KDTree+AABB filter

### Analyzer / utilities (3)
46. topology.split_components UF path-doubling
47. geometry.inside_winding_number
48. geometry.inside_generalized_winding_number

## 회귀 status (beta2518)

- **154 passed** broader regression (cvt3d / aniso_cvt / SI / inside / hex / poly /
  cdt_recovery / amips / phaseB / chunked).
- **22 cli_flags** tests pass.
- **234 GUI** tests (test_qt_app).

## 결론

이번 4-card batch (beta2515-2518) 는 **flip.py fallback paths + BL triangle-only
fast paths**.

**56 hot-loop 벡터화 누적**. 남은 loops 는 대부분:
- variable-length polyhedron faces (poly cells, openFOAM polyMesh I/O)
- sequential algorithm logic (BFS/DFS traversal, edge-collapse updates,
  iterative repair)
- BVH/octree traversal (inherently sequential)

**벡터화 가능한 hot-loop saturation 완료**. 추가 진전은:
- algorithmic 진화 (Klingner §4 swap-based sliver removal, BL per-vertex aspect cap)
- C++/Cython 확장 (이미 일부 native_tet 에 존재 — `_native/`)
- GPU CUDA path (multi-month 계획)
가 필요.
