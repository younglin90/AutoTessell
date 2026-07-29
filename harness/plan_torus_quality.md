# CARD BETA2833 (FSL1) — all-surface flat-sliver detector (boundary-skew debt)

**target_engine**: tet
**모티프**: fTetWild §3.4 topology-preserving sliver removal (drop 금지 대체) — void-free 로 유지된 슬리버 부채의 정밀 특성화

## 재현 조건 (실측, 3분 이내)

- **정본 N = 600** (target_cells=600). N=2000 은 orchestrator rebudget 루프로 210s+ →
  대신 `generate_native_tet` **직접 호출**(rebudget/BL 우회) 로 44s 에 동일 결함 재현.
- 재현 결과 (직접 호출, P4C=0):
  - `max_boundary_skew = 2.94e7` (N=2000 의 2.2e6 과 동일 계열 — 재현 확정). max internal skew 는 정상.
  - FAIL 을 만드는 셀은 **단 2개**(tet 6056: bskew=2.94e7, tet 731: 6.5e5).
- **정본 재현 명령** (maker 가 baseline 확인용으로 실행, ~44s):
  ```bash
  AUTO_TESSELL_P4C_PYTETWILD=0 timeout 120 python3 -c "import numpy as np,tempfile;from pathlib import Path;from core.analyzer.file_reader import load_mesh;from core.generator.native_tet.mesher import generate_native_tet;m=load_mesh(Path('tests/benchmarks/high_genus_dual_torus.stl'));r=generate_native_tet(np.asarray(m.vertices,float),np.asarray(m.faces,np.int64),Path(tempfile.mkdtemp())/'c',target_cells=600);print('grade',r.quality_grade,'ncells',r.n_cells)"
  ```

## 최악 셀 실측 (근본원인)

- 최악 tet 6056: 4정점 **전부 surface vertex** (idx<2047), apex_offplane_dist=9e-9 → **4점 공면**.
  vol=6.1e-11 (neg_vol/degen gate 1e-20 통과), min_dihedral=180°, aspect=8.8e7, q(edge)≈0.
- 결정적: `normal_dist`(경계면 skew 분모, `native_checker._compute_boundary_skewness`
  line 773-776) = **2.3e-9** → skew = tangential / normal_dist 가 천문학적으로 폭발.
  즉 셀 무게중심이 벽면과 거의 공면. cylinder BETA2829 flat-cap 과 **동일 축**.
- 형상: dual_torus 는 z∈[-0.5,0.5]·x∈[-2.5,7.5] 의 **얇은 워셔** → 얇은 gap 을 tet 분할하면
  4 surface 정점이 공면인 flat sliver 발생. 6056/731 은 **2 boundary + 2 internal face**
  (벽 두 면에 끼인 wedge).

## 왜 기존 인프라(drop/filter)가 안 걸러내나 (핵심 답)

- **걸러낸다(detect). 다만 제거를 안 한다.** `drop_extreme_slivers`(dih<0.5° or aspect>1e4)
  와 `filter_slivers`(q<0.002 bnd) 는 이 셀들을 **전부 flag** (실측 frac=1.00).
- 제거 안 하는 이유는 **`void_free=True`**(BETA2822/2832) — 내부 tet 삭제 시 그 face 가
  입력 표면에 없는 void 벽이 되어 방금 복구한 **area/vol=1.010 이 깨진다**. 이 프로젝트의
  고전 함정. 즉 결함은 "미탐지"가 아니라 "제거 경로 부재"다.
- 실측한 제거 경로 후보:
  - vertex relocation: 4정점 전부 surface-locked → 이동 불가 (시뮬레이션 n_moved=0, skew 불변).
  - drop: void → area/vol 파괴 (금지).
  - 2-3 flip: **중간 flat(q≈0.009) 슬리버 10/12 는 valid**, 그러나 **최악 6056/731 은
    union 비볼록으로 invalid**(2-3 flip 후 tet 역전). → 최악 core 는 별도 다-tet 연산 필요.

## 본 카드 (시퀀스 #1 — detector 스켈레톤, mesh 불변)

- 파일: `core/generator/native_tet/validate.py` (슬리버 로직 상주지, 단일 파일)
- 함수(신규): `flat_allsurf_sliver_candidates(pts, tets, n_surface_vertices, *,
  q_flat=0.01, bskew_thresh=4.0) -> dict` (skeleton, **no caller, default OFF**)
- 핵심 변경 (≤60줄):
  1. all-surface mask = `(tets < n_surface_vertices).all(1)`; flat = `q_edge < q_flat`
     (q_edge = 8.48·|V|/edge_max³, filter.py 와 동일 공식 재사용).
  2. face→owner 인접(sorted-key bincount) 으로 각 후보 tet 의 (n_internal_faces,
     n_boundary_faces) 분류 + 2-3 flip 유효성(공유 internal face 이웃과의 3-tet
     signed-vol 동부호) 판정.
  3. 각 후보의 boundary-face skew 기여치(normal_dist 재현식) 계산 → dict 반환:
     `{n_cand, n_flip_eligible, n_core_unflippable, max_bskew, worst_tet}`. mesh 미변경.
- 단조 가드: **읽기 전용**. tets/pts 반환 없음, 어떤 caller 도 없음 → solid 4대 불변식
  (surface 6.0/void 0/vol 1.0/degen 0) 및 area/vol=1.010 이 구조적으로 불변.

## 검증 명령 (unit_tester 가 그대로 실행, 각 3분 이내)

```bash
timeout 90 python3 -m pytest tests/test_native_tet_flat_sliver_detect.py -q
```
(신규 test: (a) 합성 4-공면-surface tet → n_cand≥1·flag; (b) 정사면체 → n_cand=0;
 (c) 3-internal-face flat → flip_eligible=True, 2-boundary wedge → False.)
회귀:
```bash
timeout 170 python3 -m pytest tests/test_native_tet_solid_volume.py -q
```

## 합격 기준 (validator 평가)

- 신규 detector unit test + 회귀 PASS.
- **mesh 불변 증명**: cube/draft/N=2000 solid 4대 불변식 pre==post (helper 미호출 → 자명).
- dual_torus grade/coverage 불변 (area/vol=1.010 유지 — 절대 회귀 금지).
- cube/cylinder smoke 회귀 측정 **불필요·금지** (mesh 미변경 카드).
- bench 시간 ≤ 기존 +2% (helper 미호출).

## 카드 시퀀스 위치

- "얇은 영역 all-surface flat-sliver 의 topology-preserving 제거" 시퀀스 **1/4**.
- #2: mesher VVV-line 진단 hook (gate OFF→ON, 실주행 per-fid evidence, mesh 불변).
- #3: flip-eligible 부분집합만 **guarded 2-3 flip** (post: min_q 비감소 + neg_vol=0 +
  boundary face 미파괴 + 영향 boundary-skew 비증가), default OFF→ON. flat sliver 제거.
- #4: 2-boundary-face core(6056/731) — surface-edge 보존 다-tet 연산 or known-limit 확정.
- 다음 카드 후보(본 카드 PASS 후): **BETA2834 FSL2 — VVV-line 진단 hook 활성**(evidence-only).

## 혁신성 평가

- novelty 2 (generic dih/aspect 와 구분되는 all-surface 공면 + flip-eligibility 특성화,
  void-free 유지 부채를 정조준).
- rigor 2 (정확한 기하 술어 + mesh-불변 구조적 단조).
- impact 2 (FAIL driver 2셀 정확 특정 + tractable 부분집합 정량 → #3 flip 카드의 근거).
- 합 = 6 (≥5 충족).
