---
type: architecture
status: active
updated: 2026-07-26
stability: implemented
source_paths: [CLAUDE.md, core/pipeline/orchestrator.py, core/schemas.py, ROADMAP.md]
tags: [architecture, pipeline, native-first]
---

# 시스템 개요

AutoTessell에는 개념적으로 두 제품이 있다.

1. **3D 표면 메싱**: 표면을 분석·수리하고, topology·feature·provenance·기하 drift 계약을 지키는 triangle 또는 quad-dominant 표면을 만든다.
2. **3D 볼륨 메싱**: 선택한 표면 계약을 그대로 보존하면서 tet·hex-dominant·polyhedral cell로 내부를 채우고, 필요하면 wall layer를 넣은 뒤 OpenFOAM topology와 품질 보고서를 만든다.

코어 Python은 5단계 파이프라인이다.

| 단계 | 주 담당 파일 | 출력 |
|---|---|---|
| Analyzer | `core/analyzer/geometry_analyzer.py` | 기하·topology 문제·flow 추정·tier 호환성을 담은 `GeometryReport` |
| Preprocessor | `core/preprocessor/pipeline.py` | 정규화된 표면/CAD 경로와 `PreprocessedReport` |
| Strategist | `strategy_planner.py`, `tier_selector.py` | 엔진·크기·BL·refinement·fallback을 담은 `MeshStrategy` |
| Generator | `core/generator/pipeline.py`, tier adapter | `constant/polyMesh`와 `GeneratorLog` |
| Evaluator | `core/evaluator/*` | `QualityReport`, fidelity, 추천, 판정 |

`PipelineOrchestrator`가 전체 생명주기와 산출물 저장을 소유한다. Tier adapter는 엔진별 함수 인자를 공통 계약으로 바꾼다. Native와 외부 엔진은 동일한 `polyMesh` 출력 계약과 evaluator를 공유한다.

## 설계 경계

- Python은 orchestration, schema, UI/API mapping, policy와 많은 실험적 geometry pass를 담당한다.
- NumPy/SciPy가 현재 수치 기반이며 C/C++ 확장이 predicate, topology parsing, snap candidate, metric을 가속한다.
- OpenFOAM은 출력 대상이자 선택적 validator이지 유일한 checker가 아니다.
- 외부 엔진은 참조/fallback이다. Native-first는 선택 정책이지 모든 native 엔진 완성을 뜻하지 않는다.
- `backend/` SaaS 경로와 `desktop/server.py` 로컬 앱 API는 상태·저장·결제 모델이 다르다.

관련 문서: [[Pipeline Lifecycle|파이프라인 생명주기]], [[Native-First Routing|Native-first 라우팅]], [[Data Contracts|데이터 계약]].
