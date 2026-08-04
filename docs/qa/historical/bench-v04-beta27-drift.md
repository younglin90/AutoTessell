# bench_v04 drift — v0.4.0-beta22 → beta27

## Scope

v0.4.0-beta23~beta27 의 구조적 변경 (Strategist native-first, fine BL 자동화,
hybrid dual, L1 native 기본화, BL 수치 품질 회귀) 이후 벤치마크 드리프트 스냅샷.

## Snapshot

- **Baseline:** `tests/stl/bench_v04_20260423T004153.json` (30 entries)
- **Matrix:** 5 난이도 STL × 3 native 엔진 × 2 quality (draft/standard) = 30 조합

## 결과 요약

| 지표 | 값 |
|------|-----|
| 전체 조합 | 30 |
| polyMesh 생성 성공 | 28 |
| polyMesh 생성 실패 | 2 |
| 성공률 | 93.3% |

## 성공 조합 (28)

각 mesh_type × quality × difficulty 에서 native 엔진이 `constant/polyMesh/` 를
성공적으로 쓴 조합. 결과 상세 (elapsed / last_lines) 는 snapshot JSON 참조.

## 실패 조합 (2)

정기적 실패는 difficulty=05_ultra_knot 의 고복잡도 형상에서 native_tet harness
가 timeout 하는 패턴. fine quality 로 승급 + target_edge 조정 시 대부분 해결
가능. v0.5 에서 복잡도 분석 개선 예정.

## beta23~beta27 structural 변경의 회귀 영향

| 변경 | 예상 bench 영향 | 관측 |
|------|------------------|------|
| Strategist native-first (beta23) | tier 선택 경로만 변경, 엔진 자체는 동일 | 중립 |
| fine BL 자동화 (beta24) | standard/draft 는 영향 없음 (BL off) | 중립 |
| poly_bl hybrid dual (beta25) | bench 는 BL 을 돌리지 않음 | 중립 |
| L1 native 기본화 (beta26) | L1 경로 변경, surface quality 비슷 | 중립 |
| BL 수치 품질 회귀 (beta27) | 신규 테스트만 추가 | 중립 |

구조 변경이 기존 matrix 성공률에 부정적 영향 없음.

## beta28~beta31 후속 변경

| beta | 변경 | 영향 |
|------|------|------|
| beta28 | NumpyKDTree 교체 | 성능 동일, scipy 의존 축소 |
| beta29 | Qt GUI native-first UX | bench 비-영향 |
| beta30 | README 갱신 | docs-only |
| beta31 | E2E matrix (slow) | 신규 테스트, 3/9 PASS + 6 xfail |

## 다음 bench 실행 계획

- v0.5 재정의: Voronoi/Delaunay/ConvexHull 자체 구현 후 full matrix + 난이도
  4~5 튜닝 시 성공률 ≥ 95% 목표.
- `python3 tests/stl/bench_v04_matrix.py --diff` CLI 로 연속 run 간 drift 추적.

---

*Generated for beta27 series completion — beta32 archival commit.*
