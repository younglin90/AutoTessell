# CARD POLY-S2 (beta2823) — tet→dual interior conformity via topological edge-ring faces

**target_engine**: poly
**모티프**: OpenFOAM `polyDualMesh` / Owen 2007 "Intro to Polyhedral Meshing" — dual face per
interior tet EDGE (ordered centroid ring), not per-cell ConvexHull.

## 파이프라인 구조 (실측 확인)

`tier_native_poly._runner` (bl_layers=0, cell_budget=0 → harness 경로,
tier_native_poly.py:57) → `run_native_poly_harness` (harness.py:140) →
`generate_native_tet` → `tet_to_poly_dual` (dual.py:179). dual 이 polyMesh 를 직접 write.
dual 알고리즘: 각 input vertex v_in 마다 (tet centroid + boundary-face centroid +
boundary-edge midpoint + v_in) 의 **독립 ConvexHull** 로 cell 을 만들고(dual.py:264-334),
face 는 `tuple(sorted(f))` **정확 정점집합 일치**로만 dedup(dual.py:351-386). 2회 참조=internal,
1회=boundary(defaultWall). 원본 tet 경계 face 가 dual 로 바뀌는 곳 = boundary vertex 의 cell
capping (dual.py:162-170, surface 점만 사용 → on-plane cap).

## 실측 트레이스 (standalone dual, cube.stl 6-tet — 정본 smoke 7.588 과 동일 메커니즘)

generate_native_tet(seed=10) → 8 verts / 6 tets → dual 8 cells / 86 faces:
- boundary **on-plane = 6.000** (표면 완벽 폐합) / **off-plane void = 4.171 / 48 faces**.
- **internal faces = 8 개뿐** (8 cell 이면 conformal dual 은 ≥12+ 기대) → 계면 대부분 미매칭.
- void 48 face 는 전부 **deep interior** (평면거리 0.062–0.417, min 0.062), 표면 cap 아님.
- coincident-centroid pair **0/48** (tol 0.02), ≥3-vert 공유 pair 4개뿐 → **near-duplicate 도 아님**
  (관용 매칭으로 복구 불가). 정본 smoke 는 same defect 로 void 7.588.

## 근본 원인 (plan_poly1 가설 반증)

plan_poly1/테스트 docstring 은 "boundary cell 이 surface 에 uncapped open-wall" 로 기록했으나
**실측상 틀림**: on-plane=6.000 으로 표면은 완전히 닫혀 있고 void 는 100% 내부다.
진짜 원인: barycentric dual 계면(tet edge 주위 centroid ring)은 일반적으로 **비평면**이라
per-cell ConvexHull 이 이를 **서로 다르게 삼각분할/coplanar-merge** → 인접 cell 의 계면
polygon 정점집합이 불일치 → `sorted` 키 매칭 실패 → 계면이 **양측 모두 one-sided boundary
face 로 누출** → 내부 void wall. 즉 dual 이 **face-conformal 하지 않다**. 관용/삼각형 단위
매칭도 불가(pair 0). 유일한 해법은 **위상적(topological) dual 구성**.

## 이론적 근거 (≤30줄)

- **문제 정의**: watertight 입력의 dual 은 2-manifold 여야 한다 — 모든 내부 계면 face 는
  정확히 2개 cell 이 공유. 현재는 계면 매칭이 기하(정점집합 일치)에 의존해 실패.
- **핵심 아이디어** (polyDualMesh 정석): dual vertex = tet centroid. **내부 tet edge e=(a,b)
  마다 dual face 1개** = e 를 공유하는 tet 들의 centroid 를 face-adjacency 로 정렬한 ring
  polygon. owner=cell[a], neighbour=cell[b] (input-vertex→dual-cell index). 이 구성은
  **위상만으로 정확히 2-cell 공유를 보장** → dedup 불필요, void 원천 제거.
  boundary edge(경계 face 를 가진 edge)는 open fan → 기존 surface 점(edge midpoint /
  boundary-face centroid / v_in)으로 cap 하여 on-plane 6.000 유지.
  1. 새 자료구조: `edge_tets`(이미 dual.py:213 존재) + `face_tets` 로 ring 정렬.
  2. 기존 차이: ConvexHull+정점집합 dedup(264-386) → edge-ring 위상 emit 로 교체.
  3. 보장: 내부 edge 는 닫힌 ring(정확히 2 cell), 위상적 2-manifold → void→0 수렴(내부).
- **레퍼런스**: OpenFOAM `polyDualMesh`, Owen 2007 §tet→poly dual, dual.py:179.
- **혁신성**: novelty 2 / rigor 2 / impact 2 = 6. 파라미터 sweep 아님 — 매칭을 기하→위상으로
  전환하는 알고리즘 교체(3 round sweep 금지 규칙 부합).

## 변경 (파일 1개: core/generator/native_poly/dual.py)

- 함수: `tet_to_poly_dual` 본문 264-405 (cell ConvexHull + face_map dedup) 교체.
- 핵심 변경 (≤80줄):
  1. `_ordered_tet_ring(e, edge_tets, face_tets)` 신규 — edge e 주위 tet 을 공유 face 로
     walk 하여 정렬 ring 반환(내부=닫힘, 경계=open fan + 두 boundary face).
  2. 내부 edge → centroid ring polygon 을 internal face 로 emit,
     owner=cell[min(a,b)] / nbr=cell[max(a,b)]. dual point = tet centroid(+cap 점).
  3. boundary edge → open fan 을 midpoint/boundary-centroid/v_in 으로 cap → boundary
     (on-plane) face. boundary vertex surface cap 은 기존 로직 재사용.
  4. cell 당 face 수집 후 min_cell_verts/degenerate 필터는 유지.
- **단조 가드**: post void_area 를 계측, `post_void > pre_void`(=7.588) 또는
  on-plane 이 6.0±5% 이탈 또는 negative_volumes 증가 시 **기존 ConvexHull 경로로 revert**
  (두 경로 공존, 위상경로가 개선일 때만 채택). pre/post 는 dual 내부에서 boundary area
  split 로 직접 비교.

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
timeout 120 python3 -m pytest tests/test_native_poly_solid_volume.py -q
timeout 170 python3 scripts/smoke_native_poly.py      # ≈45s, 1줄, exit 0
```

## 합격 기준 (validator 가 평가)

- 스모크 3분 내 완주, exit 0, 출력 포맷 불변.
- **void(off-plane) 유의미 감소**: 7.588 → **≤ 4.0** (약 ≥47% 감소; 내부 conformity 확보
  지표). on-plane surface **6.000 유지(6.0±5%)** — permanent gate 절대 불파.
- degenerate cells 0 유지, negative_volumes 증가 없음.
- `test_native_poly_covers_input_surface`·`_has_no_degenerate_cells` = **PASS 유지**.
- void gate(`_has_no_interior_voids`)는 여전히 xfail(strict) 허용(완치 아님) — 단
  void 측정치가 낮아졌으면 docstring 수치를 새 값으로 갱신(strict xpass 방지).
- volume gate 는 S3 로 이월(xfail 유지). tet/hex 회귀 0(dual.py 단일 변경).

## 카드 시퀀스 위치

- native_poly solid 캠페인 **2/4** (S1 측정 → **S2 내부 conformity** → S3 volume/boundary
  bulge → S4 skew/non-ortho quality).
- 다음 카드 후보(POLY-S2 PASS 후): **POLY-S3** — boundary open-fan cap 정밀화로 void→~0
  및 Σ|vol| 1.18x→1.0 (경계 cell bulge 제거), void gate xfail→permanent 승격.
