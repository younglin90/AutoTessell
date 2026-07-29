---
type: invariant
status: active
updated: 2026-07-26
stability: contract
source_paths: [ROADMAP.md, core/generator/native_tet/boundary_invariant.py, core/generator/native_tet/near_wall.py, core/evaluator/fidelity.py]
tags: [surface-preservation, invariant, boundary]
---

# 표면 보존 불변식

> 볼륨 메싱은 pre-meshing 표면을 바꾸지 않고 최종 mesh에 그대로 보존해야 한다.

이것이 프로젝트 최우선 불변식이다. 품질, cell 수, 속도, fallback 성공보다 앞선다.

## 근거의 종류

| 근거 | 잡아내는 문제 | 대표 용도 |
|---|---|---|
| canonical boundary face key | face 노출·삭제·교체 | tet local op와 stage harness |
| boundary 총면적 | 좌표 이동·triangulation 변화 | tet stage와 fidelity |
| exact/hash surface identity | bitwise 또는 canonical 보존 | permanent gate |
| wall deviation | curved boundary snap drift | native hex cylinder |
| 양방향 distance/envelope | vertex 사이 기하 excursion | fidelity, exact-envelope 계획 |
| patch/entity provenance | 기하는 같지만 semantic이 잘못된 face | multi-input, poly dual, BL, BC |

## 반복 확인된 버그 계열

1. Local topology candidate가 neighborhood를 이동·재구성하면서 duplicate/zero/sign-flipped tet을 만들고, 그 tet만 삭제해 원래 내부면을 boundary로 노출한다.
2. 후속 단계가 vertex를 추가/remap했는데 이전 boundary lock을 재사용해 새 boundary vertex가 CVT/AMIPS/smoothing에 움직인다.
3. Rescue/fallback이 hole·genus·component를 메워 겉보기에는 닫혔지만 원본과 다른 mesh를 만든다.

검증된 수정 패턴은 transaction이다. 전체 influence region에서 candidate를 시뮬레이션하고 positive orientation과 동일한 boundary 계약을 확인한 뒤, candidate 전체를 commit하거나 전체 reject한다. 문제 cell만 부분 정리하는 방식은 안전하지 않다.

면적만 같다고 face set, geometry, genus, patch semantic이 같지는 않다. 가장 강한 조합은 topology key + area/coordinate + provenance + 양방향 envelope/fidelity다.
