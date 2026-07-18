# CARD BOOLMERGE1 (S2 — card 1/N) — per-input GWN union 판정 원시 함수

**target_engine**: core/utils (A-1 Surface input — S2 Boolean merge 착수)
**모티프**: S1(bb22d14d)이 다중 표면 업로드/추적을 완성했으나 병합은 게이트로 차단
중(`server.py:916-936`). 게이트를 풀거나 orchestrator를 다중-입력화하는 게 아니라,
fTetWild §3.6의 핵심 수식 — "per-input surface 별 GWN을 독립 계산 후 boolean 조합" —
을 격리 함수로 만들고 합성 도형(교차 큐브)으로 실측 검증하는 게 첫 단추다.

## 조사 근거 (실측/원문)

1. S1은 병합을 시도한 적이 없다 — surfaces는 디스크상 독립 파일, orchestrator는
   여전히 단일 `input_path`(`core/pipeline/orchestrator.py:81`)만 받는다.
2. 게이트: `server.py:916-936`, `len(surfaces)>=2`면 orchestrator 호출 없이 즉시
   실패 처리 + 메시지 전송. `TestMultiSurface::test_two_surfaces_generation_rejected`
   / `test_single_surface_not_gated`로 고정됨 — 이번 카드는 무변경.
3. `_final_validate`(BETA2832, `pipeline.py:766-844`)는 **단일 STL 내부**의 disjoint
   컴포넌트 보존(상대 면적가드)이다. S2는 **여러 파일**을 다루므로 입력 형태가
   다르다 — 재사용 불가, 방법론(상대가드·표면보존 절대)만 계승.
4. `core/utils/geometry.py::inside_generalized_winding_number(query, V, F)`는
   **단일 surface 전용**. `native_tet/mesher.py`가 9곳에서 사용하지만 전부
   1-surface 시그니처. 다중 surface 조합 함수는 존재하지 않음 — 이게 빈 자리.
5. fTetWild §3.6 원문(`papers/md/02_hu_2020_ftetwild.md:487-491`): 각 입력 surface의
   provenance 를 추적, per-surface GWN을 독립 계산 후 boolean 결합으로 tet 채택
   여부 결정. **surface-level 교차/클리핑 없음** — volume-level 판정.

## 이론적 근거

- 병합의 원자 연산은 "점 p가 병합 볼륨 안에 있는가"라는 점별 판정 함수다. 각
  `(V_i, F_i)`에 대해 독립적으로 `inside_generalized_winding_number`를 평가(서로의
  삼각형을 전혀 참조하지 않음 → surface CSG 아님, invariant 1 자동 보존: 어느 입력
  표면도 변형되지 않는다), N개 bool 배열을 op별 결합: union=OR, intersection=AND,
  difference=AND NOT. 카드 1은 **union만**(S2 문구 "여러 파일→하나의 볼륨" 최소 요구).
- surface-level CSG(예 libigl mesh_boolean)는 교차 곡선을 계산해 표면 자체를
  재구성하므로 경계 근방 삼각형이 원본과 달라져 invariant 1을 위협한다. GWN 방식은
  원본 삼각형을 건드리지 않고 볼륨 판정에만 쓴다 — 결과 표면이 원본과 정확히
  일치하려면(=invariant 1) tet 삽입 단계에서 원본 삼각형이 tracked-surface로 삽입돼
  있어야 하는데(fTetWild 방식), 그건 **이후 카드**(orchestrator 다중-입력 배선)
  범위다. 이번 카드는 그 전 단계인 순수 판정 함수만 격리 검증한다.
- 혁신성: novelty 2(첫 다중-surface 판정 원시 함수) / rigor 2(합성 도형 실측 + 기존
  GWN 단위테스트 패턴 재사용) / impact 2(S2 전체의 최소 지반, 사용자 경로 무영향).
  합 6 — 진행.

## 변경 (1파일 + 신규 테스트)

- `core/utils/geometry.py`에 `inside_union_winding_number(query, surfaces:
  list[tuple[np.ndarray, np.ndarray]], *, threshold: float = 0.5) -> np.ndarray`
  추가: `mask = OR_i inside_generalized_winding_number(query, V_i, F_i, threshold)`.
  빈 리스트 → 전부 False(기존 empty-mesh 관례와 일치). docstring에 fTetWild §3.6
  인용 + "union만, intersection/difference는 후속 카드" 명시.
- **orchestrator/server/게이트/mesher.py 무변경** — 회귀 불가능.
- 신규 테스트: `tests/test_geometry_boolean_merge.py` (기존
  `test_geometry_inside.py::_unit_cube_mesh()` 헬퍼 재사용/평행이동).

## 검증 명령

```bash
python -m pytest tests/test_geometry_inside.py -q
python -m pytest tests/test_geometry_boolean_merge.py -q
python -m pytest tests/test_desktop_server.py::TestMultiSurface -q
```

## 합격 기준 (정량, 합성 도형)

- **겹치는 두 큐브** A=[0,1]³, B=[0.5,1.5]³ (해석적 union=1.875, 교집합=0.125):
  grid/Monte-Carlo(≥50k) 샘플 union 판정 부피가 해석값 대비 **±3%** 이내.
- **분리된 두 큐브** A=[0,1]³, B=[10,11]³: 각 내부 점 inside, 사이 점([5,5,5]) outside
  — 다중-파일 케이스에서도 body 분리 보존(단일-STL dual_torus의 파일-레벨 유사물).
- **단일 surface 항등원**: `surfaces=[(V,F)]` 하나일 때
  `inside_union_winding_number`가 `inside_generalized_winding_number(query,V,F)`와
  정확히 일치 — 향후 게이트 완화 시 1-표면 경로 무손상 보장.
- **회귀 없음**: `test_geometry_inside.py` 전체 PASS, `TestMultiSurface` 19개 그대로
  PASS(게이트 미변경 확인).

## 카드 시퀀스 위치 (S2, 계획)

- **1/N (본 카드)**: 다중-surface GWN union 판정 원시 함수 — 격리, 게이트/orchestrator
  무변경.
- **2 후보**: intersection/difference 추가 + 순수 판정 함수를 tet centroid 필터로
  연동하는 실험(native_tet 배경격자에 2-surface 합성 도형 직접 통과, 실제 tet volume
  측정).
- **3 후보**: `server.py:916` 게이트를 "union + 정확히 2 surface"로 좁혀 완화,
  orchestrator에 `input_paths: list[Path]` 확장(단일-경로 하위호환 유지) — 이
  단계에서만 `TestMultiSurface` 게이트 테스트 문구/기대값 업데이트.
- **4 후보 이후**: invariant 1 실측 gate(병합 후 각 원본 표면 face가 결과 표면에
  그대로 보존되는지 — envelope/hausdorff 가드) + N>2 surface, per-patch BL 연동
  (B0 patch ontology와 공유).
