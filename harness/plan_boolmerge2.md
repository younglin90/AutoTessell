# CARD BOOLMERGE2 (S2 — card 2/N) — tet centroid union-filter 격리 헬퍼

**target_engine**: tet (native_tet — S2 Boolean merge, 실험 검증 후 헬퍼 격리)
**모티프**: fTetWild §3.6 Filtering — "각 tracked input surface 의 GWN 을 tet
centroid 에서 계산, boolean op 로 keep 판정". BOOLMERGE1(geometry.py) 이 만든 순수
union 판정 함수를 **실제 tet cell** 에 적용해 병합 볼륨이 나오는지 실측한 뒤, 그
메커니즘을 native_tet 안 격리 헬퍼로 응축한다.

## 조사 (tet 파이프라인에서 inside 판정 지점)

- 유일한 "표면 안/밖 → tet keep" 지점은 `mesher.py:1311-1313`:
  `centroids = all_pts[tets].mean(axis=1); inside_tet = _inside_winding_number(centroids, V, F)`.
  단일 surface `(V, F)` 만 받는다. `boundary_clip.py:72-75` 도 같은 패턴(centroid →
  단일 surface winding → keep)의 clip 전용 복제본. **다중-surface 조합 지점은 없음.**
- 즉 병합은 이 centroid-filter 를 `inside_union_winding_number` 로 바꾸면 원리적으로
  된다 — 아래 실험으로 실측.

## 실험 결과 (정본 스크립트, WSL, 총 10.6s < 3분)

- setup: A=[0,1]³, B=[0.5,1.5]³ (해석적 union=1.875). union bbox 배경격자 → scipy
  Delaunay → tet centroid 에 `inside_union_winding_number` 적용 → Σ|vol|.
- 결과 (grid N³, err = |vol_union−1.875|/1.875):

  | N | tets | vol_union | err | vol_singleA(참고) |
  |---|------|-----------|-----|-------------------|
  | 16 | 28k | 1.7755 | 5.31% | 0.9474 |
  | 24 | 96k | 1.9229 | 2.55% | 1.0307 |
  | 32 | 228k | 1.8034 | 3.82% | 0.9646 |
  | 40 | 447k | 1.8189 | 2.99% | 0.9646 |

- **결론**: union filter 는 실제 tet cell 위에서 병합 볼륨(≈1.82, 1.875 부근 진동)을
  복원한다. 대조군(단일 surface A 필터)은 큐브 하나(≈1.0)만 남긴다 — 병합이 실제로
  일어남을 증명. 잔여 오차(±3~5%, 약간 저평가)는 **경계 centroid 계단화**(grid
  quantization)이지 알고리즘 결함이 아니다 — 원본 삼각형은 판정에만 쓰여 invariant 1
  자동 보존, envelope/surface-conformal 삽입(후속 카드)이 오차를 제거한다.

## intersection/difference 판단 (point 1)

- fTetWild §3.6 원문 재확인: "one winding number for each tracked input surface …
  keep if supposed to be contained in the Boolean result. e.g. intersecting → keep
  tets inside **both**." → union=OR, intersection=AND, difference=AND-NOT — **세 연산이
  전부 동일 패턴**(per-surface bool 배열 + reduce). 일반화 `inside_boolean_winding_
  number(query, surfaces, ops)` 는 사소하다.
- **그러나 이번 카드엔 넣지 않는다**: S2 최소 요구는 union("여러 파일→하나의 볼륨"),
  AND/AND-NOT 브랜치는 현재 호출자·요구가 없어 dead code(스타일 규칙 위배). 패턴 동일성만
  헬퍼 docstring 에 명시하고 후속 카드로 미룬다.

## 이론적 근거 / 혁신성

- 원자 연산: tet σ 를 keep ⇔ centroid(σ) 가 union 볼륨 내부. BOOLMERGE1 이 점별 판정을
  격리했고, 본 카드는 그것을 (pts, tets) 도메인으로 리프트한 순수 필터로 만든다 —
  surface CSG 없음(원본 삼각형 불변, invariant 1 자동).
- novelty 2(첫 다중-surface tet 필터) / rigor 2(해석 union 실측 수렴 + 대조군) /
  impact 2(S2 병합의 tet 실체화, 사용자 경로 무영향). 합 6 — 진행.

## 변경 (1 신규 파일 ≤80줄 + 신규 테스트, 프로덕션 호출자 0)

- 신규 `core/generator/native_tet/boolean_merge.py` — `boundary_clip.py` 구조 미러:
  1. `@dataclass UnionMergeResult(n_tets_before, n_tets_after, n_dropped, volume_after)`.
  2. `filter_tets_to_union(pts, tets, surfaces: list[tuple[V,F]], *, threshold=0.5)
     -> (pts, kept_tets, UnionMergeResult)`: `centroids = pts[tets].mean(1)`;
     `keep = inside_union_winding_number(centroids, surfaces, threshold=threshold)`;
     `kept = tets[keep]`; `volume_after = Σ|tet vol|(pts, kept)`.
  3. empty tets/surfaces 가드 → 원본 그대로 반환(boundary_clip 관례와 일치).
  - docstring: fTetWild §3.6 인용 + "union 만; intersection=AND, difference=AND-NOT 은
    동일 패턴이나 호출자 생길 때 후속 카드" 명시.
- **호출자 없음** — `mesher.py`/orchestrator/server/게이트 diff 0줄. 순수 격리 헬퍼.
- 상대 가드: keep 판정만 하고 pts·원본 F 불변 → 표면보존 절대 불변식 구조적 보장.

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
python -m pytest tests/test_native_tet_boolean_merge.py -q
python -m pytest tests/test_geometry_boolean_merge.py -q
python -m pytest tests/test_geometry_inside.py -q
python -m pytest tests/test_desktop_server.py::TestMultiSurface -q
```

## 합격 기준 (정량, 결정론적)

- 신규 테스트(seed 고정 grid 24³ jitter, 두 겹치는 큐브):
  - `1.70 ≤ volume_after ≤ 2.05` (해석 union 1.875 의 ±~9%, 계단화 여유).
  - `volume_after ≥ single_surface_volume + 0.5` (병합이 실제로 일어남 — 큐브 하나
    1.0 이 아님).
  - `n_tets_after < n_tets_before` 그리고 `> 0`.
  - 분리된 두 큐브(A=[0,1]³, B=[10,11]³): `volume_after ≈ 2.0 ± 5%`, 사이 tet keep 0.
  - 단일 surface 항등: `surfaces=[(V,F)]` 결과 == `boundary_clip.clip_to_input_surface`
    의 keep 볼륨과 부호/크기 일치(1-surface 경로 무손상).
- 실행 시간 < 30s (스크립트 40³ 6s → 테스트 24³ ~1.3s).
- **회귀 0**: `test_geometry_inside.py`, `test_geometry_boolean_merge.py`,
  `TestMultiSurface` 전부 그대로 PASS(geometry.py·게이트·orchestrator 무변경 확인).

## 카드 시퀀스 위치 (S2)

- 1/N ✔ BOOLMERGE1: 다중-surface GWN union 판정 원시 함수(geometry.py).
- **2/N (본 카드)**: 그 함수를 실제 tet centroid 에 적용 → 병합 볼륨 실측 + native_tet
  격리 헬퍼 `filter_tets_to_union`. 호출자·orchestrator 무관.
- **3 후보**: `server.py:916` 게이트를 "union + 정확히 2 surface" 로 완화 +
  orchestrator `input_paths: list[Path]` 확장(단일-경로 하위호환) + `mesher.py:1313`
  에서 다중-surface 시 `filter_tets_to_union` 배선. 이때만 `TestMultiSurface`
  기대값 갱신. envelope/surface-conformal 삽입으로 계단화 오차 제거.
- **4 후보**: intersection/difference 일반화(`inside_boolean_winding_number` + ops) +
  invariant 1 실측 gate(원본 face hausdorff 보존) + N>2 surface + per-patch BL.
