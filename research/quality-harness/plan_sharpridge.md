# CARD SHARPRIDGE1 — L2 Laplacian 스무딩 얇은-쉘 붕괴 상대가드

**target_engine**: tet (preprocessor L2 remesh — native_tet 커버리지 회복)
**모티프**: BETA2832/2833 상대 단조가드를 L2 `apply_laplacian_smoothing`으로 이식 — 자유경계 미고정 cotan 스무딩의 형상 붕괴 차단

## 형상/원인 실측 (P4C=0, 전 과정 실측 — 재검증 완료)

**형상**: `sharp_features_micro_ridge.stl` = 얇은 텐트/핀. 정점 6개(A(-2,0,0) B(2,0,0)
C(2,1,0) D(-2,1,0) E(0,.5,.05) F(0,.5,.1)). 바닥 사각형(2 tri) + 능선 지붕(4 tri).
extents [4,1,**0.1**], 18 open edge 전부 열림, non-watertight/open_boundary, euler 6.

**핵심 발견 — 원인이 task 가정(pymeshfix)에서 한 단계 아래로 이동함**:
1. **pymeshfix는 이미 revert 됨**(BETA2833 area guard 작동). 실측 트레이스:
   `pymeshfix_repaired 6->4` → `pymeshfix_area_guard_revert in_area=6.10 out_area=2.10`
   (2.10 < 0.5·6.10) → 원본 6-face 반환. 즉 task의 옵션 A/B(pymeshfix 가드)는 **이미 해결됨**.
2. gate 실패(non-watertight) → **L2 강제 remesh**. quadwild(실패)·vorpalite(rc=127, env)
   실패 → **pyACVD 384-face**. 여기까지 형상 완벽 보존: `haus(orig→pyACVD)=0.0`,
   z-range [0.0,0.1] 유지, area 6.16.
3. **범인 확정 = `apply_laplacian_smoothing`(iters=5,λ=0.5)**. 실측: pyACVD 후 스무딩 →
   **area 6.16 → 0.0**, z-range **[0.0,0.1] → [0.014,0.019]**(능선 완전 붕괴),
   `haus 1.52(rel 0.369)`. 원인: cotan Laplacian `(M-λL)⁻¹M`가 **자유경계 정점을
   미고정**(remesh.py:522-538 Dirichlet 제약 없음) → 얇은 쉘이 무게중심으로 수축.
4. 붕괴 쉘이 native_tet로 → `hausdorff_rel 13962`, grade D, plane_coverage 0, neg_vol 691.

**대조 실측(가드 반영 시 = laplacian revert → pyACVD 표면 입력, P4C=0)**:
`native_tet: hausdorff_rel=0.04596, n_cells=2262, grade D, mean_q 0.041` — polymesh 생성,
hausdorff 13962 → **0.046**(약 30만배 개선). thin open shell이라 grade는 D 유지(정직).

## 이론적 근거 (≤30줄)

- **문제 정의**: L2 remesh 목표는 표면 보존(#1 불변식) 하 품질 개선. cotan Laplacian
  smoothing `min ‖∇V‖²`은 자유경계에 Dirichlet 제약이 없으면 경계를 안쪽으로 당겨
  면적 단조 감소 → 얇은 형상(min-extent ≪ diag)에서 A(V)→0 붕괴. 현재 코드는 pre/post
  비교 없이 무조건 스무딩 결과를 채택(단조성 미보장).
- **핵심 아이디어**(BETA2832/2833 상대가드의 L2 이식):
  1. 스무딩 진입부에서 `pre_area = mesh.area`, `diag = ‖extents‖` 기록.
  2. 스무딩 결과 `post` 계산 후 **단조 형상가드**: `post.area < guard_frac(0.5)·pre_area`
     또는 `directed_hausdorff(pre→post)/diag > tol(0.05)` 이면 **`mesh`(pre) 반환**(revert).
  3. 정상 메쉬(cube/cylinder류)는 스무딩이 면적 보존 → 가드 no-op(무회귀).
- **수렴/안정성**: 가드는 순수 단조 revert — worst-case에서 pre 반환을 보장하므로 회귀
  불가. sharp_ridge는 post.area=0.0 < 0.5·6.1 에서 즉시 revert → pyACVD 형상 보존 표면 유지.
- **레퍼런스**: remesh.py:494 `apply_laplacian_smoothing`; BETA2833 area guard(repair.py:316);
  Desbrun 1999 "Implicit Fairing"(자유경계 제약 필요성); 표면보존 #1 불변식(MEMORY).
- **혁신성 평가**: novelty 1 / rigor 2(단조 면적+hausdorff 가드, 결정론) / impact 2
  (커버리지 붕괴 잔여 sharp-feature 클러스터 hausdorff 13962→0.046). 합 5 — 진행.

## 변경

- 파일: `core/preprocessor/remesh.py` (단일 파일)
- 함수: `apply_laplacian_smoothing` (line ~494)
- 핵심 변경 (≤30줄):
  1. 진입부(igl 계산 전): `pre_area = float(mesh.area)`; `diag = float(np.linalg.norm(mesh.extents)) or 1.0`.
  2. `result` 생성 후 반환 직전: `post_area = float(result.area)`.
  3. 방향 hausdorff: `_, d, _ = mesh.nearest.on_surface(result.vertices); hd = float(d.max())`
     (예외 시 hd=0 — 가드 무해).
  4. 단조 가드: `if post_area < 0.5*pre_area or hd > 0.05*diag: log.warning(
     "laplacian_shape_guard_revert", pre_area, post_area, hd_rel=hd/diag); return mesh`.
  5. 정상시 기존대로 `result` 반환.
- 단조 가드: pre(입력) vs post(스무딩) 면적+hausdorff 비교; 위반 시 입력 그대로 반환(revert).
  cube/cylinder/perforated/dual-torus는 L1 gate 통과로 **L2 자체 미진입** → 원천적 무회귀.

## 검증 명령 (unit_tester 가 그대로 실행, 각 ≤3분)

```bash
# 1) sharp_ridge 회복 (핵심, 정본 측정, ~10s)
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 170 python3 scripts/bench_native_tet_matrix.py \
  --stl tests/benchmarks/sharp_features_micro_ridge.stl
# 2) cube 회귀 금지 (~1s)
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 60 python3 scripts/smoke_native_tet.py 500
# 3) cylinder 회귀 금지 (정본 smoke)
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 90 python3 scripts/smoke_native_cylinder.py
# 4) perforated 재회귀 금지 (BETA2833 회복분 보존, ~3s)
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 90 python3 scripts/bench_native_tet_matrix.py \
  --stl tests/benchmarks/many_small_features_perforated_plate.stl
# 5) dual-torus 재회귀 금지 (~55s, 초과 시 기록만)
AUTO_TESSELL_P4C_PYTETWILD=0 timeout 170 python3 scripts/bench_native_tet_matrix.py \
  --stl tests/benchmarks/high_genus_dual_torus.stl
```

## 합격 기준 (validator 가 평가, 정량)

- **sharp_ridge (핵심)**: polymesh 생성(n_cells > 0), **hausdorff_rel < 5.0**(현 13962,
  실측 목표 ~0.046). grade는 무관(thin open shell — grade D 허용, 형상 보존이 목적).
  `laplacian_shape_guard_revert` 로그 1회 발생 확인.
  - **known-limit 허용**: grade가 A로 오르지 않아도 PASS. hausdorff 정상화 + 형상 보존이
    합격 조건. 완치 불가는 "매우 얇은 open shell → 체적메쉬 난제"로 정직히 xfail 기록.
- **cube 회귀**: smoke PASS 유지, area_ratio 1.00±0.01, cells 무붕괴(≥400 @N500).
- **cylinder 회귀**: 신규 회귀 금지 — area_ratio 1.00, cells·skew 기존과 동등(±5%).
- **perforated 재회귀 금지**: area_ratio ≥ 0.85(BETA2833 회복분), neg_vol=0.
- **dual-torus 재회귀 금지**: area_ratio ≥ 0.95, vol_ratio ≥ 0.95. 170s 초과 시 기록.
- **bench 시간**: sharp_ridge ≤ 15s(가드는 area 1회 + on_surface 1회, O(V) 저비용).
- **BL 영향 없음**: L2 전처리 단계 변경이라 BL 합격 분포 불변.

## 카드 시퀀스 위치

- 커버리지 붕괴 클러스터 시퀀스 **3/3** (1: BETA2832 dual-torus / 2: BETA2833 L1
  perforated / **3: 본 카드 — L2 laplacian sharp_ridge**). task 옵션 A/B(pymeshfix)는
  BETA2833 area guard로 이미 충족됨을 실측 확인 → 원인이 L2로 이동, 그 지점을 타격.
- **환경 이슈 분리 기록**: quadwild rc=139 / vorpalite rc=127(libgeogram.so.1.9.9 부재)는
  본 카드 범위 밖 인프라 이슈. pyACVD fallback이 형상을 보존하므로 본 가드만으로 충분.
- **다음 카드 후보**(본 카드 PASS 후): `SHARPRIDGE2_BOUNDARY_PIN` — `apply_laplacian_smoothing`
  자유경계 정점을 Dirichlet 고정(∂V pin)해 revert가 아닌 **경계 보존 스무딩**으로 격상
  (얇은 형상의 능선을 유지한 채 내부만 품질 개선 → grade D→C 시도). 가드는 안전망 유지.
