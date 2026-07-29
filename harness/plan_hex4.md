# CARD HEX-SKEW-INNER-RELAX (beta_hex4) — snapped boundary cell 의 normal-thickness 복원

**target_engine**: hex
**모티프**: snappyHexMesh addLayers 정신 (경계 normal thickness 확보) + Klingner 2007 smart smoothing (최소품질 비악화 시에만 accept)

## skew 4.64 정체 — 실측 (cylinder standard N=2000, 정본 PipelineOrchestrator 경로)

두 skew 정의가 공존한다. quality.py(internal, /√area) = 0.195. **evaluator checker(4.64) = boundary skewness**.

- checker max_skew **4.644 = 전량 boundary**(max_bnd 4.644, max_int 0.129). 32 faces>4.0, 96>2.0, 384>1.0 — **전부 곡면 side-wall**(cap boundary 전부 0.116, internal 전부 정상).
- worst faces 는 r=0.499(월핏 성공 지점)에 있음. 분해: `skew = tmiss/|nd|` = **0.0410 / 0.0088 = 4.64**.
  - 분자 tmiss(=face중심의 owner-cell중심 대비 tangential offset) 0.041 ≈ h(0.076) — 정상.
  - 분모 **|nd|(=owner cell 중심→boundary face 의 wall-normal 거리) = 0.0088 이 비정상적으로 작다** (side |nd| median 0.017, min 0.0067).
- 원인: draft 축정렬 박스는 |nd|≈h/2≈0.03. `_wall_fit_snap` 가 4 outer 정점을 반경 안쪽으로 벽까지 당기면 face중심은 안쪽으로 ~d, cc 는 ~d/2 이동 → **|nd| 붕괴**(0.03→0.0088). 즉 snap 이 경계 셀을 **wall-normal 방향 sliver** 로 만든 것. wall_dev 는 오히려 0.003 으로 좋다(월핏 성공의 부작용).
- fine(N=2000): max_skew 1.419 = **internal**(max_int 1.419 > max_bnd 1.271), 게다가 **max_nonortho 89.99**(octree level 전환부, 90° revert 트리거 근접). fine 은 별개·취약 → **이 카드가 절대 건드리면 안 됨**.

## 이론적 근거 (핵심 아이디어)

- **문제**: boundary skewness Sb = |(fc−cc)_⊥| / |(fc−cc)·n̂|. snap 이 |(fc−cc)·n̂|=|nd| 을 0 으로 붕괴시켜 Sb→∞.
- **아이디어**: 표면 정점(4 outer)은 **완전 고정**(wall_dev 재회귀 절대 금지, 최우선 가드). 그 대신 **incident 자유 내부정점(4 inner, boundary_verts∉)** 만 벽-normal 바깥(축 방향, 안쪽=inward)으로 밀어 cc 를 벽에서 멀리 → |nd|↑ → Sb↓. tmiss 는 radial 이동에 거의 불변이므로 Sb 단조 감소.
  1. `_build_hex_adjacency` 로 boundary_verts(=frozen) 확보. 각 boundary hex 셀의 owner |nd| 계산, `|nd| < τ·h`(sliver) 플래그.
  2. sliver 셀의 **non-boundary 정점만** 수집 → 각 정점을 incident sliver face 들의 평균 outward-normal 방향 −α·(목표두께−|nd|) 만큼 이동(directed, 안쪽).
  3. **최종단계 checker 로 pre/post 실측 후 전체 pass accept/revert**.
- **단조/안정성 (Klingner smart)**: pass 는 다음을 **모두** 만족할 때만 accept, 아니면 전량 revert —
  max_boundary_skew 가 eps 이상 **감소** ∧ max_internal_skew ≤ pre+eps ∧ max_non_ortho ≤ pre+eps ∧ negative_volumes==0. 표면정점 불변 ⇒ wall_dev 자동 보존.
- **레퍼런스**: attempts_catalog **R-c7 BETA2829(tet)** — 동일 근본원인(측벽 normal_dist 미소→bskew 폭발) 을 tet 에서 진단, "volume-only local op 불가·Garimella offset ring 뿐" 로 사망. **hex 는 다르다**: tet 은 4정점 전부 벽 근접이라 자유 내부점이 없지만, hex boundary 셀은 4 inner 자유정점을 가져 **동일 아이디어(normal thickness 복원)가 local volume-op 로 실현 가능**. R-c6 BETA2827 교훈: block-stage guard 가 하류 재악화 미탐지 → **guard 를 최종 mesh 의 실제 checker bskew 로**(본 카드 준수). papers/01_klingner_2007.
- **혁신성**: novelty 1.5(진단-특화 적용) · rigor 2.5(skew 성분분해 실측 + smart-guard + 최종단계 측정) · impact 2.5(hex 유일 잔여 결함 제거) = **6.5**.

## 변경

- 파일: `core/generator/native_hex/mesher.py` (단일 파일)
- 신규 함수 `_relax_boundary_sliver_interior(pts, hexes, tau, alpha, iters) -> (pts, stats)` (약 45줄), `_wall_fit_snap` 직후(line ~1352) 호출. 기존 disabled `enable_post_smooth`(boundary Laplacian, 표면정점 이동=금지 접근) 는 **미사용 유지·수정 금지**.
- 핵심 변경 (≤80줄):
  1. adjacency 캐시로 boundary_verts(frozen)·cell 목록 확보. 각 boundary 셀 owner |nd| 계산.
  2. `|nd| < τ·h` sliver 셀의 non-boundary 정점만 outward-normal −α 방향 directed relax (1–3 iter).
  3. 최종 `hex_quality_report`(internal) + checker `_compute_boundary_skewness`/`_compute_skewness` 로 pre/post 실측.
- 단조 가드: pass 전체를 pre_pts 로 스냅샷 → post 가 (bskew 감소 ∧ int_skew·nonortho 비악화 ∧ neg_vol==0) 아니면 `final_pts = pre_pts` 로 전량 revert. env `AUTO_TESSELL_HEX_SKEW_RELAX_OFF` 로 kill-switch(default ON — 가드가 revert-safe 보장하므로 default ON 무해).

## 검증 명령 (unit_tester 가 그대로 실행)

```bash
# 신규 skew 게이트 + 기존 6 불변식 (cylinder std/fine, cube 4) — 총 <3분
timeout 170 python3 -m pytest tests/test_native_hex_solid_volume.py -q
# 정본 solid smoke (cube, 회귀 감시) — <1분
timeout 90 python3 scripts/smoke_native_hex.py 2000
```

신규 테스트 `test_native_hex_standard_boundary_skew`(같은 파일): cylinder standard N=2000 실행 →
`res.quality_report.evaluation_summary.checkmesh.max_boundary_skewness ≤ 3.0` assert (정본 run 헬퍼 재사용, ad-hoc 금지).

## 합격 기준 (validator 가 평가)

- 기존 6 tests PASS + smoke SOLID OK (surface 6.0 / void 0 / vol 1.0 / degen 0).
- **standard checker max_skew(=bskew) 4.64 → ≤ 3.0** (permanent gate; 실측 root-cause 상 directed relax 로 ~2.0–2.5 도달 예상, 보수적 게이트).
- **wall_dev_max ≤ 0.0035 불변** (standard, 현 0.0032 — 재회귀 절대 금지, 표면정점 frozen 으로 자동 보장. **최우선 가드**).
- fine 회귀 금지: max_skew ≤ 1.5(현 1.42), max_nonortho ≤ 90.0(현 89.99 — 악화 금지, guard 로 revert).
- negative_volumes = 0, cube 4대 불변식 유지, bench 시간 ≤ 기존+15%.

## 카드 시퀀스 위치

- "post-snap boundary sliver 제거" 시퀀스 **1/2**. 본 카드: directed 내부정점 relax + smart-guard, 게이트 ≤3.0.
- 다음 카드 후보(본 카드 PASS 후): **HEX-SKEW-RELAX-ITER** — multi-iter + tangential cc 정렬(tmiss 저감) 추가, 게이트 standard bskew ≤ 2.0 로 강화. 표면정점 frozen·smart-guard 동일 유지.
