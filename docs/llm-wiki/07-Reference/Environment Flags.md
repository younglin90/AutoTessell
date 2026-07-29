---
type: reference
status: active
updated: 2026-07-26
stability: working-tree
source_paths: [core/generator/native_tet/mesher.py, core/generator/native_hex/mesher.py, core/layers/native_bl.py, core/strategist/tier_selector.py]
tags: [environment, flags, experiments]
---

# 환경변수 플래그

AutoTessell은 runtime dependency, 진단, 연구 메커니즘에 `AUTO_TESSELL_*` 환경변수를 사용한다. 이 문서는 flag family를 설명하며 정확한 spelling과 default는 반드시 호출부에서 확인한다.

| 계열 | 예시 | 의미 |
|---|---|---|
| native-tet routing | `NATIVE_FTETWILD_MODE`, `USE_FTETWILD_LOOP`, `P4C_PYTETWILD` | Wild/reference와 parity lane |
| tet 초기화/recovery | `SEED_GWN`, `PARALLEL_DELAUNAY`, `TET_OFFSET_RING`, BSP/recovery switch | seed, region 분류, constraint recovery |
| tet quality card | `FSL_WAVE1`, `TET_FLOW2`, `CVT3D_*`, `STELLAR_*`, `NNN*`, `RRR*`, `VVV*` | local topology/smoothing 연구 메커니즘 |
| tet final polish | `TET_QUALITY1_OFF`, `TET_CFD_QUALITY`, `VAL1_OFF` | quality/validation stage |
| hex quality | `HEX_WALLFIT_OFF`, BL budget, buffer/snap, `HEX_MATCH2` | post-snap과 transition repair |
| BL | engine, Taubin, cavity, collision, persistence flag | wall-layer 생성과 진단 |
| policy/runtime | tier history JSON, native preference, dependency path | 선택과 환경 동작 |

## 안전 규칙

- 새 quality mechanism은 카드가 이득과 영구 게이트 안전성을 입증하기 전 기본 OFF다.
- `*_OFF` 이름은 해당 코드가 기본 ON임을 뜻한다. 실험처럼 보인다고 opt-in이라 가정하지 않는다.
- Flag 상태는 benchmark identity 일부이므로 export 값을 기록한다.
- 함수 내부의 임시 환경변수 변경은 반드시 원래 값으로 복원한다.
- Rescue flag가 topology, provenance, fidelity gate를 우회하면 안 된다.

현재 native-tet 작업트리에는 역사적 card flag가 많고 opt-out 형태의 default-on block도 있다. 재현성과 유지보수 위험으로 [[Contradictions and Open Questions|불일치 원장]]에 기록한다.
