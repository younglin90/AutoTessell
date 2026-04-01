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

1. 디렉터리 생성: `cli/`, `core/analyzer/`, `core/preprocessor/`, `core/strategist/`, `core/generator/`, `core/evaluator/`, `core/utils/`, `tests/`, `tests/benchmarks/`
2. `pyproject.toml` — 의존성, `auto-tessell = "cli.main:cli"` 엔트리포인트
3. `core/schemas.py` — 5개 에이전트 스펙의 JSON 스키마를 Pydantic 모델로 통합 정의
4. `core/utils/logging.py` — structlog 설정
5. `cli/main.py` — click CLI (analyze, preprocess, strategize, generate, evaluate, run)
6. `tests/conftest.py`

### 3. Analyzer 구현 — analyzer 서브에이전트 위임

- `core/analyzer/file_reader.py` (최소 STL, OBJ)
- `core/analyzer/geometry_analyzer.py`
- `tests/test_analyzer.py`

### 4. 벤치마크 STL 생성

trimesh로 sphere, cylinder 생성 → `tests/benchmarks/`

### 5. 검증

```bash
pip install -e ".[dev]" --break-system-packages
pytest tests/test_analyzer.py -v
auto-tessell analyze tests/benchmarks/sphere.stl
```

통과 시 `_plan.md`에 초기화 완료 기록.
실패 시 **analyzer 서브에이전트**를 재호출하여 수정 (최대 3회).
