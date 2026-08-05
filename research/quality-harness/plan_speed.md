# CARD BETA2830_SI_DETECT_MEMO (beta2830) — native_tet 곡면 경로 SI 검출 메모이제이션 (순수 가속, 결과 불변)

**target_engine**: tet
**모티프**: fTetWild 곡면 입력 처리 — surface self-intersection 검출은 입력 불변량. rebudget 재생성 루프에서 동일 표면을 매 pass 재검출하는 낭비 제거.

## 이론적 근거 (계측 기반)

- **문제 정의**: mesher 진입부(`mesher.py:382`)는 매 호출마다
  `native_remesh._detect_self_intersections(V, F)` 를 실행. 이 함수는 O(T^2)
  AABB 오버랩 행렬 + Python per-pair 루프(`np.intersect1d` + `_moller_tri_tri`).
  sphere.stl(T=1280)에서 1회 ~17.8s. cube(작은 T)는 <0.1s → 이차 스케일.
- **낭비 구조**: `harness.py:173` `_generate_with_cell_rebudget` 는 동일 (vertices,
  faces) 로 `generate_native_tet` 를 최대 passes+1 = **7회** 재호출(edge/seed 만
  변경). 검출은 auto-fix(`mesher.py:432`) 이전에 실행되므로 **표면 V,F 는 7 pass
  모두 바이트 동일**. 따라서 7 x 17.8s ~= 125s 중 6회 ~107s 는 순수 중복.
  Advisor 프로파일의 `cell_rebudget -> uuu2_si_detect` 전이 ~17.8s x 다수와 정확히 일치.
- **핵심 아이디어**: `_detect_self_intersections` 를 (V,F) content-hash 로
  메모이제이션. 동일 입력 -> 캐시된 동일 배열 반환. 알고리즘/결과 무변경, 재실행만 제거.
  - 자료구조: module-level FIFO dict (max 8 entries), key = `hash((V.shape, F.shape,
    V.tobytes(), F.tobytes()))`. 해시 비용 ~20us (45KB) << 17.8s.
  - 정확성 보장: memoization 은 순수 함수의 항등 캐시 → 반환값 array-equal 불변.
    post-split 재검출(`mesher.py:399`, 다른 F_cand)은 cache-miss 로 정상 신규 계산.
    다른 mesh 는 다른 key -> miss. 프로세스 로컬, 8-entry 상한으로 누수 없음.
- **레퍼런스**: `mesher.py:371-422` (UUU2 진입 검출), `harness.py:173-182`
  (rebudget 재호출), `native_remesh/__init__.py:32-79` (O(T^2) 검출 본체).
- **혁신성 평가**: novelty 1 (memoization 가드) / rigor 3 (bit-identity 증명적 보존)
  / impact 3 (TIMEOUT 3형상 -> PASS). 합 7. 속도 카드로 채택.

## 변경

- 파일: `core/preprocessor/native_remesh/__init__.py` (단일 파일)
- 함수: `_detect_self_intersections` (line ~32) — 본체를 `_detect_self_intersections_impl`
  로 리네임, 동명 wrapper 신설.
- 핵심 변경 (<=25줄):
  1. 기존 `_detect_self_intersections` 본체(32-79) -> `_detect_self_intersections_impl`.
  2. module-level `_SI_MEMO: dict = {}` 추가.
  3. 신규 `_detect_self_intersections(V, F)`: key 계산 -> hit 시 `cached.copy()` 반환,
     miss 시 `_impl` 호출 -> 저장(FIFO pop when >8) -> `.copy()` 반환.
     비-ndarray/비정상 입력은 try/except 로 `_impl` 직행(캐시 우회).
  4. `__all__`(line ~321) 은 `_detect_self_intersections` 유지 — 심볼명 불변.
- 단조 가드: 결과 항등(memoization) 이 곧 가드. copy 반환으로 caller mutation 격리.
  검출 실패/예외 시 캐시 우회 -> 기존 동작 100% 보존.

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
# 1) 검출기 정확성 + 리메시 회귀 (결과 불변)
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 timeout 90 python3 -m pytest \
  tests/test_native_remesh.py tests/test_self_intersect.py -q
# 2) cube 솔리드 4게이트 + skew 불변 (정확성 회귀 가드)
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 timeout 90 python3 scripts/smoke_native_tet.py 2000
```

## 합격 기준 (validator 가 평가)

- 위 pytest 2종 PASS (결과 array-equal 불변 — memoization 항등).
- `scripts/smoke_native_tet.py 2000`: 솔리드 4불변(surface 6.000, off-plane 0.000,
  volume ~1.0, degenerate 0) 유지, skew 값 **직전과 동일**.
- **sphere 속도 + 결과 불변** (`scripts/bench_native_tet_matrix.py`, draft/N=2000/P4C=0):
  - sphere.stl 완주 시간 **<60s** (목표 <30s), cells=2453 / skew=2.62 / area·vol≈1.0
    **불변** (캐시 전후 동일).
  - TIMEOUT 3형상(sphere / sphere_watertight / torus) 중 sphere 대표 PASS 전환.
- cylinder wall_dev 0.000, solid 4게이트 불변 (정확성 1비트 미희생).
- bench 회귀 없음: 다른 형상 결과/시간 동등 이하.

## 카드 시퀀스 위치

- 곡면 경로 성능 시퀀스 1/2 카드. 본 카드 = rebudget 중복 검출 제거(107s 절감,
  sphere ~143s -> ~35s, <60s 달성).
- 다음 카드 후보 (PASS 후, 목표 <30s 필요 시): BETA2831_SI_DETECT_ACCEL —
  단일 검출 17.8s 자체 가속. 단, `native_remesh._detect_self_intersections` 를
  KDTree/spatial-hash 로 교체 시 pair 집합·순서 bit-identity 재현 필수 (SI 보유
  FAIL mesh 에서 face-split 순서 영향). 순서 보존(정렬) 가드 동반해야 채택 가능.
