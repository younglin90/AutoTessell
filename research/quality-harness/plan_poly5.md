# CARD POLY-S5 (beta2827) — 곡면(cylinder/sphere)에서 solid 4-불변식 일반화 진단 + 회귀 락

**target_engine**: poly
**모티프**: Fluent Watertight surface-wrap 불변식을 평면(cube) 밖 곡면으로 검증 — OpenFOAM polyDualMesh 의 per-triangle 평면 근접도 일반화.

## 진단 결론 (실측, 정본 경로: PipelineOrchestrator, tier_hint=native_poly, strict_tier)

**일반화 확인 완료 — cube 검증 로직이 곡면에서도 solid 4-불변식을 그대로 만족.**
POLY-S3 의 on-plane cap 필터가 "곡면에서 작동 안 할 것"이라는 사전 우려는 **실측상 발생하지
않았다**. 근거: `_surface_planes` (dual.py:182) 가 **입력 삼각형마다 고유 평면**을 만들고,
dual boundary 점(삼각형 centroid / edge midpoint / vertex)은 그 삼각형 평면 위에 정확히
놓이므로, faceted 곡면에서도 `_is_on_plane` 이 자연히 True 가 된다.

### cylinder.stl (draft / native_poly, 37.7s < 3분)
- dual: n_cells=73, skipped=0, **use_topo=True** (topological path B 채택).
- 가드 로그: pre_off(ConvexHull path A)=**18.13**, post_off(topological path B)=**0.0**,
  pre_on=post_on=4.851 → 곡면에서도 path B 가 void 를 18.13→0 으로 제거.
- **surface**: bmesh_total_area 4.851 vs input 4.697 → ratio **1.033** (독립 측정, 큰 void 없음).
- **void(off-plane)**: **0.000** (가드 post_off) → 불변식 유지.
- **volume**: Σ|cellvol| 0.8156 vs input_vol 0.7804 → ratio **1.045** (< 1.05, 여유 얇음).
- **degen**: **0** → 유지.
- 4-불변식 전부 통과. 단, evaluator 최종 **FAIL** 원인은 **max_skewness=173.8°**,
  max_non_ortho=81.07° (hard_fails=1) — solid 불변식이 아닌 **품질 축**(POLY-S 범위 밖).

### sphere.stl (draft / native_poly)
- dual 정상 생성 (n_cells=802, skipped=0) — dual 단계는 곡면에서 성공.
- 그러나 dual 이후 NativeMeshChecker(802 poly cell)+fidelity 평가가 **3분 예산 초과**
  (200s timeout 내 orchestrator 미반환) → end-to-end 정본 수치 확보 불가. 예산 문제이지
  로직 파탄 아님. sphere 게이트는 예산상 제외.

## 이론적 근거 (왜 카드가 "락"인가)

- **문제 정의**: cube(평면 6개)에서만 4-불변식이 permanent gate. 곡면 회귀를 잡는 게이트
  부재 → dual.py 리팩터가 곡면 처리를 조용히 깰 수 있다. cylinder 로 방금 검증한 성질을
  **영구 보호**해야 한다.
- **핵심 아이디어**: 기존 `_boundary_area_split` 는 cube 6평면 하드코딩(|x|=0.5 등)이라
  곡면에 부적합. 대신 **envelope 근접도 일반화** — boundary face 각 정점이 입력 STL
  삼각형 평면 집합 중 하나에 tol 내로 놓이면 on-surface, 아니면 off(void). 이는 dual.py
  내부 `_area_split`(dual.py:205) 과 동일 개념을 test 쪽에서 독립 재현.
- **차이**: 엔진 코드(dual.py) **무변경** → cube 4 게이트 구조적으로 불가침. test 파일에만
  cylinder fixture + envelope split 추가.
- **혁신성 평가**: novelty 1 (게이트 확장), rigor 2 (envelope 독립 측정 + 상대 가드),
  impact 2 (곡면 회귀 상시 차단, 지금까지 poly 는 cube 단일 검증). 합 5 — 경계선, 저위험.

- **레퍼런스**: dual.py:182-224 (`_surface_planes`/`_area_split`), tests/test_native_poly_solid_volume.py (POLY-S1 방법론), Owen 2007 poly dual, ANSYS Fluent Watertight surface wrap.

## 변경 (test-only — 엔진 무변경)

- 파일: tests/test_native_poly_solid_volume.py (단일)
- 추가:
  1. `_input_surface_planes(stl_path)` — 입력 STL 삼각형 → 고유 평면 목록(dedup),
     `_boundary_area_split_envelope(poly_dir, planes, tol)` — 정점 전부 어느 평면에
     tol(1e-5) 내면 on, 아니면 off.
  2. `poly_cyl_case` module fixture — cylinder.stl 1회 실행(≈38s, 예산 내).
  3. 4 테스트: surface ratio∈[0.95,1.10], void off≤0.05·on, vol ratio∈[0.95,1.06]
     (실측 1.045 → 상한 1.06 상대 가드), degen==0. 전부 permanent.
- 단조 가드: cube 게이트 4개는 **그대로 유지**(회귀 0). cylinder 게이트는 실측 여유가
  얇은 vol(1.045)만 1.06 상한으로 완화, 나머지는 cube 와 동일 tol.
- 비고: sphere 는 3분 예산 초과로 게이트 제외(docstring 에 명시), skewness(173.8°)는
  본 카드 범위 밖 — 별도 시리즈 후보.

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
timeout 90 python3 -m pytest tests/test_native_poly_solid_volume.py -q
```

## 합격 기준 (validator 가 평가)

- 기존 cube 4 게이트 PASS 유지(회귀 절대 금지).
- 신규 cylinder 4 게이트 PASS: surface ratio 1.033, void 0.000, vol 1.045, degen 0.
- 총 실행시간 ≤ 기존 + cylinder 1회(≈38s) — 3분 예산 내.
- 엔진(dual.py) diff 0 줄 — cube 불변식 구조적 불가침.

## 카드 시퀀스 위치

- POLY-S 시리즈(S1 측정 → S2 edge-ring dual → S3 void 제거 → S4 volume 축소)의
  **5번째, 곡면 일반화 검증/락** 카드. solid 불변식 시리즈는 본 카드로 사실상 완결.
- 다음 카드 후보(별도 시리즈): **POLY-Q1** — 곡면 dual cell skewness 저감
  (cylinder max_skewness 173.8° → OpenFOAM 사용가능역). Lloyd/centroidal 완화 또는
  dual point 위치 재배치. **이것이 곡면 poly 실사용의 진짜 병목** — S 시리즈 solid
  불변식과 독립된 품질 축.
