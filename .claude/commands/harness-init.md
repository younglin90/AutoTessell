---
name: harness-init
description: |
  Auto-Tessell 프로젝트 초기화. 스펙 로딩 → 디렉터리 생성 → 공통 스키마/CLI 생성 →
  Analyzer 서브에이전트 위임 → 벤치마크 STL 생성 → 검증.
  트리거: 프로젝트 초기 세팅, 처음부터 시작, 스캐폴딩 언급 시.
---

# Auto-Tessell 프로젝트 초기화

## 실행 순서

### 1. 스펙 전체 로딩 (필수 — 컨텍스트에 없는 파일만 읽을 것)

1. `CLAUDE.md`
2. `agents/specs/analyzer.md`
3. `agents/specs/preprocessor.md`
4. `agents/specs/strategist.md`
5. `agents/specs/generator.md`
6. `agents/specs/evaluator.md`

### 2. 디렉터리 + 공통 스키마 생성

직접 수행 (서브에이전트 미사용):

1. 디렉터리 생성:
   - `cli/`
   - `core/analyzer/`, `core/preprocessor/`, `core/strategist/`, `core/generator/`, `core/evaluator/`, `core/utils/`
   - `tests/`, `tests/benchmarks/`
   - `desktop/qt_app/` — Qt GUI 모듈 (PySide6 + PyVistaQt)
2. `pyproject.toml` — 의존성 및 extras 정의:
   - 기본: trimesh, meshio, pyvista, pyacvd, pymeshfix, pymeshlab, click, rich, pydantic, structlog
   - `[starter]`: pytetwild (Draft 품질 기본 동작에 필요)
   - `[volume]`: netgen-mesher, mmg
   - `[cad]`: gmsh, cadquery (conda 전용 — pip에서는 설치 실패 가능)
   - `[gui]`: PySide6, pyvistaqt
   - `[dev]`: pytest, pytest-qt, mypy, ruff, black
   - 엔트리포인트: `auto-tessell = "cli.main:cli"`
3. `core/schemas.py` — 5개 에이전트 스펙의 JSON 스키마를 Pydantic 모델로 통합 정의
4. `core/utils/logging.py` — structlog 설정
5. `cli/main.py` — click CLI (analyze, preprocess, strategize, generate, evaluate, run)
   - `run` 커맨드: 포맷 검증 + 성공 footer (output 경로 + "다음 단계" 안내) 포함
6. `tests/conftest.py`

### 3. Analyzer 구현 — analyzer 서브에이전트 위임

- `core/analyzer/file_reader.py` (최소 STL, OBJ, 512MB 게이트 포함)
- `core/analyzer/geometry_analyzer.py`
- `tests/test_analyzer.py`

### 4. Desktop GUI 스캐폴딩 — desktop 서브에이전트 위임

- `desktop/qt_app/drop_zone.py` — DropZone(QLabel) 서브클래스
- `desktop/qt_app/main_window.py` — AutoTessellWindow (DropZone + QProgressBar + PyVista)
- `desktop/qt_app/pipeline_worker.py` — QThread 워커
- `tests/test_qt_app.py` — headless 호환 테스트 (requires_display 마커 포함)

### 5. 벤치마크 STL 생성

trimesh로 sphere, cylinder 생성 → `tests/benchmarks/`

### 6. pytest 설정 (collection 에러 방지)

`pyproject.toml`의 `[tool.pytest.ini_options]`에 반드시 추가:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

`backend/tests`가 존재하면 root `tests/`와 충돌하므로 `testpaths`로 명시적 격리 필수.
`tests/test_desktop_server.py` 상단에 `pytest.importorskip("fastapi")` 추가.

### 7. 검증

```bash
pip install -e ".[dev,starter]" --break-system-packages
pytest tests/ -q --ignore=backend
auto-tessell analyze tests/benchmarks/sphere.stl
```

통과 시 `_plan.md`에 초기화 완료 기록.
실패 시 해당 **서브에이전트**를 재호출하여 수정 (최대 3회).
