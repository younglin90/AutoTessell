---
type: subsystem
status: active
updated: 2026-07-26
stability: implemented
source_paths: [core/evaluator/quality_checker.py, core/evaluator/native_checker.py, core/evaluator/report.py, core/evaluator/metrics.py, core/evaluator/fidelity.py]
tags: [evaluator, quality, gates]
---

# 평가기와 품질 게이트

평가에는 네 종류의 입력이 들어간다.

1. OpenFOAM `checkMesh` 또는 `NativeMeshChecker`의 topology/geometry 검사
2. `AdditionalMetricsComputer`의 직접 분포 지표
3. `GeometryFidelityChecker`의 source-to-output fidelity
4. 선택한 `MeshStrategy`, tier, quality level, BL 문맥

`MeshQualityChecker`는 요청 시 native checker를 쓰고, 아니면 OpenFOAM을 시도한 뒤 `checkMesh`가 없으면 native로 fallback한다. `NativeMeshChecker`는 points/faces/owner/neighbour/boundary를 읽어 face/cell geometry를 만들고 topology count, volume, determinant proxy, non-orthogonality, internal/boundary skew, AR, concavity/warpage와 poly/hex Phase-0 metric을 계산한다.

## 판정 구성

`EvaluationReporter`는 draft/standard/fine 임계값에서 시작해 tier와 BL별 policy를 적용한다. 의미 있는 negative/inverted volume, non-positive minimum volume/determinant는 hard failure다. Non-ortho와 skew는 quality별 한계가 있고 AR과 cell-volume ratio는 soft quality failure다. Fidelity는 surface area와 거리 failure를 추가할 수 있다. 최종 결과는 structured failed check와 parameter 추천을 가진 `PASS`, `PASS_WITH_WARNINGS`, `FAIL`이다.

고 AR은 네 증거가 모두 존재하고 통과할 때만 정렬된 anisotropy로 인정된다: principal-axis alignment, 이웃 stretch-direction consistency, surface-tangent alignment, surface-normal alignment. 증거가 없거나 약하면 기존 scalar AR gate를 유지한다.

## Fidelity

Fidelity checker는 `polyMesh`에서 geometry patch를 골라 polygon face를 triangulate하고 source/output surface를 sampling한다. Symmetric Hausdorff 근사, RMS/p95/p99, relative distance, surface-area deviation, normal deviation, feature score를 보고한다. Orchestrator에서는 best-effort이므로, 엔진 연구의 permanent gate가 필요한 곳에서는 더 강한 계약을 사용한다.

`report.py`의 tier/BL별 임계 완화는 policy일 뿐 안전성 증명이 아니다. Exact surface identity, wall deviation, zero negative volume, cell census, strict xfail 같은 영구 게이트가 더 강한 연구 합격 기준이다.
