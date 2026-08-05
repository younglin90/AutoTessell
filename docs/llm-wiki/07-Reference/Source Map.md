---
type: reference
status: active
updated: 2026-07-26
stability: implemented
source_paths: [core, cli, desktop, backend, frontend]
tags: [source, symbols, navigation]
---

# 소스 지도

## 파이프라인

- `core/pipeline/orchestrator.py::PipelineOrchestrator.run` — 전체 생명주기와 retry
- `core/schemas.py` — 단계 공통 Pydantic 계약
- `core/analyzer/geometry_analyzer.py::GeometryAnalyzer.analyze` — geometry report
- `core/preprocessor/pipeline.py::Preprocessor.run` — L1/L2/L3
- `core/strategist/tier_selector.py::TierSelector.select` — tier 선택
- `core/strategist/strategy_planner.py::StrategyPlanner.plan` — 구체 전략
- `core/generator/pipeline.py::MeshGenerator.run` — tier 실행/fallback

## 엔진

- `core/generator/native_tet/mesher.py::generate_native_tet`
- `core/generator/native_tet/harness.py::run_native_tet_harness`
- `core/generator/native_tet/boundary_invariant.py::check_boundary_invariant`
- `core/generator/native_hex/mesher.py::generate_native_hex`
- `core/generator/native_hex/match_repair.py::run_match_repair`
- `core/generator/native_poly/dual.py::tet_to_poly_dual`
- `core/generator/native_poly/harness.py::run_native_poly_harness`
- `core/preprocessor/native_tri/operator_loop.py::OperatorTransaction`
- `core/preprocessor/native_tri/bijective_shell.py::build_linear_bijective_shell`
- `core/preprocessor/native_remesh/quad_dominant.py::native_quad_dominant_remesh`
- `core/layers/native_bl.py::generate_native_bl`
- `core/generator/tier_layers_post.py::LayersPostGenerator`

## 품질·IO

- `core/evaluator/native_checker.py::NativeMeshChecker.run`
- `core/evaluator/quality_checker.py::MeshQualityChecker.run`
- `core/evaluator/report.py::EvaluationReporter.evaluate`
- `core/evaluator/fidelity.py::GeometryFidelityChecker.compute`
- `core/utils/predicates_staged.py`, `core/utils/_shewchuk/`
- `core/generator/polymesh_writer.py::write_generic_polymesh`
- `core/utils/polymesh_reader.py`
- `core/utils/mesh_exporter.py::export_mesh`

## 인터페이스

- `cli/main.py::run` — 전체 CLI
- `desktop/server.py` — local FastAPI job API
- `desktop/qt_app/main_window.py::AutoTessellWindow` — Qt UI
- `products/web/api/main.py`, `products/web/api/api/` — SaaS API
- `products/web/app/app/` — Next.js UI
