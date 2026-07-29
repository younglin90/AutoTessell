---
type: interface
status: active
updated: 2026-07-26
stability: implemented
source_paths: [cli/main.py, desktop/qt_main.py, desktop/qt_app/main_window.py, desktop/server.py, desktop/electron/main.js]
tags: [cli, qt, fastapi, electron]
---

# CLI와 데스크톱

## CLI

`auto-tessell` Click entry point에는 단계별 `analyze`, `preprocess`, `strategize`, `generate`, `evaluate`, 전체 `run`, `doctor`, `smoketest`, tier 목록, stats/mesh info, cleanup, benchmark summary, convert와 여러 export command가 있다. CLI가 `PipelineOrchestrator`와 가장 직접적으로 대응하며 mesh type, tier, cell budget, BL, retry, native preference, strict tier, validator, tier override를 지원한다.

## Qt 앱

`auto-tessell-qt`는 PySide6 앱을 시작한다. `qt_app/main_window.py`가 큰 desktop workflow를 소유하고, pipeline worker, preview, BC selection/overlay, preset, batch, history, compare, PDF, engine policy, error recovery가 보조 모듈로 분리돼 있다. 무거운 작업은 Qt event loop 밖으로 위임한다.

## 로컬 웹 데스크톱

`desktop/server.py`는 upload, multi-surface job, cancel, surface diagnosis, WebSocket progress, meshing, mesh/surface 조회, export/download, demo를 제공하는 FastAPI 앱이다. 로컬 job state를 저장하고 UI parameter를 orchestrator 인자로 바꾼다. `desktop/web/`가 browser viewer와 control을 제공한다.

Electron package는 로컬 FastAPI web GUI를 감싸는 shell이지 별도 mesher가 아니다.
