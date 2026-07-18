# CARD BETA2826 (cycle5) — surface-locked AMIPS smooth written to disk (pre-write Stage-4)

**target_engine**: tet
**모티프**: TetWild §3.2 op(4) vertex smoothing — 4-op 중 유일하게 inversion-safe 한 stage 를 단독으로, disk write 직전에 적용.

## 이론적 근거 (계측으로 확정 — 추측 아님)
- **왜 klingner_full_sweep 이 효과 0 인가 (질문 #1 답, 코드+계측 증명)**:
  P4C=0(하네스 측정 조건)에서 `_phase_bc_skip=False`(mesher.py:1341 은 P4C≠0 요구) 이고
  `_p4c_rewrote=False`. 따라서 **disk write 는 오직 line 2094 한 번** — sweep(4315)·GAP-SELF
  AMIPS(4402)·CFD AMIPS(4658) **전부 write 이후**라 in-memory 만 바꾸고 버려진다
  (post-write 재기록 4688 은 `_phase_bc_skip or _p4c_rewrote` 게이트로 P4C=0 시 미발화).
  → **disk 무반영 = 효과 0. 확정.**
- **왜 sweep 을 그냥 disk 로 보내면 안 되나 (질문 #2 답, 계측)**: sweep 은 accepted=True 로
  mean_q 0.296→0.361 개선하지만, 그 출력을 disk 로 쓰면 **skew 10.02 → 2.1e15 폭발**. 원인:
  op 별 계측 결과 split(inv=144)/flip32(inv=332)/flip44(inv=119+noncon 60) 이 전부
  **inverted/overlap tet 주입** — `flip.py` 검사가 `abs(vol6)>=1e-20`(부호 무시)이라 TetWild
  Invariant 3(no inversion) 위반. |V/ℓ³| quality 는 |vol| 기반이라 이를 못 본다.
  collapse 만 clean(inv=0). **즉 disk-reflection 은 지금 sweep 의 불량 출력을 막아주는 방패다.**
- **본 카드 핵심 (계측으로 검증된 유일 안전+유효 경로)**:
  4-op 중 **smooth(Stage 4)만 inversion-safe** (`amips.py:336` 이미 per-vertex det>0 가드).
  이걸 **모든 surface(경계) 정점 lock** 상태로 disk write **직전**에 적용:
  - 계측(cube/draft/N2000/P4C0): skew 10.018 → **2.03** (n_iter=5), on_area **6.000**,
    off_area **0.000**, vol **1.025**, n_degen **0**, surf 정점 max 이동 **0.0**, inv **0**,
    min_sv6 **9.2e-8>0**. n_iter 8/12/20 도 2.1~2.6.
  - 표면 완전 lock → 표면 fidelity 는 **구조적으로** 보존(경계 face 불변). cube/cyl 공히 안전.
- **레퍼런스**: Klingner 2008 §3.1 smart smoothing(min-quality 비감소 시에만); TetWild §3.2 op(4)
  + Invariant 3; `papers/01,02,03`. `amips.py:318 smooth_amips`, `mesher.py:2094 write`.
- **혁신성/적합성**: novelty 1(가드/배선 교정) rigor 3(단조·det>0·표면lock·부피가드 증명)
  impact 3(draft 임계 초과 → 임계 1/4). 카드 목적=측정 벽 돌파, 합 7.

## 변경 (단일 파일)
- 파일: `core/generator/native_tet/mesher.py`
- 위치: BETA2825 축퇴제거 블록 종료(line ~2079) 직후, `_prog("write",0.9)`(2081)·write(2094) **직전**.
- 핵심 (≤30줄, `if not _phase_bc_skip and final_tets.shape[0] > 100:` 안):
  1. **surface 정점 집합** (벡터화): 4 face/tet → `np.sort` → `np.unique(axis=0, return_counts=True)`
     → count==1 인 face(=tet 경계면) 정점 = `surf_ids`. (adjacency.py:108 boundary_faces 개념.)
  2. `pre_pts = final_pts.copy()`; `pre_abs = |signed_vol6(final_pts, final_tets)|.sum()`.
  3. `_, new_pts = smooth_amips(final_pts, final_tets, locked_vertex_ids=surf_ids, n_iter=5)`.
  4. **단조 가드** (revert 조건): `sv6_new = signed_vol6(new_pts, final_tets)`;
     accept 오직 `sv6_new.min() > 1e-12` **and** `|sv6_new|.sum()/pre_abs <= 1.03`.
     아니면 `final_pts = pre_pts` (topology 불변이라 tets 그대로).
  5. `log.info("native_tet_prewrite_locked_smooth", n_surf, vol_ratio, accepted)`.
- 이후 기존 write(2094) 가 개선된 final_pts 를 기록 → disk 반영.
- **금지 준수**: split/flip 미사용(inversion 회피), 임계·평가자·테스트 불변, P4C 미변경.

## 검증 명령 (unit_tester 가 그대로 실행)
```bash
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 AUTO_TESSELL_P4C_PYTETWILD=0 \
  python3 -m pytest tests/test_native_tet_solid_volume.py \
  tests/test_native_tet_target_cells.py tests/test_cylinder_wall_fidelity.py \
  tests/test_native_tet_harness.py tests/test_native_tet_phaseA.py -q
```

## 합격 기준 (validator)
1. **max_skewness 10.02 → ≤ 8.0** (계측 2.03, 큰 여유). 하네스 skew metric 하락이 주 성공조건.
2. **solid 4-게이트 전부 유지** (계측치): covers_input_surface on_area=6.000 /
   has_no_interior_voids off_area≤0.05 (계측 0.000) / mesh_encloses_true_volume vol≤1.05x
   (계측 1.025x) / has_no_degenerate_cells n_degen=0. **하나라도 깨지면 카드 실패.**
3. `test_cylinder_wall_fidelity`(표면 lock 으로 곡면 정점 불이동 → 보존),
   `test_native_tet_target_cells`(topology 불변 → cell 수 불변), harness/phaseA 유지.
4. bench 시간 ≤ 기존+15% (smooth n_iter=5 는 2340 tet 기준 ~1s; 5 fid +~5s).

## 회피 이유 (attempts_catalog AVOID 와 근본 차이 — 명시)
- AVOID "AMIPS smoothing BSP 직후(4회 fail)": 그건 (a) 구멍/축퇴 있는 BSP 직후 메쉬 위,
  (b) 표면 lock 부재/first-V=8 만 lock → 표면 이동으로 fidelity 파괴, (c) 출력이 disk 무반영.
  **본 카드는** (a) BETA2825 로 solid+축퇴0 된 메쉬 위, (b) **모든 225 경계정점 lock**(계측 surf
  이동 0.0), (c) **write 직전 배치로 disk 반영** — 세 지점 모두 반대. 근본적으로 다른 개입.
- split-dip 회피: 본 카드는 split 미사용(inversion 원흉). smooth 는 det>0+부피가드로 단조.

## 카드 시퀀스 위치 (총 4장 예상, 본 카드 = 1/4)
- **1/4 (본 카드)**: locked AMIPS smooth pre-write → skew 10→2 (즉시 목표 달성, solid-safe).
- 2/4: `flip.py` 부호검사 `abs(v)>=1e-20 → v>1e-12` (flip_edges_32/44, 5 site) —
  op-level inv 332/119→0, noncon 60→0. sweep 위상연산 재활성 전제.
- 3/4: `split_long_edges`(local_ops.py) inversion 제거 (inv 144→0).
- 4/4: 전 4-op sweep disk-reflection 배선 + envelope-guarded 경계 이동(worst tet 64% 경계접촉,
  계측) → fTetWild 급 worst-mq. (2~4 는 skew 이미 통과 후 품질 상한 확장.)
- **다음 카드 후보(본 PASS 후)**: BETA2827 = flip.py signed-validity fix (2/4).
