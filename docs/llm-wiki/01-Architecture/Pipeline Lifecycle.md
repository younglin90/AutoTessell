---
type: architecture
status: active
updated: 2026-07-26
stability: implemented
source_paths: [core/pipeline/orchestrator.py, core/generator/pipeline.py, core/generator/tier_layers_post.py]
tags: [pipeline, retry, fallback]
---

# 파이프라인 생명주기

## 한 번의 실행

1. 인자를 검증하고 하나 이상의 입력 표면을 수집한다.
2. 기하를 분석해 `geometry_report.json`을 저장하고 호환 tier를 추정한다.
3. CAD 또는 표면을 전처리한다. CAD는 Netgen에 원본 전달할 수 있고, 표면은 변환→L1 repair→선택적 L2 remesh→선택적 L3 repair→최종 검증을 거친다.
4. `MeshStrategy`를 만들고 명시적 cell size/cap, BL, tier parameter를 적용한다. Strict-tier이면 fallback을 제거한다.
5. `MeshGenerator`가 tier 이름을 정규화하고 `polyMesh`를 비운 뒤 순서대로 실행한다. 예외는 failed `TierAttempt`로 바꾸며 첫 성공에서 멈춘다.
6. 모든 tier가 실패하면 winding-number/voxel 기반 표면 재구성을 한 번만 시도하고 같은 tier sequence를 재실행할 수 있다.
7. 선택적으로 post-generation 경계층 엔진을 실행한다. Native BL, cfMesh/OpenFOAM, Netgen, Gmsh, pyHyp, MeshKit, SU2/Hexpress 계열과 extrusion helper가 라우팅 대상이다.
8. 요청 시 OpenFOAM case dictionary와 boundary condition을 쓴다.
9. topology·geometry·추가 지표·표면 fidelity를 평가해 판정을 만든다.
10. `auto_retry`가 허용하면 이전 `QualityReport`를 Strategist에 넣어 전략을 다시 세우고 반복한다.

## 재시도 정책

| 값 | 최대 시도 | 의미 |
|---|---:|---|
| `off` | 1 | 기본값, 실패 후 사용자 결정 |
| `once` | 2 | 평가 피드백을 반영한 한 번의 재시도 |
| `continue` | `max_iterations` | 하위호환 bounded loop |

Strict-tier는 사용자가 고른 tier를 유지하고 fallback을 비운다. 재시도가 같은 cell 수를 반복하면서 전략 변화가 없으면 조기 중단할 수 있다.

## 실패 격리

- Tier crash는 `GeneratorLog` 데이터가 되어 fallback chain을 살린다.
- Fidelity나 선택적 후처리 실패는 hard contract를 깨지 않는 한 warning이다.
- 무거운 native 작업은 UI 프로세스 밖에서 실행해야 한다. PyTetWild/fTetWild와 반복 native-tet는 특히 subprocess 격리가 필요하다.
- Writer 성공과 품질 `PASS`는 별개다.
