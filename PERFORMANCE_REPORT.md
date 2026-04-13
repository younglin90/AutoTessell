# AutoTessell 성능 벤치마킹 리포트
생성 시간: 2026-04-13T11:39:11Z
테스트 케이스: 26개

---
## 📌 메타데이터
- **Suite ID**: `9d3c5152-ac73-4137-bfb9-7cc76897da60`
- **Git Commit**: `9ab7128` (master)
- **Dirty**: ⚠ Yes
- **Quality Level**: `draft`
- **Timeout**: `600s`

---
## 📊 요약
| 상태 | 개수 |
|------|------|
| ✅ 성공 | 24 |
| ❌ 실패 | 2 |
| ⏱ 타임아웃 | 0 |
| ⚠ 오류 | 0 |

## ⏱ 실행 시간 통계 (성공한 경우)
| 지표 | 값 |
|------|-----|
| 최소 | 4.07s |
| 최대 | 137.02s |
| 평균 | 22.16s |
| 중앙값 | 7.61s |

## 📋 상세 결과
| 테스트 케이스 | 상태 | 시간 | 셀 수 | Mesh OK |
|---|---|---|---|---|
| broken_sphere.stl | ✅ | 52.97s | — | ✓ |
| coarse_to_fine_gradation_two_spheres.stl | ✅ | 6.46s | — | ✓ |
| cylinder.stl | ✅ | 5.30s | — | ✓ |
| degenerate_faces_sliver_triangles.stl | ✅ | 6.43s | — | ✓ |
| external_flow_isolated_box.stl | ✅ | 5.17s | — | ✓ |
| extreme_aspect_ratio_needle.stl | ✅ | 19.53s | — | ✗ |
| five_disconnected_spheres.stl | ✅ | 48.78s | — | ✓ |
| hemisphere_open.stl | ✅ | 137.02s | — | ✓ |
| hemisphere_open_partial.stl | ✅ | 35.99s | — | ✓ |
| high_genus_dual_torus.stl | ✅ | 57.12s | — | ✓ |
| highly_skewed_mesh_flat_triangles.stl | ✅ | 7.59s | — | ✗ |
| large_mesh_250k_faces.stl | ✅ | 12.12s | — | ✓ |
| many_small_features_perforated_plate.stl | ✅ | 5.66s | — | ✓ |
| mixed_features_wing_with_spike.stl | ✅ | 7.64s | — | ✗ |
| mixed_watertight_and_open.stl | ✅ | 34.67s | — | ✓ |
| multi_scale_sphere_with_micro_spikes.stl | ✅ | 4.54s | — | ✓ |
| naca0012.stl | ✅ | 22.71s | — | ✓ |
| nonmanifold_disconnected.stl | ❌ | 14.45s | — | ✗ |
| | Error: 2026-04-13T11:47:46.951947Z [info     ] retry_poli... | | | |
| self_intersecting_crossed_planes.stl | ❌ | 1.81s | — | ✗ |
| | Error: 2026-04-13T11:48:01.365320Z [info     ] retry_poli... | | | |
| sharp_features_micro_ridge.stl | ✅ | 7.36s | — | ✓ |
| sphere.stl | ✅ | 4.07s | — | ✓ |
| sphere_20k.stl | ✅ | 9.10s | — | ✓ |
| sphere_watertight.stl | ✅ | 4.11s | — | ✓ |
| trimesh_box.stl | ✅ | 6.50s | — | ✓ |
| trimesh_duct.stl | ✅ | 5.26s | — | ✓ |
| very_thin_disk_0_01mm.stl | ✅ | 25.85s | — | ✓ |
