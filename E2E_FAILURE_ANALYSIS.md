# E2E 테스트 실패 분석 (v0.3.1 기준선)

작성일: 2026-04-13  
범위: AutoTessell Draft quality E2E 벤치마크  
근거: `E2E_TEST_RESULTS.json`, `BENCHMARK_ANALYSIS_DETAILED.md`, `PERFORMANCE_REPORT.json`, `PERFORMANCE_REPORT.md`, `v0.4_FINAL_RESULTS.md`, `BENCHMARK_RESULTS_V0.4.md`, `IMPROVEMENTS_V0.4.md`, `CURRENT_STATUS_AND_BACKLOG.md`, `TEST_CASES_GUIDE.md`, `scripts/benchmark_test_cases.py`, `git log v0.3.1..HEAD`

## 요약

v0.3.1 전후의 E2E 성공률 36% 문제는 단일 원인이 아니라 데이터 기준선 혼재, 120초 타임아웃 설정, 중간 복잡도 파라미터 드리프트, 열린/2D/극단 형상 처리 부족이 결합된 결과다.

확인된 기준선은 3개다.

| 기준선 | 소스 | 범위 | 결과 | 해석 |
|---|---:|---:|---:|---|
| v0.3.1 중간 JSON | `E2E_TEST_RESULTS.json` | 20개 | 8 PASS, 3 FAIL, 9 TIMEOUT | 120s timeout 스냅샷. 25개 전체가 아님 |
| v0.3.1 상세 분석 | `BENCHMARK_ANALYSIS_DETAILED.md` | 25/26 완료 | 9 PASS, 16 FAIL, 1 중단 | 36% 기준선. `very_thin_disk_0_01mm.stl` 중단 |
| v0.4 최종 | `PERFORMANCE_REPORT.json`, `v0.4_FINAL_RESULTS.md` | 26개 | 15 PASS, 10 FAIL, 1 TIMEOUT | Phase 0/1/2 적용 후 57.7% |

핵심 결론:

| 항목 | 판단 |
|---|---|
| 36%의 직접 원인 | 중간/고복잡도 형상에서 Tier/Generator 파라미터가 충분히 적응하지 못함 |
| 가장 큰 빠른 개선점 | TetWild 파라미터 키 불일치, aspect ratio 계산, 2D/open surface 감지 |
| 단순 timeout 증가 효과 | 제한적. 120s를 올리면 일부 timeout은 완료되지만 품질 실패로 바뀔 수 있음 |
| v0.4에서 검증된 개선 효과 | 9/25 또는 9/26 수준에서 15/26까지 상승 |
| 70% 가능성 | Sprint 1-3 변경의 예상치 기준 18-21/26, 즉 69-81%. 전체 E2E 재실행으로 확인 필요 |

## 데이터 무결성 메모

요청에는 “25개 E2E 테스트”와 “9개 실패 케이스”가 함께 등장하지만, 저장된 산출물은 서로 다르다.

| 파일 | 발견 내용 |
|---|---|
| `E2E_TEST_RESULTS.json` | `total=20`, `passed=8`, `failed=3`, `timeout=9`. 120초 timeout 기반 중간 실행 결과 |
| `BENCHMARK_ANALYSIS_DETAILED.md` | 26개 중 25개 완료, 9개 성공, 16개 실패, `very_thin_disk_0_01mm.stl` 중단 |
| `PERFORMANCE_REPORT.json` | v0.4 최종 26개, 15개 성공, 10개 실패, 1개 600초 timeout |
| `scripts/benchmark_test_cases.py` | 현재 기본 timeout은 600초. 과거 `E2E_TEST_RESULTS.json`의 120초와 다름 |

따라서 이 문서는 36% 원인 분석은 `BENCHMARK_ANALYSIS_DETAILED.md`를 기준으로 삼고, 케이스별 최신 계측값과 개선 검증은 `PERFORMANCE_REPORT.json`을 보조 근거로 사용한다.

## v0.3.1 기준 25/26 케이스 목록

`BENCHMARK_ANALYSIS_DETAILED.md` 기준 PASS 9개, FAIL 16개, 중단 1개다. 최종 Tier는 v0.3.1 실패 케이스에 대해 저장되지 않았고, v0.4의 성공 케이스는 대부분 `tier2_tetwild`로 확인된다.

| 케이스 | v0.3.1 상태 | v0.3.1 시간 | v0.4 상태 | v0.4 시간 | 최종 Tier | 형상/목표 |
|---|---:|---:|---:|---:|---|---|
| `multi_scale_sphere_with_micro_spikes.stl` | PASS | 3.57s | PASS | 3.80s | `tier2_tetwild` | 마이크로 스케일 피처 |
| `sphere.stl` | PASS | 3.63s | PASS | 4.23s | `tier2_tetwild` | 기본 구 |
| `sphere_watertight.stl` | PASS | 3.93s | PASS | 4.15s | `tier2_tetwild` | watertight baseline |
| `trimesh_box.stl` | PASS | 4.89s | PASS | 7.63s | `tier2_tetwild` | 단순 상자 |
| `trimesh_duct.stl` | PASS | 4.97s | PASS | 6.06s | `tier2_tetwild` | 덕트 |
| `sphere_20k.stl` | PASS | 7.84s | PASS | 9.36s | `tier2_tetwild` | 고해상도 구 |
| `large_mesh_250k_faces.stl` | PASS | 11.03s | PASS | 9.72s | `tier2_tetwild` | 대형 메시 |
| `nonmanifold_disconnected.stl` | PASS | 336.49s | PASS | 337.72s | `tier2_tetwild` | non-manifold/disconnected |
| `self_intersecting_crossed_planes.stl` | PASS | 352.53s | PASS | 342.83s | `tier2_tetwild` | 자기교차 평면 |
| `hemisphere_open.stl` | FAIL | 1.65s | FAIL | 1.59s | 미생성 | 열린 표면 |
| `degenerate_faces_sliver_triangles.stl` | FAIL | 1.80s | PASS | 5.22s | `tier2_tetwild` | 퇴화/sliver 면 |
| `coarse_to_fine_gradation_two_spheres.stl` | FAIL | 1.82s | PASS | 5.18s | `tier2_tetwild` | coarse-to-fine LOD |
| `five_disconnected_spheres.stl` | FAIL | 1.84s | PASS | 3.81s | `tier2_tetwild` | 다중 component |
| `high_genus_dual_torus.stl` | FAIL | 1.90s | PASS | 4.65s | `tier2_tetwild` | high genus |
| `highly_skewed_mesh_flat_triangles.stl` | FAIL | 23.12s | FAIL | 404.56s | 미생성 | 극도 skew/aspect |
| `extreme_aspect_ratio_needle.stl` | FAIL | 24.30s | FAIL | 87.74s | 미생성 | 극단 종횡비 |
| `hemisphere_open_partial.stl` | FAIL | 40.52s | FAIL | 155.42s | 미생성 | 불완전 열린 반구 |
| `broken_sphere.stl` | FAIL | 69.21s | FAIL | 220.62s | 미생성 | 손상 입력 |
| `naca0012.stl` | FAIL | 77.38s | FAIL | 67.78s | 미생성 | 2D 에어포일 |
| `many_small_features_perforated_plate.stl` | FAIL | 89.97s | FAIL | 86.24s | 미생성 | 다수 구멍/미세 피처 |
| `mixed_watertight_and_open.stl` | FAIL | 110.41s | FAIL | 109.70s | 미생성 | watertight+open 혼합 |
| `mixed_features_wing_with_spike.stl` | FAIL | 128.84s | FAIL | 119.49s | 미생성 | 날개+스파이크 혼합 |
| `sharp_features_micro_ridge.stl` | FAIL | 169.90s | FAIL | 166.77s | 미생성 | 예각 micro ridge |
| `cylinder.stl` | 별도/중간 JSON PASS | 4.35s | PASS | 4.42s | `tier2_tetwild` | 원통 |
| `external_flow_isolated_box.stl` | 별도/중간 JSON PASS | 3.26s | PASS | 4.28s | `tier2_tetwild` | external flow box |
| `very_thin_disk_0_01mm.stl` | 중단 | - | TIMEOUT | >600s | 미생성 | 극도로 얇은 구조 |

## 실패 원인별 분포

아래 분포는 v0.3.1 상세 분석의 16개 실패와 1개 중단을 포함한 실무 분류다. 단, `BENCHMARK_ANALYSIS_DETAILED.md`는 총계로 16개 실패를 보고하지만 본문 카테고리에 이름이 명시된 실패 케이스는 14개뿐이다. 따라서 누락된 2개는 `SOURCE_GAP`으로 분리했다.

`QUALITY`는 quality report의 Hausdorff 수치가 남은 케이스가 아니라, 메시/품질 검증 단계까지 도달하지 못했거나 품질 판정에서 탈락한 것으로 추정되는 중간 복잡도 케이스를 포함한다. 실패 레코드에 `quality_report`가 없기 때문에 Hausdorff 초과를 직접 계측한 항목은 없다.

| 원인 | 케이스 수 | 비율 | 케이스 |
|---|---:|---:|---|
| TIMEOUT/RUNTIME | 3 | 17.6% | `mixed_features_wing_with_spike.stl`, `sharp_features_micro_ridge.stl`, `very_thin_disk_0_01mm.stl` |
| QUALITY/PARAMETER | 5 | 29.4% | `many_small_features_perforated_plate.stl`, `mixed_watertight_and_open.stl`, `extreme_aspect_ratio_needle.stl`, `highly_skewed_mesh_flat_triangles.stl`, `naca0012.stl` |
| INVALID/INPUT | 4 | 23.5% | `hemisphere_open.stl`, `hemisphere_open_partial.stl`, `broken_sphere.stl`, `degenerate_faces_sliver_triangles.stl` |
| OTHER/STRATEGY | 3 | 17.6% | `coarse_to_fine_gradation_two_spheres.stl`, `five_disconnected_spheres.stl`, `high_genus_dual_torus.stl` |
| SOURCE_GAP | 2 | 11.8% | 상세 문서 총계에는 포함되지만 본문 카테고리에서 이름이 명시되지 않은 실패 2개 |

`E2E_TEST_RESULTS.json`만 기준으로 하면 분포는 다르다: 20개 중 9개가 “Timeout after 120s”, 3개가 일반 실패, 8개가 성공이다. 이 차이가 가설 4, 즉 데이터 버전 불일치의 핵심 증거다.

## 실패 원인 상세 분석

### TIMEOUT/RUNTIME

| 케이스 | 증상 | 실패 지점 추정 | 근거 | 개선 방향 |
|---|---|---|---|---|
| `very_thin_disk_0_01mm.stl` | v0.4에서도 600초 초과 timeout | Generator/TetWild 또는 fallback 경로 | `v0.4_FINAL_RESULTS.md`: 600s 초과, Thin-wall 처리 필요 | thin-wall 감지 후 cell size/2D 처리 또는 early fallback |
| `sharp_features_micro_ridge.stl` | 169.90s 후 실패, v0.4도 166.77s 실패 | Generator/Evaluator 전후 | micro ridge, 극단 예각 피처 | feature angle 기반 보수 파라미터 또는 snappy 강화 |
| `mixed_features_wing_with_spike.stl` | 128.84s 후 실패, v0.4는 119.49s 실패 | Generator/Tier fallback | 날개+스파이크 혼합 피처 | TetWild 내부 timeout 후 fallback 전환, 피처별 cell size 조정 |
| `nonmanifold_disconnected.stl` | 120s JSON에서는 timeout, 상세 분석/v0.4에서는 337s PASS | timeout 정책 문제 | 120s 설정에서는 false negative, 600s에서는 PASS | 케이스별 timeout profile 적용 |
| `self_intersecting_crossed_planes.stl` | 120s JSON에서는 timeout, 상세 분석/v0.4에서는 343s PASS | timeout 정책 문제 | 120s 설정에서는 false negative, 600s에서는 PASS | extreme 분류 시 timeout floor 상향 |

판단: 단순히 전역 timeout을 올리면 성공률은 오를 수 있지만 총 실행 시간이 크게 늘고, `very_thin_disk_0_01mm.stl`처럼 600초를 초과하는 케이스는 해결되지 않는다. 전역 상향보다 complexity 기반 timeout floor가 더 안전하다.

### QUALITY/PARAMETER

| 케이스 | 증상 | 실패 지점 추정 | 근거 | 개선 방향 |
|---|---|---|---|---|
| `many_small_features_perforated_plate.stl` | v0.3.1 89.97s 실패, v0.4 86.24s 실패 | Generator parameter tuning | 64개 구멍 천공판, 미세 피처 | local feature size 기반 TetWild/snappy 파라미터 조정 |
| `mixed_watertight_and_open.stl` | v0.3.1 110.41s 실패, v0.4 109.70s 실패 | Preprocessor repair + Generator | watertight/open 혼합 | open boundary 분리/repair 후 tier 강제 |
| `extreme_aspect_ratio_needle.stl` | v0.3.1 24.30s 실패, v0.4 87.74s 실패 | Strategist 분류 + Generator | 길이 100배 needle, BL 처리 목표 | 2D/thin/needle 별도 분기 |
| `highly_skewed_mesh_flat_triangles.stl` | v0.3.1 23.12s 실패, v0.4 404.56s 실패 | Evaluator skewness 또는 Generator | aspect ratio >100 납작 삼각형 | skewed surface pre-remesh 강제 |
| `naca0012.stl` | v0.3.1 77.38s 실패, v0.4 67.78s 실패 | Strategist 2D 감지 + Generator | 2D 에어포일 | `tier0_2d_meshpy` 우선 또는 thin extrusion |

직접 Hausdorff 거리 초과 수치는 실패 케이스에 저장되어 있지 않다. 성공 케이스의 `quality_report`에는 `geometry_fidelity.hausdorff_relative`가 남아 있으나, 실패 케이스는 `quality_report=null`이다. 따라서 이 범주의 본질은 “Hausdorff threshold 완화”보다 “품질 평가까지 도달 가능한 메시 생성”에 가깝다.

### INVALID/INPUT

| 케이스 | 증상 | 실패 지점 추정 | 근거 | 개선 방향 |
|---|---|---|---|---|
| `hemisphere_open.stl` | 1.65s 실패, v0.4도 1.59s 실패 | Analyzer/Preprocessor 또는 early Generator | 열린 표면 | open surface closing 또는 명시적 unsupported fail |
| `hemisphere_open_partial.stl` | 40.52s 실패, v0.4 155.42s 실패 | Preprocessor repair + Generator | 열린 반구 | repair 정책 강화, timeout guard |
| `broken_sphere.stl` | 69.21s 실패, v0.4 220.62s 실패 | Analyzer/Preprocessor | 손상 입력 | critical issue 조기 감지 및 빠른 실패 |
| `degenerate_faces_sliver_triangles.stl` | v0.3.1 실패, v0.4 PASS | Preprocessor L2 remesh | 매우 작은 sliver 면 | v0.4 Phase 0/1 효과로 해결됨 |

v0.4의 Phase 1 입력 검증은 empty geometry, degenerate bounding box, invalid volume, critical issue 처리를 추가했다. 다만 손상/열린 표면이 모두 해결된 것은 아니며, 실패 시간을 줄이는 방향의 가치가 크다.

### OTHER/STRATEGY

| 케이스 | 증상 | 실패 지점 추정 | 근거 | v0.4 변화 |
|---|---|---|---|---|
| `coarse_to_fine_gradation_two_spheres.stl` | v0.3.1 1.82s 실패 | Strategist/parameter key | LOD 혼합 | v0.4 PASS 5.18s |
| `five_disconnected_spheres.stl` | v0.3.1 1.84s 실패 | Preprocessor component 병합 | 다중 component | v0.4 PASS 3.81s |
| `high_genus_dual_torus.stl` | v0.3.1 1.90s 실패 | Strategist high-genus 분류 | genus=2 | v0.4 PASS 4.65s |
| 데이터 기준선 혼재 | 20개/25개/26개 결과가 공존 | 벤치마크 운영 | timeout 120s vs 600s | 보고서/runner 기준 정리 필요 |

v0.4에서 해결된 케이스들은 대부분 코어 버그 수정의 직접 효과로 보인다. `IMPROVEMENTS_V0.4.md` 기준 수정 사항은 aspect ratio 계산 정정, TetWild 적응형 튜닝 추가, `tw_*`와 `tetwild_*` 파라미터 키 불일치 수정이다.

## v0.4에서 실제로 해결된 케이스

| 케이스 | v0.3.1 | v0.4 | 추정 해결 원인 |
|---|---:|---:|---|
| `coarse_to_fine_gradation_two_spheres.stl` | FAIL | PASS | aspect ratio/complexity 분류 개선, TetWild tuning 적용 |
| `degenerate_faces_sliver_triangles.stl` | FAIL | PASS | TetWild 파라미터 일관성, 전처리 robustness |
| `five_disconnected_spheres.stl` | FAIL | PASS | component/complexity 분류 개선 |
| `high_genus_dual_torus.stl` | FAIL | PASS | high-genus strategy 개선 |
| `cylinder.stl` | 중간 JSON PASS/품질 이슈 후보 | PASS | verdict 경로 및 draft 판정 일관화 |
| `external_flow_isolated_box.stl` | 중간 JSON PASS | PASS | 안정 케이스 유지 |

v0.4 최종 결과는 15/26, 즉 57.7%다. 이는 36% 기준선에서 +21.7%p 개선이다.

## Quick wins

### 1. 벤치마크 기준선 고정

| 항목 | 내용 |
|---|---|
| 원인 | `E2E_TEST_RESULTS.json`은 20개/120s, 상세 분석은 25/26, v0.4는 26개/600s로 혼재 |
| 제안 | runner 출력에 `suite_id`, `case_count`, `timeout`, `git_sha`, `quality`, `runner_version` 기록 |
| 예상 효과 | 성공률 해석 오류 제거. 36%, 40%, 57.7%가 같은 기준으로 비교 가능 |
| 구현 노력 | 15-30분 |
| 위험도 | 낮음. 테스트 메타데이터만 추가 |

### 2. Complexity 기반 timeout profile

| 항목 | 내용 |
|---|---|
| 원인 | 120s 전역 timeout은 `nonmanifold_disconnected`와 `self_intersecting_crossed_planes`를 false negative로 만들 수 있음 |
| 제안 | simple/moderate 120s, complex 180s, extreme 420-600s로 runner timeout floor 적용 |
| 예상 효과 | 120s 기준 8/20 또는 9/25에서 장시간 PASS 후보 2개 회복 가능. 단 600s 초과 thin disk는 별도 처리 필요 |
| 구현 노력 | 30분 |
| 위험도 | 중간. 벤치마크 시간이 늘 수 있으므로 per-case cap 필요 |

### 3. TetWild 파라미터 키/적응형 튜닝 유지 검증

| 항목 | 내용 |
|---|---|
| 원인 | v0.3.1 계열에서 `tw_epsilon`/`tw_stop_energy`와 `tetwild_epsilon`/`tetwild_stop_energy` 불일치로 튜닝이 무시됨 |
| 제안 | strategy 생성 결과에 실제 generator 입력 파라미터를 저장하고 회귀 테스트 추가 |
| 예상 효과 | v0.4에서 이미 `coarse_to_fine`, `degenerate`, `high_genus`, `five_disconnected` 개선으로 검증됨. 9/25 → 13-15/26급 효과의 핵심 |
| 구현 노력 | 30분-1시간 |
| 위험도 | 낮음. v0.4 코드에 이미 반영된 개선을 보호하는 테스트 |

### 4. Open surface pre-closing + early unsupported fail

| 항목 | 내용 |
|---|---|
| 원인 | `hemisphere_open`, `hemisphere_open_partial`, `mixed_watertight_and_open`은 열린 표면/혼합 경계에서 실패 |
| 제안 | TetWild 전 `trimesh.fill_holes()`와 `pymeshfix.repair()` 시도, repair 실패 시 긴 fallback 대신 명확한 early fail |
| 예상 효과 | `hemisphere_open*` 1-2개 회복 또는 실패 시간 대폭 단축. Sprint 1-3 보고서의 예상 효과 +1-2 케이스 |
| 구현 노력 | 30분 |
| 위험도 | 중간. 부적절한 hole closing은 형상 fidelity를 훼손할 수 있어 repair 여부를 report에 기록해야 함 |

### 5. 2D/thin shape 분기 강화

| 항목 | 내용 |
|---|---|
| 원인 | `naca0012`, `extreme_aspect_ratio_needle`, `very_thin_disk_0_01mm`는 3D TetWild 경로에 부적합한 얇은/2D 형상 |
| 제안 | bbox min/max 비율, 정점 수, edge ratio 기반으로 `tier0_2d_meshpy` 또는 thin extrusion 경로 우선 적용 |
| 예상 효과 | `naca0012` 1개 회복 가능, thin/needle 케이스는 실패 시간 단축 또는 별도 fallback 가능 |
| 구현 노력 | 30분-1시간 |
| 위험도 | 중간. 실제 3D 얇은 구조와 2D 프로파일을 구분해야 함 |

## 70%+ 달성 시나리오

| 단계 | 누적 성공률 | 근거 |
|---|---:|---|
| v0.3.1 기준선 | 9/25 = 36% | `BENCHMARK_ANALYSIS_DETAILED.md` |
| v0.4 Phase 0/1/2 | 15/26 = 57.7% | `PERFORMANCE_REPORT.json`, `v0.4_FINAL_RESULTS.md` |
| Sprint 1-3 예상 | 18-21/26 = 69-81% | `SPRINT_123_COMPLETION.md`의 open surface, TetWild timeout, 2D detection 개선 예상 |

70%를 넘기려면 26개 중 최소 19개 성공이 안정적이다. 현재 v0.4 15개 성공에서 4개를 더 회복해야 한다. 가장 현실적인 후보는 다음 4개다.

| 후보 | 이유 | 대응 |
|---|---|---|
| `hemisphere_open.stl` | 작은 열린 표면, 빠른 실패 | open surface closing |
| `hemisphere_open_partial.stl` | 열린 반구, repair 대상 | open surface closing + fallback timeout |
| `naca0012.stl` | 명확한 2D 에어포일 | 2D tier 우선 |
| `many_small_features_perforated_plate.stl` 또는 `mixed_watertight_and_open.stl` | runtime은 90-110s로 timeout보다 품질/파라미터 문제 | TetWild timeout guard + local feature tuning |

## 다음 단계

1. `scripts/benchmark_test_cases.py` 결과 JSON에 runner 메타데이터와 timeout 설정을 기록한다.
2. Sprint 1-3 변경 후 전체 E2E를 재실행해 18/26 이상인지 확인한다.
3. 실패 케이스에 대해 `quality_report.json`, `mesh_strategy.json`, stderr 전체 로그를 보존하도록 runner를 수정한다.
4. `naca0012`, `hemisphere_open*`, `very_thin_disk_0_01mm`를 별도 regression fixture로 승격한다.
5. 70% 미달 시 `many_small_features_perforated_plate`, `mixed_watertight_and_open`, `sharp_features_micro_ridge` 순서로 파라미터 튜닝을 진행한다.
