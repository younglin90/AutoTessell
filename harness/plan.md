# CARD BETA2821_POLY_SELF_INTERSECT_DETECT (beta2821) — Voronoi cell self-intersect detector (skeleton, default OFF)

**target_engine**: poly
**모티프**: cfMesh polyhedral quality pass / OpenFOAM polyDualMesh `checkMesh -allTopology` self-intersect 감지 — extreme topology 의 degenerate ridge / collinear vertex 식별.

## 이론적 근거 (≤30줄)

- **문제 정의**:
  - 현 native_poly: extreme tier (knot, gear, sharp-feature) 에서 Voronoi cell 의 ridge 가
    near-degenerate (3 collinear vertex) 또는 ridge intersect 자기-교차 → cell volume sum 은
    양수지만 face plane 이 self-intersect → checkMesh skewness/non-ortho 부풀림 → grade B.
  - bench: 20-mesh 중 3개 (extreme tier) 가 grade B (큰 plan: poly A=17/20).
- **본 카드 핵심 아이디어 (skeleton-only)**:
  1. 신규 helper `_detect_cell_self_intersect(cell_faces, points, *, eps)` 추가:
     - 각 face 의 vertex 가 ≥3 이며 non-collinear (cross-product norm > eps) 인지 검사.
     - face pair 의 plane 이 (n·d≈0, distance≈0) 이며 vertex 가 서로의 face 내부에 있으면 SI 후보.
     - 결과: `(n_collinear_face, n_si_pair)` int 튜플 반환.
  2. **caller 추가하지 않음** — detect-only helper, 호출 site 0개.
  3. env gate `AUTO_TESSELL_POLY_SI_DETECT=1` 시 향후 활성화 예정 (현 카드는 placeholder).
  4. NativeVoroPolyResult 에 `n_self_intersect_cells_post: int | None = None` 필드만 신규 (default None).
  5. 단조 가드: helper 미호출 → 기존 path 100% 무영향. 회귀 0 위험.
- **레퍼런스**:
  - OpenFOAM `polyDualMesh/checkMesh.C` self-intersect topology check.
  - cfMesh `polyMeshGenChecks::checkSelfIntersection`.
  - Owen 2007 "Polyhedral Meshing" §4 quality cleanup.
- **혁신성**: novelty=2 (Voronoi cell 단위 SI detector — 기존 surface SI 와 별개) /
  rigor=2 (eps 기반 collinear + plane intersect 단조 정의) /
  impact=2 (다음 카드 BETA2822 의 repair caller 진입점). 합=6.

## 변경

- 파일: `core/generator/native_poly/voronoi.py` (단일 파일)
- 추가:
  1. `_detect_cell_self_intersect(cell_faces, points, *, eps=1e-12) -> tuple[int, int]` (~30줄, line ~735 근처 _ccw_sort_face_vertices 옆).
     - face 별 collinear 검사 (cross-norm < eps 면 +1).
     - face pair 의 normal 이 거의 평행 (|n1·n2| > 0.9999) 이며 plane d 차이 < eps 면 +1.
     - 호출되지 않음 (skeleton).
  2. `NativeVoroPolyResult` dataclass 에 `n_self_intersect_cells_post: int | None = None` 1줄 추가 (line ~216 근처).
- 단조 가드: helper 미호출 → 기존 모든 path 무영향. dataclass 기본값 None → 직렬화 영향 없음.
- 변경 ≤50줄.

## 검증 명령

```bash
timeout 90 python3 -m pytest tests/test_native_poly.py tests/test_native_poly_dual.py tests/test_native_poly_harness_edge.py -q
```

## 합격 기준

- 회귀 PASS (3개 native_poly 테스트 100%)
- syntax 무오류 (helper import 가능성 검증: `python3 -c "from core.generator.native_poly.voronoi import _detect_cell_self_intersect"`)
- bench 시간 ≤ 75s (poly bench 영향 0, helper 미호출)
- poly grade A ≥ 5/5 monotone (small bench)
- env `AUTO_TESSELL_POLY_SI_DETECT` 미설정 시 baseline 100% 재현
- NativeVoroPolyResult 직렬화 (dict / asdict) 호환

## 카드 시퀀스 위치

- P1.2 poly self-intersect extreme repair 시퀀스 1/3 카드.
- 다음 카드 후보:
  - BETA2822_POLY_SI_DETECT_CALLER — generate_native_poly_voronoi 종료부에 helper 호출 + log only (env ON)
  - BETA2823_POLY_SI_REPAIR — collinear face vertex merge / SI cell collapse (env ON, monotone guard)
- 최종 목표: poly grade A 17/20 → 20/20 (큰 bench).
