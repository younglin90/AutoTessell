---
type: architecture
status: active
updated: 2026-07-26
stability: implemented
source_paths: [core/strategist/tier_selector.py, core/strategist/strategy_planner.py, core/generator/pipeline.py, core/generator/_tier_native_common.py]
tags: [routing, tiers, fallback, native-first]
---

# Native-first 라우팅

라우팅은 세 층이다.

1. `TierSelector`가 alias, explicit hint, surface quality, mesh family, 기하 복잡도, policy filter, 선택적 benchmark-history hint를 해석한다.
2. `StrategyPlanner`가 실제 sizing, refinement, BL, tier parameter를 만들고 평가 피드백으로 재시도 전략을 조정한다.
3. `MeshGenerator`가 선택 tier와 fallback을 순서대로 실행하고 모든 시도를 기록한다.

## 우선순위

- 명시적 `tier_hint`가 최우선이다.
- Critical input은 robust fallback 쪽으로 라우팅하되 요청한 mesh family를 가능한 앞에 둔다.
- L3 AI repair 입력에서 tet은 TetWild, hex/poly는 cfMesh가 우선이다.
- 명시적 `mesh_type`은 같은 family primary를 고르며, strict가 아니면 다른 family가 마지막 안전망으로 남을 수 있다.
- `prefer_native_tier`는 auto 선택을 native 쪽으로 기울이지만 compatibility 검사를 없애지 않는다.
- `strict_tier`는 orchestrator가 fallback을 비우고 재시도 때 forced tier를 복원해 강제한다.

## Native adapter

`tier_native_tet.py`, `tier_native_hex.py`, `tier_native_poly.py`가 `MeshStrategy`를 엔진 호출로 변환한다. `_tier_native_common.py`는 STL load, kwarg filtering, 결과 정규화, 품질 grading, `TierAttempt` 생성을 공유한다. Poly adapter는 native-tet harness 뒤 dual 변환을 수행하고, hex/tet adapter는 각 native 엔진을 호출한다.

Native-first는 제품 계약과 구현 소유권을 AutoTessell 쪽으로 옮기는 정책이다. SciPy, trimesh-compatible 객체, optional extension, reference implementation을 전혀 쓰지 않는다는 뜻은 아니다.
