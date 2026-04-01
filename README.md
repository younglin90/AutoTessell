# Auto-Tessell

CAD/메쉬 파일 → OpenFOAM polyMesh 자동 생성 도구.
오픈소스 메쉬 라이브러리 총동원, 사용자 개입 최소화.

```bash
auto-tessell run model.stl -o ./case --quality draft      # ~1초, 빠른 검증
auto-tessell run model.stl -o ./case --quality standard    # ~수분, 엔지니어링
auto-tessell run model.step -o ./case --quality fine        # ~30분+, 최종 CFD
```

## 주요 기능

- **2-Phase Progressive 파이프라인**: 표면 메쉬(L1→L2→L3) + 볼륨 메쉬(Draft→Standard→Fine)
- **5-Agent 아키텍처**: Analyzer → Preprocessor → Strategist → Generator ↔ Evaluator
- **Windows 네이티브 지원**: OpenFOAM 없이도 메쉬 생성 + 품질 검증 가능
- **다양한 입력 포맷**: STL, OBJ, PLY, STEP, IGES, BREP, Gmsh .msh, VTK 등
- **자동 품질 검증**: NativeMeshChecker + Hausdorff 거리 기반 표면 충실도
- **Godot 4.3 데스크톱 GUI**: 3D 메쉬 뷰어 + WebSocket 실시간 진행상황
- **331+ 테스트**: 단위 + 통합 + 벤치마크

## 설치

```bash
# 기본 설치
pip install -e .

# 선택 의존성
pip install -e ".[cad]"       # STEP/IGES 지원 (cadquery)
pip install -e ".[netgen]"    # Netgen 볼륨 메쉬
pip install -e ".[volume]"    # TetWild 볼륨 메쉬
pip install -e ".[desktop]"   # Godot GUI 백엔드 서버
pip install -e ".[dev]"       # 개발 도구 (pytest, ruff, mypy)
```

## 빠른 시작

### CLI

```bash
# 분석만
auto-tessell analyze model.stl

# 전체 파이프라인 (자동)
auto-tessell run model.stl -o ./case --quality draft

# 전략만 확인 (dry-run)
auto-tessell run model.stl -o ./case --quality standard --dry-run

# 특정 Tier 강제
auto-tessell run model.stl -o ./case --tier tetwild --quality draft
```

### 데스크톱 GUI (Godot)

```bash
# 1. Python 백엔드 서버 실행
python -m desktop.server

# 2. Godot 4.3에서 godot/project.godot 열기
# 3. F5 (Play) → 파일 선택 → 메쉬 생성
```

## 아키텍처

```
┌─────────────────────────────────────────────┐
│  Godot GUI (.exe)                           │  ← MIT, Windows 네이티브
│  ↕ WebSocket (ws://localhost:9720)          │
├─────────────────────────────────────────────┤
│  desktop/server.py (FastAPI)                │  ← 실시간 진행상황 스트리밍
├─────────────────────────────────────────────┤
│  core/ (Python Backend)                     │
│                                             │
│  Analyzer → Preprocessor → Strategist       │
│                ↓                             │
│           Generator ↔ Evaluator (재시도)     │
│                ↓                             │
│         OpenFOAM polyMesh                   │
└─────────────────────────────────────────────┘
```

### 2-Phase Progressive 파이프라인

**Phase 1: 표면 메쉬 (Surface)**

| 레벨 | 엔진 | 소요 시간 |
|------|------|----------|
| L1 (Repair) | pymeshfix + trimesh | 초 |
| L2 (Remesh) | pyACVD + pymeshlab | 초~분 |
| L3 (AI fix) | meshgpt-pytorch | 분 (GPU) |

**Phase 2: 볼륨 메쉬 (Volume)**

| 품질 | 엔진 | 소요 시간 |
|------|------|----------|
| Draft | TetWild | ~1초 |
| Standard | Netgen / cfMesh | ~수분 |
| Fine | snappyHexMesh + BL | ~30분+ |

## 품질 레벨

| 지표 | Draft | Standard | Fine |
|------|-------|---------|------|
| Max Non-orthogonality | < 85° | < 70° | < 65° |
| Max Skewness | < 8.0 | < 6.0 | < 4.0 |
| Max Aspect Ratio | < 500 | < 200 | < 100 |
| Hausdorff Relative | < 10% | < 5% | < 2% |

## 테스트

```bash
# 전체 테스트
pytest tests/ -v

# 모듈별
pytest tests/test_analyzer.py -v
pytest tests/test_evaluator.py -v
pytest tests/test_generator.py -v

# 벤치마크 (실제 메쉬 생성)
pytest tests/test_integration.py -v
```

## 프로젝트 구조

```
auto-tessell/
├── cli/                    # CLI (click + rich)
├── core/
│   ├── analyzer/           # 파일 로딩 + 지오메트리 분석
│   ├── preprocessor/       # L1→L2→L3 표면 전처리
│   ├── strategist/         # QualityLevel별 전략 수립
│   ├── generator/          # 볼륨 메쉬 + PolyMeshWriter
│   ├── evaluator/          # checkMesh + NativeMeshChecker
│   ├── pipeline/           # Orchestrator
│   └── utils/              # OpenFOAM 래퍼, 로깅
├── desktop/                # FastAPI WebSocket 서버
├── godot/                  # Godot 4.3 GUI
├── tests/                  # 331+ 테스트
└── agents/specs/           # 에이전트 스펙 문서
```

## 라이선스 요약

| 라이브러리 | 라이선스 | 상업 사용 |
|-----------|---------|----------|
| trimesh, pyACVD, pymeshfix | MIT/BSD | ✅ |
| TetWild (pytetwild) | MPL-2.0 | ✅ |
| Netgen | LGPL-2.1 | ✅ (동적 링크) |
| OpenFOAM | GPL | ✅ (서버 내부) |
| MMG | LGPL-3.0 | ✅ (동적 링크) |
| Godot | MIT | ✅ |
| meshgpt-pytorch | MIT | ✅ |
| MeshAnythingV2 | S-Lab 1.0 | ❌ (비상업, 허가 필요) |
