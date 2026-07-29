# PLAN HEX5 — HEX-SKEW2 판단: 추가 카드 불필요 (실측 기반 일단락)

**target_engine**: hex
**결론**: `_relax_boundary_sliver_interior` 파라미터 조정으로 skew 2.84 추가 개선
불가. 현재 default 는 이미 **내부-지표 제약 프론티어에 정확히 위치**. HEX-SKEW2
카드 미생성 — 억지 카드 금지 원칙에 따라 hex boundary skew 를 여기서 일단락.

## 측정 프로토콜 (정본)
- `tests/test_native_hex_solid_volume.py::test_native_hex_standard_boundary_skew`
  (cylinder N=2000 standard). 파이프라인 1회 10.4s.
- relax 파라미터 sweep 은 post-wall-fit mesh 를 1회 캡처 후 `_relax_boundary_sliver_interior`
  를 직접 호출해 격리 측정(파이프라인 재실행 불필요, 수초). accept 가드는 코드
  원본과 동일: post_bskew<pre-ε ∧ post_int_skew≤pre+ε ∧ post_no≤pre+ε ∧ post_neg==0.

## Baseline 재확인 (실측)
- checker max_boundary_skewness = **2.8406**, negative_volumes = **0** (task 배경 2.84 일치).
- 캡처 mesh: n_pts=2744, n_cells=1781, sliver=520.
- 현재 default 인자: tau=0.5, alpha=0.5, iters=2 (두 호출부 mesher.py:1219, 1545 모두 default).

## 핵심 실측: default 가 이미 프론티어
| 상태 | bskew | int_skew | non-ortho | 판정 |
|------|-------|----------|-----------|------|
| PRE (raw wall-fit) | 4.6436 | 0.1293 | 27.380 | — |
| default 0.5/0.5/2  | 2.8406 | 0.1248 | 21.243 | ACCEPT |
| 0.52/2 | 2.7998 | 0.1269 | 20.949 | ACCEPT (Δ만 -0.04) |
| 0.55/2 | 2.7413 | **0.1301** | 20.499 | reject (int_skew>pre 0.1293) |
| 0.60/2 | 2.6499 | 0.1354 | 19.730 | reject |
| 0.5/0.5/**4** | 2.1951 | 0.1706 | 29.942 | reject (int_skew·no 둘 다 >pre) |
| 0.5/1.0/8 | 1.1767 | 0.3345 | 89.725 | reject |

- default relax 는 bskew·int_skew·non-ortho **셋 다 동시 개선**(4.64→2.84,
  0.129→0.125, 27.4→21.2)이라 accept. 이 함수는 이미 유효.
- alpha 를 0.5→0.53 부근 넘기면 **post_int_skew 가 PRE(0.1293)를 초과** → 가드가
  정확히 revert. iters 를 늘리면 bskew 는 단조 감소(→1.18)하나 non-ortho·int_skew
  가 PRE 대비 폭증 → 전부 reject.
- 유일한 accept 개선폭: alpha 0.52 (bskew 2.84→2.80, **-1.4%**). 이는
  (a) 노이즈 수준이고 (b) 0.5→0.52 순수 매개변수 sweep = harness 금지 패턴.
  카드 가치 없음.

## non-orthogonality ↔ skew 결합 (task 항목 3 규명)
이 operator 는 sliver 셀의 자유 정점을 안쪽으로 **균일 directed 이동**시켜 벽-법선
두께 |nd| 를 복원한다. bskew 는 두께로 단조 감소하나, 같은 이동이 그 셀과 내부
이웃 사이의 내부 면을 기울여 internal skew·non-ortho 를 올린다. 즉 bskew 와
내부 non-ortho 는 이 단일 lever 에서 **구조적으로 반대 방향**으로 결합돼 있고,
독립 개선이 불가능하다. default 가드가 멈춘 지점이 정확히 두 곡선의 교차점(내부
지표가 raw mesh 수준을 넘기 직전)이다. octree level-transition 부근 89.99° non-ortho
관측도 동일 원인: 벽 근처 자유 정점을 더 밀수록 그 값이 커진다(위 표 89.7° 재현).

## 왜 억지 카드를 만들지 않는가
- gate 는 이미 ≤3.0, 현재 2.84 로 여유 통과. snappyHexMesh 산업 관행(max skew <4)
  대비도 양호.
- block-level 가드가 내부-지표 프론티어에 정확히 앉아 있어 파라미터로는 여유 0.04뿐.
- 유일한 알고리즘적 escape 는 "per-vertex 국소 가드 relax"(각 자유 정점 이동을
  블록이 아니라 정점별로, 인접 내부 면 skew/no ≤ pre 를 만족하는 최대 fraction 까지
  line-search) — native_tet HEX-WALLFIT-BACKTRACK 과 동형. 그러나:
  - 프론티어 자체가 내부-지표 제약으로 묶여 있어 상한이 낮다(정점별로 여유가 있는
    소수만 추가로 움직여 기대 이득 소폭, 대략 2.84→2.4 추정, 비용·리스크 대비 낮음).
  - 다중 카드 규모 + neg-vol/wall_dev 재회귀 리스크. 현 gate 여유를 감안하면 ROI 낮음.
  - → **지금은 착수하지 않음**. 필요 시 별도 캠페인으로 기록만 남긴다.

## 불변식 (미변경 — 본 판단은 코드 변경 없음)
- wall_dev_max 불변(표면 정점 frozen), negative_volumes==0 불변, solid 4대 불변식 불변.

## 로드맵 재조준 제안
- hex boundary skew: **일단락**(2.84, gate ≤3.0 permanent).
- 다음 우선순위: poly 캠페인 지속(PPP/TTT 라인) 또는 hex 의 다른 축
  (예: octree level-transition non-ortho 자체를 2:1 balance 이후 템플릿으로 완화 —
  WWW 라인 연장). 단 skew lever 로는 재진입 금지(본 실측이 프론티어를 확정).
