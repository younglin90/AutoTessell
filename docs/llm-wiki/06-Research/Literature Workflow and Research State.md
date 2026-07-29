---
type: research
status: active
updated: 2026-07-26
stability: measured
source_paths: [docs/references/literature/native_tet, docs/references/literature/native_hex, docs/references/literature/native_poly, docs/references/literature/native_tri, ROADMAP.md]
tags: [literature, evidence, roadmap]
---

# 문헌 워크플로와 연구 상태

각 native 엔진에는 두 권위 자료가 있다.

- **evidence matrix**: 완독 논문, claim audit, 생산 결정, 카드 acceptance를 기록
- **literature-integrated development plan**: 측정·구현·rollback·phase decision 순서를 규정

## 작업 규칙

1. canonical script로 현재 실패를 먼저 측정한다.
2. 문헌 근거가 있는 단일 메커니즘을 고른다.
3. 작은 default-off 카드로 구현한다.
4. permanent gate와 surface invariant를 보존한다.
5. 실측 이득만 남기고, 기각 결과는 기록하며 dead mechanism은 제거한다.
6. plan, evidence matrix, roadmap/changelog를 필요한 범위에서 갱신한다.
7. 정확성과 결정론이 확립되기 전에는 병렬화하지 않는다.

## 엔진별 방향

| 엔진 | 근거 기반 방향 | 주의점 |
|---|---|---|
| native tet | protected-CDT와 epsilon-Wild 의미 분리, transactional recovery/topology/optimization, FSL/FLOW-2 | 혼합 루프가 논문 전체 보장을 상속한다고 말할 수 없음 |
| native hex | actual cell census, adaptive transition matching, feature/patch provenance | ECR/HexOpt와 coherent-sheet는 보편 설명이 아니었음 |
| native poly | classified primal-to-dual, star validity, concave/non-manifold repair, FV metric | point placement로 모든 invalid topology를 고칠 수 없음 |
| native tri | guarded Botsch/Dunyach operator, exact predicate, curvature sizing, shell provenance | 기반 구현이 아직 production route에 연결되지 않음 |
| native quad | 4-RoSy/multires 진단과 honest triangle remainder | orientation field만으로 valid quad mesh가 되지 않음 |

Roadmap은 유용하지만 통합 계획과 최근 commit보다 늦을 수 있다. [[Contradictions and Open Questions|불일치 원장]]은 이를 지우지 않고 명시한다.
