---
title: HEX-TRANS-2 전이/행잉노드 인접성 교차 진단
date: 2026-07-26
status: measured-falsified
tags: [native_hex, transition, hanging-node, quality, report-only]
---

# 범위

`HEX-TRANS-2`는 mixed-level octree 출력에서 나쁜 경계면이 transition cell
또는 그 주변에 집중되는지 확인하는 report-only 카드다. transition-specific
repair를 구현하거나 품질 게이트를 바꾸지 않았다.

측정 조건:

- 실제 cylinder/sphere/gear fine pre-BL 출력, `max_cells=8000`
- `AUTO_TESSELL_HEX_MIXED_LEVEL_REALIZATION=1`
- 기본 wall-fit 경로, face-area guard는 OFF
- 경계면 canonical skew 임계값 `2.0`
- `transition_owner`: metadata가 transition cell로 표시한 cell이 소유한
  boundary face
- `transition_vertex_adjacent`: transition cell의 정점을 하나라도 공유하는
  boundary face. authoritative hanging-node chain ID가 없는 상태의 넓은
  report-only proxy이며 정확한 hanging-node 인접성으로 승격하지 않는다.

## 결과

| 형상 | 단계 | 나쁜 경계면 | transition 소유 | 비율 | transition 정점 인접 | 비율 |
|---|---|---:|---:|---:|---:|---:|
| cylinder | before_snap | 0 | 0 | — | 0 | — |
| cylinder | after_iterative_snap | 0 | 0 | — | 0 | — |
| cylinder | after_wall_fit | 550 | 36 | 6.545% | 168 | 30.545% |
| cylinder | final | 550 | 36 | 6.545% | 168 | 30.545% |
| sphere | before_snap | 0 | 0 | — | 0 | — |
| sphere | after_iterative_snap | 0 | 0 | — | 0 | — |
| sphere | after_wall_fit | 960 | 0 | 0% | 0 | 0% |
| sphere | final | 960 | 0 | 0% | 0 | 0% |
| gear | before_snap | 0 | 0 | — | 0 | — |
| gear | after_iterative_snap | 0 | 0 | — | 0 | — |
| gear | after_wall_fit | 135 | 10 | 7.407% | 22 | 16.296% |
| gear | final | 135 | 10 | 7.407% | 22 | 16.296% |

전체 boundary face 중 transition owner/vertex-adjacent population은 각각
cylinder `588/1705`, sphere `267/677`, gear `63/275`이었다. 나쁜 면의
대부분은 transition label과도, 그 넓은 정점 proxy와도 겹치지 않았다.

## 판정

`HEX-TRANS-2`는 **measured, falsified**다. 현재 mixed-level realization
출력에서는 나쁜 boundary skew가 transition-sheet 인접부에 집중되지 않는다.
따라서 transition cell만 대상으로 하는 wall-fit 수정이나 repair template를
이 수치만으로 열지 않는다. wall-fit 이후에 발생한 전역적 품질 저하와
transition label 바깥의 손상을 분리하는 별도 candidate-quality transaction
진단이 다음 카드다.

이 수치는 과거 wave 0의 `85/676` fine cylinder 결과와 threshold, 출력 레인,
mesh 설정이 다르므로 직접 비교하지 않는다. 이번 결과는 오직 위 조건의
`skew >= 2.0` 교차표로만 해석한다.

## 다음 카드

`HEX-WALLFIT-CANDIDATE-QUALITY-1`: wall-fit 각 후보의 적용 전후에 영향을
받는 cell neighborhood의 boundary skew, face warpage, signed volume,
boundary face-set을 함께 계산하고, 품질 악화 후보를 rollback하는 메커니즘을
곧바로 구현하지 말고 먼저 report-only로 분포를 측정한다. transition label은
분석 축으로 유지하되 후보 선택 조건으로 사용하지 않는다.
