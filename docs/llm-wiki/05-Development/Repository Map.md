---
type: reference
status: active
updated: 2026-07-26
stability: implemented
source_paths: [CLAUDE.md, core, cli, desktop, backend, frontend, tests, docs]
tags: [repository, map]
---

# 저장소 지도

조사한 스냅샷에는 `core/`, `cli/`, `desktop/`, `products/web/api/`에 약 417개 Python 파일, root에 약 220개 test module, 200개가 넘는 문서 파일이 있다.

| 경로 | 책임 |
|---|---|
| `core/analyzer/` | format load, geometry/topology 통계, issue/feature 진단 |
| `core/preprocessor/` | conversion, L1/L2/L3, native tri/quad surface 연구 |
| `core/strategist/` | tier 선택, sizing, refinement, retry 조정 |
| `core/generator/` | tier pipeline, adapter, native tet/hex/poly, polyMesh writer |
| `core/layers/` | native BL, layer front, tet subdivision, poly transition |
| `core/evaluator/` | native/OpenFOAM checker, fidelity, metric, verdict |
| `core/pipeline/` | E2E orchestration과 artifact 저장 |
| `core/utils/` | geometry, predicate, provenance, OpenFOAM IO, export, acceleration |
| `cli/` | Click command와 terminal workflow |
| `desktop/` | Qt, local FastAPI, web UI, Electron |
| `products/web/app/` | Next.js SaaS frontend |
| `products/web/api/` | SaaS API, DB, worker, payment, storage, 별도 mesh adapter |
| `auto_tessell_core/` | pybind11/C/C++ extension build |
| `tests/` | unit, integration, permanent gate, STL corpus, benchmark |
| `scripts/` | validation, benchmark, smoke, 운영 entry |
| `research/quality-harness/` | 연구 plan, run, probe, mutable evidence |
| `docs/references/literature/` | 완독 note, evidence matrix, 통합 개발 계획 |
| `vendor/dependencies/`와 참조 source tree | vendored/comparison 구현, 자동 product path 아님 |

중요 symbol은 [[Source Map|소스 지도]]에서 바로 찾을 수 있다.
