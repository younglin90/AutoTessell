---
title: HEX-WALLFIT-CANDIDATE-QUALITY-1 wall-fit 후보 품질 교차 진단
date: 2026-07-26
status: measured-diagnostic
tags: [native_hex, wall-fit, quality, report-only, rollback-candidate]
---

# 범위

`_wall_fit_snap`의 기존 candidate acceptance를 바꾸지 않고, opt-in 환경변수
`AUTO_TESSELL_HEX_WALLFIT_CANDIDATE_QUALITY_DIAG=1`에서만 각 boundary vertex
projection 후보의 영향 cell을 snapshot했다. 측정 항목은 local canonical skew,
face warpage, emitted signed volume, orientation-free volume, global boundary
face-key set, boundary area다. 결과는 reject/accept 판단에 사용하지 않는다.

## 측정 결과

작은 실험은 `max_cells=500`, mixed-level realization ON, 기본 wall-fit,
face-area guard OFF, `max_iterations=1` 조건이다. 이 낮은 cell budget에서는
pipeline이 최종 성공하지 않았으므로, 아래는 final gate가 아니라 wall-fit
단계의 candidate census다.

| 형상 | 후보 | full / partial / reject | trial 회귀 | 적용 회귀 | boundary area 변화 | 최대 적용 skew Δ | 최대 적용 warpage Δ |
|---|---:|---:|---:|---:|---:|---:|---:|
| cylinder | 128 | 128 / 0 / 0 | 128 | 128 | 128 | +1.5313 | +0.4064 |
| sphere | 128 | 128 / 0 / 0 | 104 | 104 | 128 | +1.4238 | +0.0571 |
| gear | 271 | 241 / 12 / 18 | 207 | 186 | 238 | +1.2518 | +0.7688 |

`boundary key`는 모든 후보에서 유지됐다. 하지만 정점 이동이므로 boundary
face area는 바뀌었다. 최대 area 변화는 cylinder `0.01118`, sphere `0.05576`,
gear `0.01892`였다.

더 큰 cylinder `max_cells=2000` census는 후보 `560`개 중
`358/179/23` full/partial/reject였고, trial 회귀 `515`, 적용 후 회귀
`481`, area 변화 `521`개였다. near-zero normal-distance 셀에서 skew 분모가
작아져 최대 Δ가 `2.7756e13`까지 튀었으므로, 이 outlier를 곧바로 절대 게이트
값으로 쓰지 않는다. 이 결과는 wall-fit이 현재 no-inversion/거리/envelope
guard만으로는 local quality regression을 막지 못한다는 진단 증거다.

## 판정

`HEX-WALLFIT-CANDIDATE-QUALITY-1`은 **measured, quality regression observed**다.
`HEX-TRANS-2`에서 전이 인접성 집중이 기각된 것과 합치된다. 나쁜 품질은
transition label에 한정되지 않고, 일반 wall-fit projection 후보가 영향을
받는 cell의 skew/warpage와 boundary area를 바꾼다.

아직 quality gate나 rollback을 추가하지 않았다. 다음 구현 후보는
`HEX-WALLFIT-QUALITY-TRANSACTION-1`이며, 먼저 skew의 near-zero denominator
정규화와 signed-volume orientation 계약을 확정한 뒤, 후보 단위 상대 품질
비교와 boundary area 허용오차를 이용한 default-OFF transaction으로 제한한다.
절대 임계값으로 현재 permanent gate를 대체하지 않는다.

## 계약 진단 보충

코드 대조 결과 canonical skew의 구현은 `NativeMeshChecker`와
`match_diagnostic._quad_skewness`가 모두 `max(abs(normal_dist), 1e-30)`을
분모로 사용한다. 작은 cylinder 진단에서는 trial 최소 `|normal_dist|`가
`0.0149533`, near-zero count가 `0`인데도 applied max skew Δ가 `+1.5313`이었다.
따라서 작은 실험의 회귀는 분모 붕괴만으로 설명되지 않는다. 더 큰 run의
`2.7756e13` outlier는 별도로 분모 민감성의 영향을 받는 수치로 분리한다.

signed-volume은 quality report용 보조 관찰값이다. 실제 `_wall_fit_snap`
no-inversion 계약은 각 incident cell의 `_native_generic_cell_face_signs`와
projection 전 reference sign을 비교한다. generic face winding을 centroid
fan으로 합산한 `_signed_cell_volume`은 저장된 face 방향 표현에 의존하므로,
현재 단계에서 음수 개수를 production gate로 승격하지 않는다.

## 2026-07-26 HEX-WALLFIT-QUALITY-TRANSACTION-1 result

두 가지 상대 transaction을 계산했지만 실제 후보 수용에는 연결하지 않았다.

- strict: 영향 cell의 max skew와 max warpage가 증가하지 않음
- p95: 영향 cell의 p95 skew와 p95 warpage가 증가하지 않음
- combined: strict와 p95를 동시에 만족

| 형상 | 후보 | strict 비회귀 | p95 비회귀 | combined | 거리 개선 후보 | 거리 개선+품질 회귀 |
|---|---:|---:|---:|---:|---:|---:|
| cylinder | 128 | 0 | 0 | 0 | 128 | 128 |
| sphere | 128 | 24 | 0 | 0 | 128 | 104 |
| gear | 271 | 85 | 66 | 66 | 253 | 186 |

거리 개선 총량은 cylinder `5.2117`, sphere `10.8663`, gear `16.9085`였고,
각각의 최대 단일 후보 개선은 `0.06122`, `0.17648`, `0.10862`였다. 모든
거리 개선 후보의 boundary face key는 보존됐다.

판정: **measured, quality-only rollback은 surface fitting과 충돌**한다.
cylinder에서는 거리 개선 후보 전부가 local quality 회귀를 동반했다. 따라서
단일 monotone quality gate를 구현하지 않고, 다음은 최종 wall deviation과
candidate local delta를 같은 대표 mesh에서 교차하는 trade-off 진단이다.

## 2026-07-26 HEX-WALLFIT-QUALITY-TRANSACTION-1 result

실제 후보 수용을 바꾸지 않고 두 가지 상대 품질 transaction을 계산했다.

- strict: 영향 cell의 max skew와 max warpage가 모두 증가하지 않음
- p95: 영향 cell의 p95 skew와 p95 warpage가 모두 증가하지 않음
- combined: 두 기준을 동시에 만족

| 형상 | 후보 | strict 비회귀 | p95 비회귀 | combined | 최대 상대 boundary-area 변화 |
|---|---:|---:|---:|---:|---:|
| cylinder | 128 | 0 | 0 | 0 | 0.2266% |
| sphere | 128 | 24 | 0 | 0 | 0.3641% |
| gear | 271 | 85 | 66 | 66 | 0.1702% |

세 형상 모두 boundary face-key 변경은 0건이었다. 위 결과는
`max_cells=500`의 mixed-level opt-in wall-fit 단계 census이며, 낮은 예산으로
pipeline 최종 성공을 판정하는 자료가 아니다.

판정: **measured, naive monotone transaction is too restrictive**. 특히
cylinder에서 모든 후보를 rollback하면 실제 wall-fit의 surface-distance
개선도 차단할 가능성이 있다. 따라서 quality-only rollback을 구현하지 않고,
다음 카드에서 같은 후보의 surface distance/wall deviation 개선량과 local
quality delta를 함께 교차한다. 문헌의 local regularization을 임계값으로
직접 포팅하지 않으며, surface fidelity와 품질의 상대 trade-off가 측정된
뒤에만 default-OFF transaction을 검토한다.

## 2026-07-26 HEX-WALLFIT-SURFACE-TRADEOFF-1 result

wall-fit 단계 전체의 boundary vertex-to-input-surface distance도 비교했다.
같은 `max_cells=500` mixed-level opt-in 조건이며, 최종 pipeline verdict가
아니라 wall-fit stage census다.

| 형상 | boundary vertices | mean before→after | p95 before→after | max before→after |
|---|---:|---|---|---|
| cylinder | 380 | `0.027915→0.014200` | `0.061217→0.003791` | `0.373194→0.373194` |
| sphere | 334 | `0.078905→0.046371` | `0.562459→0.562459` | `0.995472→0.995472` |
| gear | 672 | `0.026542→0.001380` | `0.096807→0.005295` | `0.108621→0.019445` |

판정: **measured, surface-fidelity benefit confirmed**. wall-fit은 평균 또는
p95 surface distance를 크게 줄이는 반면 일부 영향 cell의 local
skew/warpage를 악화시킨다. 품질-only rollback은 표면 계약과 충돌하므로
transaction 구현과 default 승격을 보류한다. 다음은 대표 mesh 크기에서 기존
wall_dev/skew gate와 후보 delta를 연결하는 검증이다.

## 2026-07-26 HEX-WALLFIT-FINAL-GATE-CROSS1

같은 report-only 실행에서 후보 snapshot과 최종 checker/evaluator 결과를
함께 출력하도록 `scripts/diag_hex_transition_quality1.py`를 확장했다. 생성
동작과 후보 수용은 바꾸지 않았다.

| 형상 / 예산 | 후보 | 거리 개선 | 거리 개선+local 회귀 | combined 비회귀 | 최종 verdict | cells | final boundary skew | negative volume | area deviation |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| cylinder / 500 | 128 | 128 | 128 | 0 | FAIL | 412 | 2.73027 | 0 | 4.59347% |
| sphere / 500 | 128 | 128 | 104 | 0 | FAIL | 276 | 2.85183 | 0 | 10.0102% |
| gear / 500 | 271 | 253 | 186 | 66 | FAIL | 408 | 1.38997 | 0 | 11.4375% |
| cylinder / 2000 | 560 | 537 | 481 | 49 | FAIL | 1384 | 125.761 | 0 | 87.0928% |

500-cell에서는 세 형상 모두 음수 체적 0이고 boundary skew가 영구 기준
3.0 아래였지만, 다른 evaluator 조건 때문에 전체 verdict는 FAIL이었다.
2,000-cell cylinder에서는 음수 체적 0인 채 final boundary skew가 125.761로
급증했다. 따라서 local candidate 회귀가 실제 최종 gate 실패와 연결될 수
있음은 확인했지만, transition 전용 원인이라는 증거는 없다. 2,000-cell
cylinder에서 거리 개선 후보 537개 중 481개가 local quality 회귀를 동반했고,
단순 combined 비회귀 정책은 49개만 허용한다.

판정: **measured, final-gate connection established**. 품질-only rollback은
표면 거리 개선 대부분을 막으므로 구현하지 않는다. 대규모 cylinder의 scale /
root-cause 진단을 별도 카드로 열고, 현재 진단과 mixed-level/face-area
실험 flag는 계속 기본 OFF로 유지한다.

## 2026-07-26 HEX-OCT-MIXED-LEVEL-ROOTCAUSE-1

대규모 cylinder에서 candidate-quality audit를 끄고 mixed-level과 wall-fit을
직교시켰다.

| 조건 | cells / census | final boundary skew | negative volume | area deviation | verdict |
|---|---|---:|---:|---:|---|
| mixed OFF, wall-fit ON | 1781 hex | 3.20865 | 0 | 0.2637% | PASS_WITH_WARNINGS |
| mixed ON, wall-fit OFF | 1363 hex + 22 other | 1.16279 | 0 | 93.4942% | FAIL |
| mixed ON, wall-fit ON | 1363 hex + 22 other | 125.761 | 0 | 87.0928% | FAIL |
| mixed OFF, wall-fit OFF | 1781 hex | 0.974374 | 0 | 15.3787% | FAIL |

mixed-level builder의 `before_snap`부터 transition cell `22`, boundary face
`1479`, report-only signed-negative `2`가 관찰됐다. `_build_nlevel_cells`가
coarse face만 sub-quad로 분해하고 fine 이웃의 대응 face partition/template을
생성하지 않는 것이 핵심이다. 따라서 writer가 주범이 아니라 비정합 transition
realization이 1차 원인이고, wall-fit은 그 위에서 skew를 증폭한다.

판정: **measured, root cause found**. mixed-level은 기본 OFF 유지하고,
wall-fit quality rollback으로 가리지 않는다. 다음 별도 카드
`HEX-OCT-TRANSITION-TEMPLATE-1`에서 양쪽 face가 일치하는 conforming template,
boundary/부피/결정론 gate를 설계·구현한다.

## 2026-07-26 correction — HEX-OCT-TRANSITION-WINDING-1

직전의 “fine 이웃 쪽 face partition이 없다”는 해석은 synthetic face-key
대조로 정정한다. 2:1 synthetic case에서는 coarse sub-quad와 fine quad가
같은 face key를 공유한다. 실제 결함은 `_sub_quads_on_face`의 모든 cyclic
순서가 `_HEX_FACES`와 반대였던 것이다.

wrapper에서 각 sub-quad를 한 번 reverse하는 최소 수정 후 synthetic
transition signed-negative는 `1→0`, face incidence는 `{1:87,2:132}`로
그대로였고 targeted test `4 passed`다. real mixed cylinder도 builder
signed-negative `2→0`, wall-fit OFF writer drop `0`을 확인했다. 그러나
wall-fit OFF의 area deviation `93.4942%`, wall-fit ON의 skew `125.761`는
남아 있으므로 broader mixed-level quality 문제는 별도 카드로 유지한다.

## 2026-07-27 HEX-OCT-MIXED-LEVEL-COVERAGE-1 — implementation result

The large-budget mixed-level failure was traced to (1) block-origin-only
`covered` handling, which stranded unprocessed cells in a partly consumed
block, and (2) single-index neighbor-level sampling, which missed finer cells
elsewhere on the coarse-face contact slab. The opt-in implementation promotes
mixed blocks to finest leaves, fills residual partial blocks safely, and scans
the complete adjacent slab before sub-quad splitting.

| metric | before | after |
|---|---:|---:|
| synthetic transition tests | 4 passed | 5 passed |
| real builder interior-looking boundary faces | 155 | 0 |
| cylinder cells at max_cells=2000 | 1383 | 1655 |
| max boundary skew | 125.761 | 3.20865134 |
| surface area deviation | 87.09% | 0.263700907% |
| negative volumes | 0 | 0 |
| writer dropped cells | 2 / malformed prediction | 0 |

Writer boundary face-set remained equal and boundary-area delta was
`-1.13e-9`; the final result is `PASS_WITH_WARNINGS` because the permanent
boundary-skew threshold `3.0` is still exceeded. The residual 85 bad-face
large-budget quality issue is not hidden by changing a gate and is tracked as
`HEX-OCT-SCALE-QUALITY-1`. Default mixed-level realization remains OFF.

## 2026-07-27 HEX-OCT-SCALE-QUALITY-1 — wall-fit isolation

With the mixed-level coverage fix active, direct builder quality had zero bad
boundary faces. Applying `_wall_fit_snap` created `80` bad boundary faces;
the full 2,000-cell pipeline reported `85`. The transition-owner and
transition-vertex-adjacent counts were both zero, so this is a wall-fit
boundary-vertex quality effect rather than a transition-template defect.

| condition | cells | max boundary skew | area deviation | bad faces |
|---|---:|---:|---:|---:|
| wall-fit ON | 1655 | `3.20865134` | `0.263700907%` | 85 |
| wall-fit OFF | 1655 | `0.974373881` | `15.3787224%` | 0 |

Candidate audit: `496/496` candidates improved surface distance; `376` also
regressed local quality, `120` passed the strict local-quality test, and `104`
passed the combined p95 test. Boundary keys remained unchanged. Mean distance
improved `0.0167231→0.0007091`, p95 `0.0490482→0.00376990`.

Decision: **measured, no implementation**. Quality-only rollback conflicts
with the surface-fidelity contract. The permanent boundary-skew gate remains
unchanged and the repair is deferred to a separately justified
surface-constrained/Pareto card.
