# AutoTessell 성능 벤치마킹 리포트
생성 시간: 2026-04-13T12:48:30Z
테스트 케이스: 26개

---
## 📌 메타데이터
- **Suite ID**: `a2fdf4e3-19ba-4f79-a177-d22eb98bdd78`
- **Git Commit**: `5a14def` (master)
- **Dirty**: ✓ No
- **Quality Level**: `draft`
- **Timeout**: `600s`

---
## 📊 요약
| 상태 | 개수 |
|------|------|
| ✅ 성공 | 23 |
| ❌ 실패 | 3 |
| ⏱ 타임아웃 | 0 |
| ⚠ 오류 | 0 |

## ⏱ 실행 시간 통계 (성공한 경우)
| 지표 | 값 |
|------|-----|
| 최소 | 3.97s |
| 최대 | 53.92s |
| 평균 | 17.97s |
| 중앙값 | 6.91s |

## 📋 상세 결과
| 테스트 케이스 | 상태 | 시간 | 셀 수 | Mesh OK |
|---|---|---|---|---|
| broken_sphere.stl | ✅ | 47.27s | — | ✓ |
| coarse_to_fine_gradation_two_spheres.stl | ✅ | 5.58s | — | ✓ |
| cylinder.stl | ✅ | 4.67s | — | ✓ |
| degenerate_faces_sliver_triangles.stl | ✅ | 5.64s | — | ✓ |
| external_flow_isolated_box.stl | ✅ | 4.61s | — | ✓ |
| extreme_aspect_ratio_needle.stl | ✅ | 17.63s | — | ✗ |
| five_disconnected_spheres.stl | ✅ | 45.94s | — | ✓ |
| hemisphere_open.stl | ✅ | 43.92s | — | ✓ |
| hemisphere_open_partial.stl | ✅ | 38.72s | — | ✓ |
| high_genus_dual_torus.stl | ✅ | 53.92s | — | ✓ |
| highly_skewed_mesh_flat_triangles.stl | ✅ | 6.91s | — | ✗ |
| large_mesh_250k_faces.stl | ✅ | 9.90s | — | ✓ |
| many_small_features_perforated_plate.stl | ✅ | 5.41s | — | ✗ |
| mixed_features_wing_with_spike.stl | ❌ | 6.20s | — | ✗ |
| | Error: 2026-04-13T12:53:48.094156Z [info     ] retry_poli... | | | |
| mixed_watertight_and_open.stl | ✅ | 42.94s | — | ✓ |
| multi_scale_sphere_with_micro_spikes.stl | ✅ | 4.05s | — | ✓ |
| naca0012.stl | ✅ | 19.99s | — | ✓ |
| nonmanifold_disconnected.stl | ❌ | 13.96s | — | ✗ |
| | Error: 2026-04-13T12:55:04.339764Z [info     ] retry_poli... | | | |
| self_intersecting_crossed_planes.stl | ❌ | 1.93s | — | ✗ |
| | Error: 2026-04-13T12:55:22.589588Z [info     ] retry_poli... | | | |
| sharp_features_micro_ridge.stl | ✅ | 6.64s | — | ✗ |
| sphere.stl | ✅ | 3.99s | — | ✓ |
| sphere_20k.stl | ✅ | 9.27s | — | ✓ |
| sphere_watertight.stl | ✅ | 3.97s | — | ✓ |
| trimesh_box.stl | ✅ | 4.42s | — | ✓ |
| trimesh_duct.stl | ✅ | 5.08s | — | ✓ |
| very_thin_disk_0_01mm.stl | ✅ | 22.94s | — | ✓ |
