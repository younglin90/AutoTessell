# CARD THINSLIVER2 — 경계 슬리버 apex tangential-recenter (surface-locked, zero-inversion)

**target_engine**: tet
**모티프**: hex `_relax_boundary_sliver_interior` (mesher.py:684) 의 tet 이식 — 단,
inward-normal push 가 아닌 **tangential-recenter** 방향 (실측으로 방향 교체 강제).

## 최악 셀 실측 (P4C=0, target_cells=2000, harness/_thin_probe2.py, 각 <75s)

baseline (final polyMesh 재파싱, native_checker 공식 그대로):
- GLOBAL max skew: **internal=33.487, boundary=82.444 → report 82.444** (=driver 는 boundary).
  (C-ext checkmesh 는 58.83 로 다른 절대 스케일이나 driver 동일 — boundary sliver.)
- WORST boundary 셀 (상위 8): cell 3720 bskew=82.44 nd=1.32e-4 **n_surf_v=3/4 free=1**,
  이하 80.8/80.2/78.5/71.8/71.8/69.8… 전부 **n_surf_v 3/4, nd 1.1–1.4e-4, apex 1개만 자유**.
- 상위 30/30 이 정확히 free interior vert 1개(apex) 보유 → apex 이동 가능 후보.

## 이론적 근거 (핵심 — apex 는 trapped, 방향이 관건)

- **문제 정의(수식)**: n_surf_v=3/4 경계 셀에서 face centroid `fc`=표면 3정점 평균(고정),
  `cc=(3·fc+apex)/4` ⇒ `fc−cc=(fc−apex)/4`. 따라서
  **boundary_skew = |tangential(fc−apex)| / |normal(fc−apex)|** — apex 위치만의 함수.
  skew→0 은 apex 를 ray `{fc − t·nu, t>0}` 위로 옮기면 달성.
- **실측 3검(harness/_thin_probe2.py)**:
  1. NAIVE inward push(−nu, hex 방식): bnd 82.4→**2.9** BUT **inv=619** → mesher 의
     inversion 가드가 전량 revert = no-op. hex 방식 직이식은 tet 에서 무효.
  2. SAFE inward(per-vertex zero-inversion backtracking line-search): **82.4→82.4 (효과 0)**
     — apex 가 boundary sliver 와 near-coplanar interior sliver 사이에 **끼어(trapped)** −nu
     로 미소 이동도 인접 interior tet 을 뒤집음(lam=0).
  3. SAFE **tangential-recenter**(disp=α·[(fc−apex)−((fc−apex)·nu)nu], zero-inversion
     line-search): **82.4→77.1, int 33.5→33.2, inv=0, surf_moved=0** (α=0.7, iters=3).
     nd 를 안 키우고 fc 아래로 정렬하는 접선 이동만이 유일한 안전 lever.
- **핵심 아이디어**: 각 thin(|nd|<τ·h) 경계면 owner 셀의 free(non-surface) apex 를,
  그 면의 **접선 성분 residual** `(fc−apex)_⊥nu` 방향으로 α 만큼 이동(accumulate→평균).
  적용은 **정점별 backtracking line-search**(각 incident tet 의 signed vol6 부호 불변 &
  |vol6|>1e-14 유지하는 최대 lam∈{1,.7,.5,.3,.2,.1,.05,.02})로 inversion 원천 차단.
  최종 `_skew_proxy` 단조 accept/revert(BETA2826 패턴 그대로).
- **레퍼런스**: hex `_relax_boundary_sliver_interior`(native_hex/mesher.py:684, cylinder
  4160→45 검증); Garimella&Shashkov 2003 near-wall thickness recovery.
- **혁신성**: novelty 2 (boundary-skew-directed **접선** relax + 정점별 zero-inversion
  line-search; hex inward 방식이 tet 에서 실패함을 실측해 방향 교체) / rigor 3 (skew 폐형식
  유도 + NAIVE/SAFE-inward/SAFE-tang 3검 + 부호보존 line-search + 단조 accept) /
  impact 1 (**부분개선**: bnd 82.4→~77, verdict 여전히 FAIL — internal 33.5 ceiling +
  trapped apex 는 follow-up). 합 = 6 (≥5, 정직).

## 변경

- 파일: `core/generator/native_tet/mesher.py` (단일 파일).
- 신규 헬퍼 `_relax_boundary_skew_interior(pts, tets, n_surface, tau=1.0, alpha=0.7,
  iters=3)` (module-level, `_skew_proxy` 근처): ≤55줄.
  1. tets→face count map 으로 boundary faces(count==1) + `boundary_verts`(=surface-lock 집합).
  2. h = √(median boundary face area). thin 판정 `|nd|<tau·h`. free = 셀 verts∖boundary_verts.
  3. disp = alpha·tangential_residual(fc−apex). vertex→incident-tet map 으로 정점별
     zero-inversion backtracking line-search 후 이동. iters 회 sweep. stats(pre/post) 반환.
- 호출: BETA2826 locked-smooth 블록 직후(~line 2326), FSL3(~2327) 직전에 삽입(≤22줄):
  `not _phase_bc_skip and final_tets.shape[0] > 100` 게이트. `_skew_proxy` pre/post +
  surf_moved + vol_ratio 계산.
- 단조 가드(BETA2826 동일): accept 조건
  `_sk_post <= _sk_pre*(1+1e-6) and surf_moved <= 1e-9 and 0.97<=vol_ratio<=1.03`.
  위반 시 `final_pts = _pre_pts` 전량 revert. (inversion 은 line-search 로 이미 0 보장.)

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
timeout 175 python3 -m pytest tests/test_native_tet_thin_sliver.py -q
timeout 175 python3 -m pytest tests/test_native_tet_solid_volume.py -q
```
`tests/test_native_tet_thin_sliver.py` 에 gate 추가: naca polyMesh 재파싱 →
pure-python boundary skew(probe 공식, C-ext 비의존) 계산 → `assert bnd_skew <= 80.0`
(pre 82.44, 실측 post 77.1, 여유 margin). 기존 degen gate(<=15) 유지.

## 합격 기준 (validator 평가)

- **naca boundary skew 82.44 → ≤ 80** (gate; 실측 목표 77.1). 부분개선 — verdict 는
  여전히 FAIL(internal 33.5 ceiling + trapped apex). **정직 기준**: skew 축 partial win,
  verdict flip 아님(THINSLIVER1 precedent 동일).
- **#1 표면보존 불변**: surf_moved ≤ 1e-9 (boundary_verts 전면 동결). area_ratio 1.000±0.002.
- **inversion 0**: line-search 보장 + neg_vol_cells 비증가. vol_ratio 0.97–1.03.
- 회귀: `test_native_tet_solid_volume.py` PASS. cube/cylinder/dual_torus/perforated/
  sharp_ridge **회귀 절대 금지** — thin boundary sliver 없으면 acc 공집합 no-op,
  있어도 monotone accept/revert 로 무해(hex·BETA2826 검증된 안전 패턴). bench 시간 ≤ +5%
  (Python loop O(iters·bnd_faces·valence), naca <1s).

## 카드 시퀀스 위치

- "얇은/샤프 피처 슬리버" 클러스터 **2/2 (naca boundary skew 축)**. THINSLIVER1(degen)
  형제 카드. smoothing 으로 가능한 안전 상한(82→77)까지 — 실측으로 확정한 partial.
- **다음 카드 THINSLIVER3 후보**: trapped apex 는 smoothing 불가(실측) → **topology**.
  boundary-skew-keyed apex collapse(THINSLIVER1 collapse arm 을 skew-driver 셀로 확장,
  apex→surface keeper 병합으로 sliver stack 통째 제거) 또는 trailing-edge near-wall
  re-seed(Garimella). internal 33.5 ceiling 동시 해소 목표.
