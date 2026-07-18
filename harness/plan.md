# CARD BETA2828 (beta2828) — BETA2826 smooth: evaluator-faithful skew non-worsening guard

**target_engine**: tet
**모티프**: fTetWild §3.5 smoothing 은 quality 를 악화시키면 안 된다 — accept 를 *실제* evaluator
metric 으로 판정 (Klingner 2008 §3.3 per-op monotone accept).

## 이론적 근거 (전부 이번 라운드 실측 — scoped stash A/B, 정본 스크립트)

- **문제 정의**: cylinder skew 280 의 원인은 flip 이 아니라 **BETA2826 locked-smooth 자체**다.
  A/B (scripts/smoke_native_cylinder.py, BETA2826 gate 를 scoped 로 OFF 후 mesher.py 복원 확인):
  - BETA2826 **ON**(현재): CYL skew=**280** · cube N500=**3.8** · N2000=**1.81**
  - BETA2826 **OFF**: CYL skew=**44.9** · cube N500=**25.7** · N2000=**10.0**
  smooth 는 cube 을 크게 개선(25.7→3.8, 10→1.81)하나 cylinder 는 악화(44.9→**280**).
  기전: interior AMIPS 이동이 owner-cell centroid 를 곡면 boundary face 로 밀어 normal_dist→0,
  boundary skew 폭발 (surface vertex 는 lock → wall_dev 0.000 유지). ⇒ 설계갈림길 **(C) 확정**.
- **핵심 아이디어**: BETA2826 은 *마지막* mutation(직후 disk write) → 이 블록 accept = **최종 판정**
  (BETA2827 이 못 지킨 필수조건 1 을 구조적으로 충족: 하류가 없다). accept 에 **evaluator 동일 공식**
  skew 비악화를 추가. smooth 중 topology 불변 → face-map 1회 build, `_pre_pts`/`_new_pts` 각각 평가.
  1. internal skew = native_checker.py:698-721 (cc=pts[tets].mean(1), fc=pts[face].mean(1),
     skew=|fc-proj|/|d|, d=cc_nbr-cc_own; own/nbr 순서·normal 부호 무관 = orient-free).
  2. boundary skew = native_checker.py:762-779 (skew=|fc-proj|/max(|normal_dist|,1e-30)).
  3. `skew_proxy = max(internal_max, boundary_max)` — evaluator max_skewness 와 방향 일치 보장.
- **레퍼런스**: core/evaluator/native_checker.py:698-721(internal),762-779(boundary);
  fTetWild(Hu 2020) §3.5; Klingner & Shewchuk 2008 §3.3. 현 블록 mesher.py:2081-2148.
- **혁신성**: novelty 1(guard hardening) · rigor 3(evaluator 공식 정확재현·reported metric 대비
  provably monotone·양끝점 A/B 실측) · impact 2(곡면 skew 6.2×↓, CFD 필수). 합 = **6**.

## 변경 (단일 파일)

- 파일: **core/generator/native_tet/mesher.py** (BETA2826 블록 ~2081-2148 + module-level helper 1개)
- 함수: `generate_native_tet` 내 BETA2826 accept 로직 / 신규 `_skew_proxy(pts, tets)`
- 핵심 (≤75줄):
  1. helper `_skew_proxy(pts, tets)`: tet 4-face → sorted-face→owner list dict 1회 build,
     internal(len==2)·boundary(len==1) 분리, 위 두 공식 벡터화, `max` 반환 (empty·1e-30 가드).
  2. BETA2826 안(n_iter=5 smooth 직후): `_sk_pre=_skew_proxy(_pre_pts, final_tets)`,
     `_sk_post=_skew_proxy(_new_pts, final_tets)`.
  3. `_accept` 에 `and _sk_post <= _sk_pre * (1.0 + 1e-6)` 추가. log 에 sk_pre/sk_post emit.
- 단조 가드: skew 악화(post>pre) 시 `_accept=False` → 기존 else 경로 `final_pts=_pre_pts` (revert).
  기존 `_no_inv`(부호비교 상대식 = 필수조건 2 이미 충족)·vol_ratio·surf_moved 가드 **그대로 유지**.
  flip(BETA2827) 은 도입하지 않음 — 원인(smooth) 을 직접 교정하므로 불요.

## 검증 명령 (unit_tester 가 그대로 실행 · Windows: PYTHONUTF8=1 PYTHONIOENCODING=utf-8, WSL python)

```bash
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 200 python3 scripts/smoke_native_cylinder.py
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 120 python3 scripts/smoke_native_tet.py
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 120 python3 scripts/smoke_native_tet.py 2000
timeout 90 python3 -m pytest tests/test_native_tet_solid_volume.py tests/test_native_tet_target_cells.py tests/test_native_tet_harness.py tests/test_native_tet_phaseA.py tests/test_flip_signed_validity.py -q
timeout 90 python3 -m pytest tests/test_cylinder_wall_fidelity.py -q   # 단독(스위트 플래키)
```

## 합격 기준 (validator)

- **CYL 부분성공**: smoke_native_cylinder skew **280 → ≤ 45** (예측 44.9, revert 로 pre-smooth 복귀),
  **wall_dev_max 0.000 유지**, cells≈1847, nonOrt ≤ +1°. "수백 이하" 목표 달성.
- **cube 회귀 금지**: smoke_native_tet N=500 skew ≤ 4.0 (현 3.8, smooth 유지=accept),
  N=2000 skew ≤ 2.0 (현 1.81); solid invariants 4종 전부 ok.
- **회귀 PASS**: 위 pytest 세트 (알려진 flaky 제외: phase_a, cylinder 스위트 간헐, TestTierGracefulFail 2건).
- **tet grade 불악화**: bench C=2/D=3, worst_mq ≥ 0.203 (guard 는 skew 악화 시에만 revert →
  smooth 이득 mesh 는 유지, grade 단조). bench 시간 ≤ base +15% (proxy 는 O(faces) 벡터화, <50ms).
- **maker 필수 로그 확인**: sk_pre/sk_post 를 cube·cylinder 양쪽에서 emit —
  cylinder: sk_post > sk_pre (revert 발화), cube: sk_post ≤ sk_pre (smooth 유지). 방향 어긋나면
  proxy 공식/부호 재점검 후에만 wiring (부분활성 규율).

## 카드 시퀀스 위치 (곡면 boundary-skew 시퀀스, 총 3장 예상 · 본 카드 1/3)

- **1/3 (본 카드)**: smooth 의 net-악화 차단으로 CYL 280→44.9 (부분성공, solid/fidelity-safe).
  BETA2827 flip 노선은 폐기(하류 재악화·필수조건 1 위배) — 본 카드가 근본원인(smooth)을 직접 교정.
- **다음 카드 후보(PASS 후) — BETA2829**: 잔여 44.9 의 flat cap-sliver(vol~1e-6, owner 자기-경계 근접)
  를 scale-relative signed 3-2 flip 으로 국소 제거하되 **BETA2826 이후(진짜 disk 직전)** 배치 =
  하류 없음 → 필수조건 1 자동충족 (설계갈림길 A 를 flip 에 적용).
