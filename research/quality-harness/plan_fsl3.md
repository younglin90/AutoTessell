# CARD FSL3 — guarded 2-3 flip 로 flip-eligible all-surface flat sliver 제거

**target_engine**: tet
**모티프**: fTetWild §3.4 topology-preserving sliver removal — 2-3 flip (drop 금지, boundary 불변)

## 재현 baseline (실측, 정본 N=600 직접 호출, P4C=0, ~28s)

명령 = `research/quality-harness/plan_torus_quality.md` §재현 (writer-spy 로 최종 in-memory mesh 캡처 후
`flat_allsurf_sliver_candidates` 적용). 실측값:

- grade **B**, n_cells 12219, n_surface_vertices 2047.
- FSL1 detector(default q_flat=0.01): `n_cand=75, n_flip_eligible=9,
  n_core_unflippable=61, max_bskew=2.94e7, worst_tet=8918`.
- **boundary-skew 를 flip-eligibility 로 버킷팅 (결정적 실측)**:
  - flip-eligible 9개의 boundary-skew 기여 **최대 = 18.7** (18.7, 18.7, 18.3…).
  - unflippable 61개: **2.94e7, 2.28e6, 2.28e6…** ← global max 전부 여기서 나옴.

## ⚠ 계획 전제와 실측의 충돌 (반드시 반영)

과제 브리핑은 "eligible 10/12 제거 → 잔여 unflippable 2개 ~6.5e5" 를 가정했으나,
**HEAD 실측은 다르다**: eligible 슬리버는 boundary-skew 를 거의 안 만든다(≤18.7).
FAIL driver 인 max_bskew=2.94e7 는 **전부 unflippable wedge** 다. 따라서 **FSL3
(eligible 부분집합 flip) 는 global max_bskew 를 낮추지 못한다** — 그건 구조적으로 #4 몫.

→ FSL3 의 정직한 가치: (1) guarded 2-3 flip 기계가 **area/vol·boundary 불변으로 안전**함을
실데이터로 증명, (2) 진짜 flat sliver 9개 국소 제거(min_q hygiene), (3) #4 (unflippable
core 다-tet 연산) 의 de-risk 기반. **max_bskew 완치는 FSL3 목표가 아니다** (비증가만 요구).

## 이론적 근거 (≤30줄)

- **문제**: 얇은 워셔(dual-torus) 를 tet 분할하면 4정점 전부 표면인 공면 flat sliver 발생.
  `q_edge = 8.48·|V|/edge_max³ < 0.01`. drop 은 void 벽 → area/vol=1.010 파괴(금지).
  vertex relocation 은 4정점 surface-locked → 불가.
- **핵심 아이디어 (2-3 flip)**: eligible sliver `ti` 와 공유 internal face `(s0,s1,s2)` 이웃 `tj`
  (apex p1,p2) 로 이룬 bipyramid 를 edge (p1,p2) 축 3-tet 로 재분할:
  `(s0,s1,p1,p2),(s1,s2,p1,p2),(s2,s0,p1,p2)`. FSL1 이 이미 3-signed-vol 동부호(볼록 union)
  로 유효성 판정.
- **boundary 불변 논증 (area/vol 구조 보존)**: 2-3 flip 은 **공유 internal face 1개만**
  재배열한다. bipyramid 의 outer 6 face(=경계 face 포함) 는 삼각형 집합이 **동일 불변**,
  owner cell 만 sliver→비공면 tet 으로 바뀐다. 1-owner boundary-face 집합 불변 ⇒ 발산정리
  면적/부피 타일링 구조 보존 ⇒ area/vol=1.010 재회귀 불가능(구조적).
- **skew 개선 방향**: flat sliver 의 boundary face 는 새 owner(p1 또는 p2 포함 → 비공면
  centroid) 로 넘어가 normal_dist 폭발 해소. 단, 이웃 boundary face 의 owner 도 바뀌므로
  국소 재악화 가능 → per-op + 최종 이중 가드 필수.
- **레퍼런스**: Hu 2020 fTetWild §3.4; validate.py `flat_allsurf_sliver_candidates` (FSL1).
- **혁신성**: novelty 2 / rigor 2 / impact 1 (eligible 은 FAIL 미driver — 합=5, 인프라·hygiene
  카드로 진행. 진짜 impact 는 #4).

## 변경 (2 파일, ≤80줄)

1. `core/generator/native_tet/validate.py` — 신규 `apply_flat_sliver_23_flips(pts, tets,
   n_surface_vertices, *, q_flat=0.01) -> (tets_new, dict)`:
   - FSL1 detector 의 face-partner/flip-eligibility 로직 재사용해 eligible 후보 수집.
   - eligible 만 순회, 이미 소비된 tet(touched mask) 스킵. 각 flip 에 **per-op 상대 가드**:
     (a) affected min_q 비감소: `min(q_new3) ≥ min(q_old2) - 1e-12` (q_edge 공식 재사용),
     (b) neg_vol 0: 3 new tet signed-vol 동부호(FSL1 판정 재확인),
     (c) affected boundary-face skew 비증가(normal_dist proxy 국소),
     (d) shared face 가 internal(partner≥0) — 구조적(경계 face 미접촉 보장).
     하나라도 위반 → 그 flip 만 skip(per-op revert). tets 재구성(2 제거→3 추가).
   - 반환 dict: `{n_eligible, n_flipped, n_reverted}`.
2. `core/generator/native_tet/mesher.py` — BETA2826 pre-write locked-smooth 블록 **직후**
   (line ~2229, `not _phase_bc_skip` 가드 안, `_prog("write")` 직전) 훅 추가:
   - `_surf_ids` 재사용해 `apply_flat_sliver_23_flips(final_pts, final_tets, n_surface_vertices)`
     호출 → `cand_tets`.
   - **이중 가드(BETA2827 교훈, 최종 mesh 기준)**: `_skew_proxy(final_pts, cand_tets) ≤
     _skew_proxy(final_pts, final_tets)·(1+1e-6)` 이고 boundary-face count 불변이면 accept,
     아니면 전량 revert(final_tets 유지). log `native_tet_fsl3_flip`.

## 검증 명령 (unit_tester 가 그대로 실행, 각 3분 이내)

```bash
timeout 90 python3 -m pytest tests/test_native_tet_flat_sliver_detect.py -q
```
신규 test 추가: (a) 합성 bipyramid(공면 flat sliver + 볼록 apex 2개) → n_flipped=1,
tet 수 +1, boundary-face 집합 불변; (b) 오목 union(FSL1 flip_ok=False) → n_flipped=0;
(c) per-op 가드 위반 합성 → n_reverted≥1, tets 불변.
회귀:
```bash
timeout 170 python3 -m pytest tests/test_native_tet_solid_volume.py -q
timeout 120 python3 -m pytest tests/test_cylinder_wall_fidelity.py -q
```

## 합격 기준 (validator 평가 — 정직한 실측 기반)

- 신규 unit test + 회귀(solid_volume, cylinder_wall_fidelity) PASS.
- **N=600 재현**(정본 명령):
  - `n_flipped ≥ 7` (eligible 9 의 ≥80%), `n_reverted` 로 나머지 설명.
  - **max_bskew 비증가**: post ≤ 2.94e7·(1+1e-6). (worst=8918 은 unflippable → **감소 불가,
    #4 몫**. 감소를 요구하지 않는다 — 정직 기준.)
  - area/vol = **1.010 ± 0.005 불변** (절대 재회귀 금지), grade B 이상 유지, boundary-face
    count 불변.
  - neg_vol 0 유지, solid 4대 불변식(surface 6.0 / void 0 / vol 1.0 / degen 0) pre==post.
- cube/cylinder smoke 회귀 0 (mesh 변화는 dual-torus 류 flat sliver 있는 입력에 한정 —
  cube 는 eligible 0 예상, no-op).
- bench 시간 ≤ 기존 +15% (flip 대상 ≤9개, Python 루프 경미).

## 카드 시퀀스 위치

- "얇은 영역 all-surface flat-sliver topology-preserving 제거" 시퀀스 **3/4**
  (FSL1 detector 스켈레톤 → FSL2 진단 hook 을 본 카드에 접음 → **FSL3 guarded flip**).
- **다음 카드(FSL3 PASS 후)**: **FSL4 — unflippable 2-boundary wedge core** (worst_tet 8918,
  2.94e7). surface-edge 보존 다-tet 연산(edge split + 재삼각화) 또는 known-limit 확정.
  **이것이 실제 FAIL driver 해소 카드** — FSL3 인프라(flip 실행 + 이중가드) 를 확장.
