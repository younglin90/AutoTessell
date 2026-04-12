# AutoTessell 성능 벤치마킹 리포트
생성 시간: 2026-04-12 20:49:36
테스트 케이스: 26개

---
## 📊 요약
| 상태 | 개수 |
|------|------|
| ✅ 성공 | 15 |
| ❌ 실패 | 10 |
| ⏱ 타임아웃 | 1 |
| ⚠ 오류 | 0 |

## ⏱ 실행 시간 통계 (성공한 경우)
| 지표 | 값 |
|------|-----|
| 최소 | 3.80s |
| 최대 | 342.83s |
| 평균 | 50.20s |
| 중앙값 | 5.18s |

## 📋 상세 결과
| 테스트 케이스 | 상태 | 시간 | 셀 수 | Mesh OK |
|---|---|---|---|---|
| broken_sphere.stl | ❌ | 220.62s | — | ✗ |
| | Error: 2026-04-12T10:59:10.269311Z [info     ] retry_poli... | | | |
| coarse_to_fine_gradation_two_spheres.stl | ✅ | 5.18s | — | ✓ |
| cylinder.stl | ✅ | 4.42s | — | ✓ |
| degenerate_faces_sliver_triangles.stl | ✅ | 5.22s | — | ✓ |
| external_flow_isolated_box.stl | ✅ | 4.28s | — | ✓ |
| extreme_aspect_ratio_needle.stl | ❌ | 87.74s | — | ✗ |
| | Error: 2026-04-12T11:03:31.496218Z [info     ] retry_poli... | | | |
| five_disconnected_spheres.stl | ✅ | 3.81s | — | ✓ |
| hemisphere_open.stl | ❌ | 1.59s | — | ✗ |
| | Error: 2026-04-12T11:05:12.233702Z [info     ] retry_poli... | | | |
| hemisphere_open_partial.stl | ❌ | 155.42s | — | ✗ |
| | Error: 2026-04-12T11:05:13.812071Z [info     ] retry_poli... | | | |
| high_genus_dual_torus.stl | ✅ | 4.65s | — | ✓ |
| highly_skewed_mesh_flat_triangles.stl | ❌ | 404.56s | — | ✗ |
| | Error: 2026-04-12T11:08:08.586643Z [info     ] retry_poli... | | | |
| large_mesh_250k_faces.stl | ✅ | 9.72s | — | ✓ |
| many_small_features_perforated_plate.stl | ❌ | 86.24s | — | ✗ |
| | Error: 2026-04-12T11:15:37.844069Z [info     ] retry_poli... | | | |
| mixed_features_wing_with_spike.stl | ❌ | 119.49s | — | ✗ |
| | Error: 2026-04-12T11:17:13.679931Z [info     ] retry_poli... | | | |
| mixed_watertight_and_open.stl | ❌ | 109.70s | — | ✗ |
| | Error: 2026-04-12T11:19:24.568052Z [info     ] retry_poli... | | | |
| multi_scale_sphere_with_micro_spikes.stl | ✅ | 3.80s | — | ✓ |
| naca0012.stl | ❌ | 67.78s | — | ✗ |
| | Error: 2026-04-12T11:21:26.928009Z [info     ] retry_poli... | | | |
| nonmanifold_disconnected.stl | ✅ | 337.72s | — | ✓ |
| self_intersecting_crossed_planes.stl | ✅ | 342.83s | — | ✓ |
| sharp_features_micro_ridge.stl | ❌ | 166.77s | — | ✗ |
| | Error: 2026-04-12T11:35:08.991433Z [info     ] retry_poli... | | | |
| sphere.stl | ✅ | 4.23s | — | ✓ |
| sphere_20k.stl | ✅ | 9.36s | — | ✓ |
| sphere_watertight.stl | ✅ | 4.15s | — | ✓ |
| trimesh_box.stl | ✅ | 7.63s | — | ✓ |
| trimesh_duct.stl | ✅ | 6.06s | — | ✓ |
| very_thin_disk_0_01mm.stl | ⏱ | — | — | ✗ |
| | Error: Timeout after 600s... | | | |
