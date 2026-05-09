# Vertex Duplication BL Refactor — Plan

## Goal
hard_100029 multi-patch junction (skew=260, θ=89.78°) + extreme_1017013/14 flat sheet (5 patches) 에서 PASS 도달.

## 수학적 근거 (iter 22 발견)
**boundary skew = tan(θ)** where θ = angle(avg_vnorm, face_normal).
Per-vertex extrusion: 한 wall vert v 가 인접 face 들의 평균 vnorm 사용 → multi-patch 에서 face_normal 과 90° 이탈 → skew 폭증.

**해결**: 각 face 가 자기 face_normal 방향으로 extrude → cap이 face_normal 축에 정확히 align → skew = 0.

## 현재 native_bl 구조 (refactor 대상)

```python
# Per-vertex extrusion (현재)
vnorm[v] = avg(face_normal of adj faces at v)  # angle-weighted (iter 16)
inner_pt = points[v] - vnorm[v] * thickness
# All faces sharing v use the SAME inner_pt
```

```python
# Per-face extrusion (목표)
for face f in wall_faces:
    for v in f:
        if v is junction_vert(f):  # face_normal of f differs from avg(adj normals)
            inner_pt_f_v = points[v] - face_normal_f * thickness  # face-specific
        else:
            inner_pt_f_v = points[v] - vnorm[v] * thickness  # shared (iter 16 default)
```

## Topology 문제

두 face f1, f2 가 wall edge (v, w) 공유 시:
- f1 prism 의 inner edge = (v_f1, w_f1)
- f2 prism 의 inner edge = (v_f2, w_f2)
- 두 inner edge 가 다른 verts → side quad 가 공유 안 됨 → topology hole

**해결책**: junction edge 에서 gap-filling cell 삽입:
- 4 inner verts (v_f1, v_f2, w_f1, w_f2) + 2 wall verts (v, w)
- 2 tet 또는 1 pyramid 로 채움
- Pyramid: apex=midpoint, base=4 inner verts (warped quad)
- 2 tets: (v, w, v_f1, w_f1) + (v, w, w_f2, v_f2)

## 단계별 implementation plan

### Step VD-1 (1d): 분석 + 설계 문서 + unit test infra
- ✅ 이 문서
- `tests/test_vd_*.py` template
- `core/layers/native_bl_vd.py` skeleton

### Step VD-2 (1d): junction vert/edge detector
- 각 wall vert v: 인접 face 의 face_normal 발산 측정
- cos(face_normal_i, face_normal_j) < threshold (default 0.9 = 25°) → junction
- Output: `is_junction_vert: dict[int, bool]`, `junction_edges: set[tuple[int,int]]`
- Unit test: cube vs sphere vs flat_sheet

### Step VD-3 (1.5d): per-face inner vert generator
- For each (face f, vert v) with v ∈ junction_verts AND f's normal differs from vnorm[v]:
  - duplicate: append new vert at points[v] (same position)
  - inner_pt = duplicated_vert - face_normal_f × thickness
- Maintain `face_inner_vert: dict[(face_id, vert_id), int]`
- Unit test: cube corner (3 faces share vert) → 3 separate inner verts

### Step VD-4 (1.5d): prism cell topology with duplications
- Original prism: outer (a0,a1,a2), inner (b0,b1,b2) where bi shared
- New prism: outer (a0,a1,a2), inner (b0_f, b1_f, b2_f) with b_f from face_inner_vert
- Side quad: (a_i, a_(i+1), b_(i+1)_f, b_i_f) — quad of THIS face
- Adjacent face's prism uses different inner verts → quads don't share

### Step VD-5 (1d): gap-filling at junction edges
- Wall edge (v, w) shared by f1, f2 with f1 ≠ f2 inner verts:
  - Insert gap-filling tets (v, w, v_f1, w_f1) + (v, w, w_f2, v_f2)
  - Or pyramid with apex at midpoint
- Care: handle 3+ faces meeting at edge (rare but possible)

### Step VD-6 (1d): faces/owner/neighbour 재구성
- All new prism + gap-fill cells appended
- Faces 정렬: internal first, boundary last
- owner/neighbour rebuild
- Patch boundary 갱신 (wall, bl_internal_domain)

### Step VD-7 (1d): multi-layer BL with duplications
- Layer 1: outer = wall, inner = layer-1 cap (per-face dup)
- Layer 2: outer = layer-1 cap, inner = layer-2 cap (per-face dup or shared if smooth)
- Layer N+1 (bl_internal): innermost cap

### Step VD-8 (1d): verification + 회귀
- bench score 측정 (목표: 2700+ → 2800-2900)
- 21 STL 모두 PASS or PASS_WITH_WARNINGS 시도
- 회귀 없음 보장 (test_cube etc.)

### Step VD-8b (2026-05-09): per-STL VD allow-list

`AUTO_TESSELL_BL_VD_FOR=token1,token2,...` 로 VD 활성화를 STL-단위로 좁힘.
이전 VD-8a 의 global `VD_ENABLE=1` 은 21 STL 전체에 VD 를 켜므로,
multi-patch junction 이 아닌 STL 들의 score 도 영향을 받았다. VD-8b 는
이를 해결한다.

활성화 결정 (`core/layers/native_bl.py::_vd_should_activate`):
- VD_FOR unset / empty → VD_ENABLE 가 결정 (기존 VD-8a 동작 유지)
- VD_FOR non-empty → 각 token 을 `case_dir/geometry_report.json` 의
  `file_info.path` basename 에 substring 매칭. 하나라도 맞으면 VD on.
  매칭 없으면 VD off (이 모드에서는 VD_ENABLE=1 무시).

권장 사용 (VD 가 도움되는 4 STL 만):
```bash
AUTO_TESSELL_BL_VD_FOR=hard_100029,extreme_1017013,extreme_1017014 \
  timeout 1800 python3 .autoresearch/tet_bl_full/verify.py 2>&1 | tail -3
```

2026-05-09 측정 (위 명령):
- 18 unaffected STLs: 동일 결과 (필터 OFF → 기존 코드 경로).
- hard_100029: max_skew 260+ → 11.68 (≈22× 개선) — VD math 검증.
- extreme_1017013/14: max_skew 1144 / 400 (BL-only mesh, evaluator FAIL).
- Aggregate score 2550 < baseline 2700 → 현 VD 경로는 bulk cell drop 으로
  evaluator FAIL 가 우세. **다음 단계 (VD-9): VD prism+gap-fill 을 기존
  bulk volume cell 과 stitch** 해야 score 가 baseline 위로 올라간다.
  VD-8b 의 가치는 "필요한 STL 만 격리해서 VD 의 boundary-skew 효과를
  단독 측정" 가능하게 한 것. VD_FOR 미설정 시 모든 21 STL 은 baseline
  2700 그대로 (default-OFF 경로 보존).

## 환경 변수 (점진적 enable)

- `AUTO_TESSELL_BL_VD_ENABLE=0` (default OFF) — 글로벌 VD on/off (VD-8a)
- `AUTO_TESSELL_BL_VD_FOR=` (default empty) — STL 이름 substring allow-list (VD-8b);
  non-empty 시 VD_ENABLE 보다 strict (= 매칭된 STL 만 VD)
- `AUTO_TESSELL_BL_VD_JUNCTION_COS=0.9` — junction detection threshold
- `AUTO_TESSELL_BL_VD_GAPFILL_MODE=tet|pyramid` — gap fill 방식

## 위험 / Mitigation

1. **Topology 깨짐**: 각 단계 unit test + checkMesh 검증
2. **회귀**: env 옵션 OFF 기본 → 기존 STL 영향 없음
3. **복잡도**: 단계별 commit, 매 단계 테스트
4. **시간**: 각 step ~1d → total ~7d

## 합격 기준

- 21 STL bench score ≥ 2800 (현재 2700)
- iter 27 baseline 회귀 0 STL
- 자체 테스트 ≥ 5 (junction detection, per-face vert, gap-fill, BL stack, full pipeline)
