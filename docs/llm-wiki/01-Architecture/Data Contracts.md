---
type: architecture
status: active
updated: 2026-07-26
stability: implemented
source_paths: [core/schemas.py, core/pipeline/orchestrator.py]
tags: [schemas, pydantic, contracts]
---

# 데이터 계약

`core/schemas.py`는 파이프라인 단계, UI, 저장 보고서가 공유하는 언어다.

| 계약 | 주요 내용 | 흐름 |
|---|---|---|
| `GeometryReport` | 파일, bounds, surface/feature 통계, issue, flow, tier 호환성 | Analyzer → Preprocessor/Strategist/UI |
| `PreprocessedReport` | 수행 단계, watertight/manifold, surface quality level | Preprocessor → Strategist/UI |
| `MeshStrategy` | mesh type, tier/fallback, domain, sizing, BL, refinement, tier parameter | Strategist → Generator/BL/Evaluator |
| `TierAttempt` | tier, status, 시간, 오류, cell/point 통계 | adapter → `GeneratorLog` |
| `GeneratorLog` | 전체 tier 시도와 성공 tier | Generator → Orchestrator/UI |
| `CheckMeshResult` | topology, non-ortho, skew, AR, volume, determinant, Phase-0 metric | checker → Reporter |
| `GeometryFidelity` | 양방향 거리, 상대 Hausdorff, 면적 편차, normal/feature score | fidelity checker → Reporter |
| `AdditionalMetrics` | cell volume, face/edge 분포, 선택적 진단 | metrics → Reporter |
| `QualityReport` | verdict, hard/soft failure, 추천, checker/fidelity/BL 근거 | Reporter → UI/재시도 |

`QualityLevel`, `SurfaceQualityLevel`, `MeshType`, `Verdict`, `AutoRetryMode` enum이 core의 문자열 drift를 줄인다. 다만 interface에서도 canonical-name mapping을 하므로 중복 policy는 [[Contradictions and Open Questions|불일치 원장]]에 기록한다.

Schema는 계속 확장 중이다. Poly FV metric, hex census, BL provenance, assembly provenance, alignment-aware AR 필드가 추가됐지만, 필드가 있다는 사실만으로 모든 producer가 값을 채운다고 볼 수는 없다.
