# CARD BETA2827 (cycle6) — 곡면 cap-sliver 를 scale-relative 3-2 flip 로 제거 (곡면 축퇴 일반화)

**target_engine**: tet
**모티프**: BETA2825 Phase 1 (signed 3-2 flip) 의 gate 를 절대부피 → **scale-relative flatness** 로 일반화. fTetWild §3.4 / TetWild §3.2 (topology-preserving, no vertex move).

## 이론적 근거 (전부 계측 확정 — 추측 아님, 태스크 전제 일부 반증)
- **skew 4159 의 진짜 원인 = boundary skewness (내부 아님).** internal-face skew max = **5.0**.
  max_skewness=max(internal, boundary) 이고 boundary 성분이 **4159**. (native_checker.py:724
  `_compute_boundary_skewness`: `sk=|fc-proj|/normal_dist`, normal_dist=(면중심−소유셀중심)·n.)
- **원인 셀 = 곡면 벽에 눌린 flat cap-sliver.** owner 중심이 자기 boundary face 에 근접
  → normal_dist→0 → skew 폭발. 최악 셀 normal_dist **2.0e-5**, vol **1.31e-6**, flat=vol/maxe³≈0.
  분포: bskew>1000: 1셀, >100: 2, >10: 20, >4: 44 (긴 꼬리, 최악 1셀 지배).
- **왜 BETA2825 가 곡면에서 no-op 인가 (핵심).** BETA2825 gate `|sv6|<6e-9` ⇔ vol<1e-9.
  cylinder 최소 vol=**3.41e-8 > 1e-9** → `n_degen_pre=0` → **블록 전체 미발화**. 즉 태스크가 가정한
  "축퇴(vol~0) 셀 잔존" 은 틀림 — vol~1e-6 near-degenerate sliver 다. 옳은 판별은 **절대부피가 아니라
  곡률/스케일 불변인 flatness** f=|vol6|/maxe³ (BSP 전면에 무관, 곡면에도 그대로 성립).
- **flap 삭제(태스크 (a)) 도 부적합 — 계측 반증.** 최악 flat 셀들: all-4-boundary **0/30**,
  ≥2 boundary-face(flap) **0/30**. cap-sliver 는 boundary face 1개 + 내부로 향한 3면 → 삭제 시
  void 발생. 삭제 불가. **smooth(태스크 (b)) 도 불가**: 최악 bskew 상위 10셀 apex 전부
  boundary(lock)=True → interior-apex 만 fatten 해도 bskew **4159 그대로**. lock 안 깨고 유일하게
  가능한 건 **정점 불이동 flip**.
- **본 카드 핵심 = signed 3-2 flip 을 flatness gate 로 확장** (정점 0 이동, 부피·경계 exact).
  내부 edge (u,v) 가 정확히 3 tet 공유 + 대변삼각 xyz 가 u,v 분리 → {xyz,u},{xyz,v} 로 재삼각.
  gate `|sv6|<6e-9` → `|sv6|/maxe³ < 1e-3`, orient tol 절대 6e-9 → scale-relative `1e-6·bbox³`.
- **실측 (P4C=0, N=2000, 결정적 2-run 동일):**
  - CYL: n_flip **18**, bskew **4159.4 → 179.7**, inverted **0→0**, wall_verts_lost **0**, n_tets 1851→1833.
  - CUBE(회귀): n_flip 6, bskew **1.8 → 1.8** (무변), inverted 0, wall_verts_lost 0. 손상 없음.
  - 179.7 = "수백 이하" **부분 성공 달성**. 잔여(179.7=2nd sliver, apex lock)는 2-3 flip 필요(다음 카드).
- **레퍼런스**: BETA2825(dc5bbf0f) Phase 1; TetWild 2018 §3.2 op(2); Klingner 2008 sliver 3-2;
  `papers/01,03`. `native_checker.py:724`, `mesher.py:1930-2079`, `predicates.orient3d`.
- **혁신성**: novelty 2(절대→scale/곡률불변 gate 일반화) rigor 3(정점불이동·부피/경계 exact·
  inversion 0·bskew 단조가드·결정적) impact 3(곡면 skew 4159→180, 23×). 합 **8**.

## 변경 (단일 파일)
- 파일: `core/generator/native_tet/mesher.py` (BETA2825 블록, line 1930-2079 내부만 수정).
- 핵심 (≤60줄, Phase 1 만 일반화 / Phase 2 절대 gate 유지):
  1. **`_FLAT6_THR = 1e-3`, `_ORIENT_REL = 1e-6`** 상수 추가. `bbox_diag = norm(V.max0−V.min0)` 를
     Phase 1 앞에서 계산(현재 Phase 2 안에만 있음). `otol = _ORIENT_REL * bbox_diag**3`.
  2. **flat 헬퍼**(벡터화): `p=final_pts[tt]; v6=|sv6(final_pts,tt)|; maxe=6-edge max;
     flat=v6/maximum(maxe**3,1e-30)`.
  3. **block gate**(line 1945-46): `n_degen_pre` → `n_flat_pre=(flat(final_tets)<_FLAT6_THR).sum()`,
     `if n_flat_pre>0:`.
  4. **Phase-1 mask**(line 1958): `degen_mask = flat(work_tets) < _FLAT6_THR`.
  5. **orient**(line 1987-90): `tol=_DEGEN_V6` → `tol=otol` (2곳).
  6. **new-row validity**(line 2002): `if vol6<=_DEGEN_V6:` → 새 tet 의 `vol6/me**3 <= _FLAT6_THR: ok=False`
     (더 flat 한 tet 생성 거부). `me`=새 row 6-edge max.
  7. **Phase 2 (line 2025-2050) 절대 gate `_DEGEN_V6` 그대로** — 곡면 sliver 는 입력평면 비공면이라
     자연히 n_flap=0 (void 방지). 변경 금지.
- **단조 가드 강화** (line 2052-2077 확장): 기존 extra_area↓·area_coverage↓ 가드에 **bskew 단조** 추가.
  `_bskew_max(pts,tt)` 헬퍼(≤12줄): boundary face(count==1)+owner tet 중심 → `|fc−proj|/max(|nd|,eps)`.
  revert 조건에 **`bskew_post > bskew_pre*1.001` OR `sv6(work).min() <= 0`(inversion)** 추가. 하나라도
  악화면 `final_pts,final_tets = pre_pts,pre_tets`. (3e-3 에서 bskew 4159 재발 계측 → 가드 필수.)
- **금지 준수**: 정점 0 이동(fidelity 구조적 보존), 임계·평가자·테스트 불변, P4C 미변경, 삭제 미사용
  (Phase 1 은 재삼각), 외부 의존 0.

## 검증 명령 (unit_tester 가 그대로 실행)
```bash
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 AUTO_TESSELL_P4C_PYTETWILD=0 python3 scripts/smoke_native_tet.py 2000
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 AUTO_TESSELL_P4C_PYTETWILD=0 python3 scripts/smoke_native_tet_cyl.py   # 신설(아래)
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python3 -m pytest tests/test_native_tet_solid_volume.py \
  tests/test_native_tet_target_cells.py tests/test_native_tet_harness.py \
  tests/test_native_tet_phaseA.py tests/test_flip_signed_validity.py -q
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python3 -m pytest tests/test_cylinder_wall_fidelity.py -q  # 단독(스위트 플래키)
```
- **신설 `scripts/smoke_native_tet_cyl.py`** (smoke 패턴 복제, cylinder.stl, P4C=0): max_skewness +
  wall_dev(side r−0.5) 측정 → `assert skew < 300 and wall_dev_max <= 0.05` (계측 179.7 / 0.000, 여유).

## 합격 기준 (validator)
1. **CYL P4C=0: bskew 4159 → ≤ 300** (계측 179.7 = 부분 성공). PASS 면 완전 성공(비필수).
2. **wall_dev_max ≤ 0.05 유지** (계측 0.000 — 정점 불이동이라 구조적 보존).
3. **CUBE 회귀 금지**: smoke 2000 solid 4-게이트 + skew 무변(계측 1.8→1.8), inversion 0.
4. 회귀 스위트(solid_volume/target_cells/harness/phaseA/flip_signed) 전부 PASS. bench ≤ 기존+15%
   (flip 18~6개 국소, <1s).

## 필수 회귀 가드 / 알려진 결함
- 가드: `test_native_tet_solid_volume test_native_tet_target_cells test_cylinder_wall_fidelity
  test_native_tet_harness test_native_tet_phaseA test_flip_signed_validity`.
- 결함(쫓지 말 것): `test_cylinder_wall_fidelity` 스위트문맥 간헐 ~2/3 실패(A/B 무관 규명) → **단독 실행 판정**.
  `phase_a_improves_cube_boundary` 플래키. `test_generator.py::TestTierGracefulFail` pristine 실패.

## 예상 부작용
- CUBE 에서 3-2 flip 6개 추가 발화(scale-relative gate 가 vol>1e-9 flat sliver 포함) — 계측상
  bskew·solid 무변, inversion 0. n_tets 소폭 감소(2346→2340). CYL n_tets 1851→1833.
- Phase 2 무변(곡면 n_flap=0 유지). BETA2826 smooth 는 이후 실행, boundary-lock sliver 불변.

## 카드 시퀀스 위치 (곡면 자립 시퀀스, 총 3장 예상 · 본 카드 1/3)
- **1/3 (본 카드)**: scale-relative 3-2 flip → CYL bskew 4159→180 (부분성공, solid/fidelity-safe).
- 2/3: 잔여 boundary-lock cap-sliver 를 **signed 2-3 flip**(Klingner sliver removal)로 제거 →
  bskew 180→수십. `flip.py` signed-validity(ed56fd31) 이미 확보 전제, per-flip min_q 가드.
- 3/3: CYL verdict PASS 마감 (skew≤threshold) — 필요 시 interior-apex 50셀 targeted smooth 병행.
- **다음 카드 후보(본 PASS 후)**: BETA2828 = signed 2-3 flip for residual cap-slivers (2/3).
