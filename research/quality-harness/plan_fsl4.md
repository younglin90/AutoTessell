# CARD FSL4 — dual-torus 2-boundary wedge = 구조적 known-limit 확정 + xfail(strict) 게이트

**target_engine**: tet
**모티프**: fTetWild §3.4 topology-preserving 제거의 한계 확정 — flat-on-surface 슬리버는
volume-only local op 으로 해소 불가, near-wall 내부점(Garimella 2003) 필수임을 게이트로 명문화

## Baseline 재확인 (정본 N=600 직접호출, P4C=0, writer-spy 캡처, ~30s 실측)

- grade B, n_cells 12219, n_surf 2047. FSL3 실측: n_eligible 9, n_flipped 0 (전량 min_q revert — 확정).
- FSL1 detector: `n_cand=75, n_flip_eligible=9, n_core_unflippable=61, max_bskew=2.94e7,
  worst_tet=8918`.
- **61 wedge 전수 위상 (실측)**: **전부 정확히 2 boundary-face**. bskew>1e4 **57개**, >1e6 **29개**
  (worst 2.94e7 뿐 아니라 다수가 대형 — 단일셀 문제 아님). worst 8918=[1355,633,67,519] 4정점
  전부 surface, vol 6.1e-11, q 7.4e-9, 4정점 공면(최소특이값 4.7e-9).

## 두 접근 실측 비교 (결정적)

- **(a) surface-edge 보존 재분할 — 실측 반증, 기각**:
  - 61개 중 **57개가 coplanar flat-on-surface**(2 boundary-face 가 *동일 평면*, 이면각 mean
    0.74° max 11.2°). normal-span/edge_max = mean 2.4e-3, min 2.3e-8 → 슬리버가 워셔 gap 을
    **가로지르지 않고** 한쪽 벽 평면에 **납작하게 눕는다**(washer 반두께 0.5 vs span ~0.002·edge).
  - 브리핑 전제("두 표면 사이 중점 삽입")는 **이 기하에 부재**. 4정점 공면(4.7e-9)이라
    **envelope(참 표면) 위 어떤 신규 정점도 같은 평면** → 분할 후 sub-tet 여전히 공면 → bskew 불변.
    게다가 표면 정점 증가 → **#1 표면보존 불변식·area/vol 위협**. → (a) 구조적 불가.
- **(b) near-wall 내부 offset 점 — 유일 해, 그러나 multi-card**:
  - worst wedge 의 2 boundary-face 를 내부 offset apex(centroid −normal·0.5·edge)로 재삼각화하면
    **bskew 2.94e7 → 0.34** (실측), signed-vol 동부호. **cure 는 오직 내부점 삽입뿐**.
  - 그러나 이는 **interior cavity 재-tet + neg-vol/void/표면 guard** 를 wedge fan 전역에 요구 →
    ≤80줄 단일카드 불가. **cylinder skew 44.9 (BETA2829) 와 동일 class**("여러 카드짜리,
    volume-only local op 으론 불가"로 이미 확정된 미해결 항목).

→ **선택: (b)-를 확정 known-limit 으로 명문화**. (a) 는 반증 기각. 실제 cure(Garimella
near-wall 내부점 삽입)는 다중-body 얇은 형상 근본 재설계 로드맵으로 이관.

## 이 카드 (엔진 무변경, read-only 게이트 신설 — 회귀 0)

- **파일**: `tests/test_native_tet_dual_torus_limit.py` (신규). **core/ 무변경** → 4대 solid
  불변식(surface 6.0 / void 0 / vol 1.0 / degen 0) 및 area/vol 구조적 불변(자명).
- **재현 헬퍼**: `plan_torus_quality.md` §재현 그대로 — `generate_native_tet` **직접호출**
  (orchestrator rebudget 회피), `target_cells=600`, `AUTO_TESSELL_P4C_PYTETWILD=0`,
  case_dir 에 polyMesh 기록 후 파싱.
- **게이트 A (PASS — #1 불변식 LOCK, 최우선 가드)**: dual_torus 에서
  `sum|cell vol| / input_vol ∈ [0.95, 1.05]` (실측 **0.9913**, input_vol=19.4868) **AND**
  `grade ≥ B`. BETA2832 가 복구한 volume-tiling 을 dual_torus 에 못박아 향후 FSL4-cure 시도가
  절대 재회귀 못하게 함. (degenerate-count 게이트는 **넣지 않음** — flat wedge 존재 자체가
  known-limit 이므로.)
- **게이트 B (xfail(strict) — cure 목표 명문화)**: polyMesh 경계면 skew 재계산
  (`native_checker._compute_boundary_skewness` 공식: 각 boundary face 의 owner-centroid 기준
  |tangential|/|normal_dist|), `max_boundary_skew < 100.0` 를 assert. **현재 2.94e7 → 실패
  (예상된 xfail)**. Garimella 내부점 삽입 cure 착지 시 XPASS→strict FAIL 로 자동 경보.
  docstring 에 근본원인(57/61 coplanar flat-on-surface, (a) 반증, (b) 유일해 multi-card) 기록.

## 검증 명령 (unit_tester 가 그대로 실행, 각 3분 이내)

```bash
timeout 120 python3 -m pytest tests/test_native_tet_dual_torus_limit.py -q
```
기대: 게이트 A **PASS**, 게이트 B **xfailed(strict)** (2 개, 실패 0). 회귀:
```bash
timeout 170 python3 -m pytest tests/test_native_tet_solid_volume.py -q
```

## 합격 기준 (validator 평가 — 정직한 실측)

- 신규 게이트 A **PASS**, 게이트 B **xfailed(strict, XPASS 아님)**. solid_volume 회귀 4/4 PASS.
- **최우선 가드**: dual_torus `sum|vol|/input_vol` = 0.9913 ± 0.02 유지 (area/vol 절대 재회귀 금지),
  grade B 유지, off-surface(void) area 불변.
- core/ 무변경 → cube/cylinder smoke 회귀 **불필요·금지** (mesh 미변경). bench 시간 ≤ 기존 +2%.
- max_boundary_skew 감소를 **요구하지 않음** (구조적 한계 — cure 는 다음 로드맵 몫, 정직 기준).

## 카드 시퀀스 위치

- "얇은 영역 all-surface flat-sliver topology-preserving 제거" 시퀀스 **4/4 (종결)**.
  FSL1 detector → FSL3 guarded flip(eligible 9, FAIL-미driver 확인) → **FSL4 known-limit 확정**.
- 실측으로 확정된 결론: dual_torus FAIL driver(61 coplanar wedge, max_bskew 2.94e7)는
  volume-only local op 의 근본 한계 — cylinder skew 44.9 와 동일 class.
- **다음 로드맵 항목(별도 시퀀스, 이 카드 아님)**: **"다중-body 얇은 형상 근본 재설계 —
  Garimella near-wall 내부점 삽입(offset ring)"**. 실측 근거: 내부 offset apex 로 bskew
  2.94e7→0.34 확인됨(cure 가능성 증명). cavity 재-tet + neg-vol/void/표면 guard 필요 →
  스켈레톤(내부점 후보 열거, default OFF)부터 다카드 분할. cylinder 44.9 와 공통 인프라.

## 혁신성 평가

- novelty 1 (신규 알고리즘 아님 — 한계의 정밀 특성화·게이트화. 단, 브리핑 전제(approach a)를
  실측 반증한 것이 실질 가치).
- rigor 3 (61 wedge 전수 위상 + 공면성 특이값 + normal-span 비 + 내부점 cure 실측 2.94e7→0.34,
  정확 기하 술어로 (a) 불가·(b) 유일 증명).
- impact 2 (FAIL driver 근본원인 확정 + #1 불변식 회귀-방지 게이트 + cure XPASS 경보 +
  로드맵 정조준 — 헛된 파라미터 sweep/무가드 카드 방지).
- 합 = 6 (≥5 충족). 정직한 종결 카드.
