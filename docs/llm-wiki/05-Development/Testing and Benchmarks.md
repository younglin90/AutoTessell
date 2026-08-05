---
type: development
status: active
updated: 2026-07-26
stability: contract
source_paths: [tests, tests/stl, scripts, harness, pyproject.toml]
tags: [tests, benchmarks, gates]
---

# 테스트와 벤치마크

현재 저장소에는 root 기준 약 220개의 `test_*.py` 모듈이 있고 backend 테스트와 benchmark script가 별도로 있다. 신뢰도는 하나의 전체 숫자가 아니라 계약별 suite로 구성된다.

| 구분 | 예시 | 증명하는 것 |
|---|---|---|
| schema/policy | schema, strategist, cap-aware, tier alias/route | parameter와 dispatch 계약 |
| reader/writer | native reader, CAD, polyMesh parser/writer, export | format과 topology round-trip |
| core geometry | predicate, AABB, winding/inside, topology, self-intersection | 공통 수치 primitive |
| engine unit | tet phase, hex octree/snap/match, poly dual, tri loop | local mechanism과 guard |
| permanent gate | tet thin-sliver/solid/torus, hex/poly solid, BL topology/persistence | 타협 불가 실측 불변식 |
| integration | orchestrator, CLI, desktop, E2E native | 단계 연결과 interface mapping |
| 환경 의존 | OpenFOAM, extension parity, GUI/visual/display | runtime별 동작 |

## Canonical corpus

`tests/stl/verify_autoresearch_mesh_matrix.py`는 문헌 캠페인의 cross-shape volume verifier다. Native-tet에는 hard-shape와 thin-sliver lane이 있고, native-hex는 cube/cylinder와 curved/transition 사례, native-poly는 cube/sphere/cylinder와 multi-patch/non-manifold fixture를 쓴다. `tests/stl/bench_native_tri.py`는 legacy L2 surface 기준선을 만든다.

`research/quality-harness/`와 `tests/stl/*.json/tsv`의 결과는 근거지만 많은 파일이 mutable WIP다. 결과에는 정확한 script, shape, quality, cell target, BL, timeout, commit/worktree, checker 정의를 함께 적어야 한다.

## 실행 제약

- 같은 heavy pytest target을 nested/duplicate runner로 반복 호출하지 않는다. Native-tet가 성공 뒤 interpreter crash를 일으킨 전례가 있다.
- PyTetWild/fTetWild와 GUI-heavy 작업은 subprocess로 격리한다.
- slow, display, visual, OpenFOAM 의존을 marker로 구분한다.
- 카드 acceptance command, permanent gate, 관련 canonical bench가 모두 green일 때만 닫는다. 부정적 실측도 정식 결과다.
