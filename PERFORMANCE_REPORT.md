# AutoTessell 성능 벤치마킹 리포트
생성 시간: 2026-04-13T10:01:32Z
테스트 케이스: 26개

---
## 📌 메타데이터
- **Suite ID**: `462c0f1c-aa1a-40df-ba07-4797fbe77ae8`
- **Git Commit**: `8f38efe` (master)
- **Dirty**: ⚠ Yes
- **Quality Level**: `draft`
- **Timeout**: `600s`

---
## 📊 요약
| 상태 | 개수 |
|------|------|
| ✅ 성공 | 20 |
| ❌ 실패 | 6 |
| ⏱ 타임아웃 | 0 |
| ⚠ 오류 | 0 |

## ⏱ 실행 시간 통계 (성공한 경우)
| 지표 | 값 |
|------|-----|
| 최소 | 3.79s |
| 최대 | 53.38s |
| 평균 | 19.44s |
| 중앙값 | 7.67s |

## 📋 상세 결과
| 테스트 케이스 | 상태 | 시간 | 셀 수 | Mesh OK |
|---|---|---|---|---|
| broken_sphere.stl | ✅ | 53.38s | — | ✓ |
| coarse_to_fine_gradation_two_spheres.stl | ✅ | 6.01s | — | ✓ |
| cylinder.stl | ✅ | 5.03s | — | ✓ |
| degenerate_faces_sliver_triangles.stl | ✅ | 5.89s | — | ✓ |
| external_flow_isolated_box.stl | ✅ | 4.71s | — | ✓ |
| extreme_aspect_ratio_needle.stl | ❌ | 43.60s | — | ✗ |
| | Error: 2026-04-13T10:02:55.253119Z [info     ] retry_poli... | | | |
| five_disconnected_spheres.stl | ✅ | 46.21s | — | ✓ |
| hemisphere_open.stl | ✅ | 45.06s | — | ✓ |
| hemisphere_open_partial.stl | ✅ | 39.54s | — | ✓ |
| high_genus_dual_torus.stl | ✅ | 53.31s | — | ✓ |
| highly_skewed_mesh_flat_triangles.stl | ❌ | 11.09s | — | ✗ |
| | Error: 2026-04-13T10:06:59.235648Z [info     ] retry_poli... | | | |
| large_mesh_250k_faces.stl | ✅ | 10.59s | — | ✓ |
| many_small_features_perforated_plate.stl | ✅ | 5.47s | — | ✓ |
| mixed_features_wing_with_spike.stl | ❌ | 6.07s | — | ✗ |
| | Error: 2026-04-13T10:07:28.859078Z [info     ] retry_poli... | | | |
| mixed_watertight_and_open.stl | ✅ | 40.39s | — | ✓ |
| multi_scale_sphere_with_micro_spikes.stl | ✅ | 4.02s | — | ✓ |
| naca0012.stl | ✅ | 19.58s | — | ✓ |
| nonmanifold_disconnected.stl | ❌ | 17.82s | — | ✗ |
| | Error: 2026-04-13T10:08:44.449320Z [info     ] retry_poli... | | | |
| self_intersecting_crossed_planes.stl | ❌ | 1.77s | — | ✗ |
| | Error: 2026-04-13T10:09:03.573196Z [info     ] retry_poli... | | | |
| sharp_features_micro_ridge.stl | ❌ | 10.61s | — | ✗ |
| | Error: 2026-04-13T10:09:05.334077Z [info     ] retry_poli... | | | |
| sphere.stl | ✅ | 3.79s | — | ✓ |
| sphere_20k.stl | ✅ | 8.75s | — | ✓ |
| sphere_watertight.stl | ✅ | 3.83s | — | ✓ |
| trimesh_box.stl | ✅ | 6.59s | — | ✓ |
| trimesh_duct.stl | ✅ | 4.48s | — | ✓ |
| very_thin_disk_0_01mm.stl | ✅ | 22.19s | — | ✓ |
