# Auto-Tessell — CLAUDE.md

CAD/메쉬 파일 → OpenFOAM polyMesh 자동 생성 CLI 도구.
오픈소스 메쉬 라이브러리 총동원, 사용자 개입 최소화.

## 개발 단계

**Phase 1 (현재): CLI** — 리눅스에서 직접 실행·테스트
**Phase 2: Web SaaS** — CLI 완성 후 FastAPI + Next.js 래핑

```bash
auto-tessell input.stl -o ./case                    # 자동 모드
auto-tessell input.step -o ./case --tier netgen --element-size 0.01 --verbose  # 개발 모드
```

## 5-Agent 하네스 아키텍처

```
Analyzer → Preprocessor → Strategist → Generator ↔ Evaluator (최대 3회 반복)
```

에이전트 간 통신은 JSON 파일 기반. 상세 스펙은 `agents/specs/*.md` 참조.

| 에이전트 | 상세 스펙 | 핵심 역할 |
|---------|----------|----------|
| Analyzer | `agents/specs/analyzer.md` | 입력 파일 분석, geometry_report.json 생성 |
| Preprocessor | `agents/specs/preprocessor.md` | 표면 수리/리메쉬 L1→L2→L3 점진적 품질 |
| Strategist | `agents/specs/strategist.md` | 품질 레벨·Tier 선택, 파라미터 결정, 재시도 전략 |
| Generator | `agents/specs/generator.md` | 2-Phase 메쉬 생성 (Surface→Volume), fallback 전환 |
| Evaluator | `agents/specs/evaluator.md` | checkMesh + 품질 검증, 품질 레벨별 PASS/FAIL 판정 |

## 2-Phase Progressive 파이프라인

### Phase 1: 표면 메쉬 (Surface Mesh)

저품질 → 고품질 순서로 점진적 개선. 각 단계는 gate 통과 시에만 다음 단계로 이행.

| 레벨 | 엔진 | 소요 시간 | 조건 |
|------|------|----------|------|
| L1 (Repair) | pymeshfix + trimesh | 초 단위 | 기본 수리 |
| L2 (Remesh) | pyACVD + geogram RVD | 초~분 | edge_length_ratio > 100 또는 > 200k 면 |
| L3 (AI fix) | MeshAnything (GPU) | 분 단위 | L2 후에도 watertight 실패 시 최후 수단 |

Gate: watertight + manifold 통과 시 Volume Phase 진입

### Phase 2: 볼륨 메쉬 (Volume Mesh)

품질 레벨(QualityLevel)에 따라 선택. 실패 시 다음 단계로 fallback.

| 레벨 | 엔진 | 메쉬 타입 | 소요 시간 | 라이선스 |
|------|------|----------|----------|---------|
| Draft | TetWild (epsilon large) | Tet | ~30초 | MPL-2.0 |
| Standard | Netgen 또는 cfMesh | Tet / Hex-dominant | ~분 | LGPL-2.1 / GPL |
| Fine | snappyHexMesh + BL 또는 MMG | Hex-dominant / Tet | ~30분+ | GPL / LGPL-3.0 |

### 지원 메쉬 타입 (볼륨)

| 타입 | 설명 | 주요 엔진 |
|------|------|---------|
| 정렬격자 (Structured) | 블록 기반, PLOT3D/CGNS 출력 | gridgen, ICEM CFD style |
| 비정렬 Tetrahedral | 복잡 형상에 범용 | TetWild, Netgen, MeshPy(TetGen), MMG |
| Hex-dominant | 경계층 품질 우수 | snappyHexMesh, cfMesh, classy_blocks |
| Polygonal/Polyhedral | 셀 수 최소화 | OpenFOAM polyDualMesh, geogram |

모든 타입을 지원하며, 형상·품질 레벨·솔버 요구사항에 따라 자동 선택.

## 입력 포맷

### CAD — 표준 중립 포맷
STL, STEP(.stp/.step), IGES(.igs/.iges), VDA-FS(.vda), OBJ, PLY, OFF, 3MF, BREP

### CAD — 커널 기반
Parasolid(.x_t/.x_b), ACIS(.sat/.sab)

### CAD — 네이티브 (상용, pythonocc/IfcOpenShell 등 경유)
CATIA V4/V5/V6, SolidWorks(.sldprt/.sldasm), PTC Creo/Pro·E(.prt/.asm),
Siemens NX(.prt), Rhino 3D(.3dm), Autodesk Inventor, Solid Edge

### 격자 데이터
CGNS(.cgns), PLOT3D(.p3d/.x/.q), Gmsh(.msh), Fluent(.msh/.cas),
VTK/VTU/VTP, Nastran, Abaqus, Medit, XDMF, OpenFOAM polyMesh,
NASA VGRID/FELISA/PATRAN, LAS/LAZ(포인트 클라우드)

## 출력 포맷

### CFD 솔버 — 주요
OpenFOAM(polyMesh), ANSYS Fluent(.cas/.msh), CGNS(.cgns),
Star-CCM+(.ccm), ANSYS CFX(.gtm), SU2(.su2), PLOT3D,
NASA FUN3D, OVERFLOW, CFL3D

### CFD 솔버 — 상용 추가
CFD++, Cobalt, SC/Tetra, CRUNCH, ADINA

### 지오메트리 재출력
IGES, STEP, STL, Parasolid(.x_t)

## 디렉터리 구조

```
auto-tessell/
├── CLAUDE.md
├── .claude/
│   ├── agents/                # Claude Code 서브에이전트 정의
│   └── commands/              # CLI 슬래시 커맨드 (/harness, /harness-init)
├── agents/specs/              # 에이전트 상세 스펙 (*.md)
├── cli/                       # CLI 진입점 (click + rich)
├── core/                      # 핵심 로직
│   ├── analyzer/              # 파일 로딩 + 지오메트리 분석
│   ├── preprocessor/          # L1→L2→L3 표면 전처리
│   ├── strategist/            # QualityLevel별 전략 수립
│   ├── generator/             # 볼륨 메쉬 생성 + 9-Tier fallback + PolyMeshWriter
│   │   ├── tier0_2d_meshpy.py       # Tier 0: 2D MeshPy
│   │   ├── tier_hex_classy_blocks.py # Tier Hex: classy_blocks
│   │   ├── tier_jigsaw_fallback.py   # Tier JIGSAW: 강건한 fallback
│   ├── evaluator/             # checkMesh + NativeMeshChecker + Hausdorff
│   ├── pipeline/              # Orchestrator (전체 파이프라인)
│   └── utils/                 # OpenFOAM 래퍼, 로깅, polyMesh 리더
├── desktop/                   # Windows 데스크톱 서버 (FastAPI + WebSocket)
├── godot/                     # Godot 4.3 GUI (3D 뷰어 + 메쉬 생성 UI)
├── auto_tessell_core/         # C++/pybind11 확장 (Tier 0, 추후)
├── tests/                     # pytest 1028+ 테스트 + 벤치마크 STL/STEP
├── backend/                   # Phase 2: FastAPI 백엔드 (기존 Web SaaS)
├── frontend/                  # Phase 2: Next.js 프론트엔드
└── infra/                     # 인프라 설정
```

## 개발 환경

Python 3.12+, C++23, OpenFOAM 2406, Node.js 24 (Phase 2)
핵심: trimesh, meshio, pyvista, pyacvd, pymeshfix, pymeshlab, click, rich, pydantic
볼륨: pytetwild, netgen-mesher, OpenFOAM(snappyHexMesh/cfMesh)
후처리: MMG3D, geogram(vorpalite)
CAD: cadquery, gmsh
데스크톱: FastAPI, Godot 4.3

## 컨벤션

- black + ruff + mypy strict
- 에이전트 통신: Pydantic 모델 (JSON Schema 검증)
- 에러: Tier 실패 시 work_dir 초기화 → 다음 Tier, 전체 중단 금지
- 로깅: structlog JSON
- CLI 파라미터 상세: `agents/specs/generator.md` 참조

## 현재 구현 상태 (1028+ tests, v0.3)

```bash
auto-tessell run input.stl -o ./case --quality draft     # ~1초, TetWild
auto-tessell run input.stl -o ./case --quality standard   # ~수분, Netgen/cfMesh
auto-tessell run input.stl -o ./case --quality fine        # ~30분+, snappyHexMesh
auto-tessell run input.step -o ./case --quality draft      # STEP CAD 지원
```

- ✅ 전체 파이프라인: Analyzer → Preprocessor → Strategist → Generator → Evaluator
- ✅ Generator↔Evaluator 재시도 루프 (최대 3회)
- ✅ **9-Tier Volume Mesh 자동 선택 (v0.3 완성)**:
  - Tier 0: 2D MeshPy (입구/출구 단면용)
  - Tier Hex: classy_blocks 기반 Hex 메시
  - Tier JIGSAW: 강건한 Tet fallback
  - Tier TetWild (Draft)
  - Tier Netgen (Standard)
  - Tier cfMesh (Standard Hex)
  - Tier snappyHexMesh (Fine)
  - Tier MMG3D (Fine)
  - Tier MeshAnything (AI fallback)
- ✅ PolyMeshWriter: tet/hex mesh → OpenFOAM polyMesh 직접 변환 (OpenFOAM 없이도 동작)
- ✅ OpenFOAM 자동 감지 (/usr/lib/openfoam/, /opt/, OPENFOAM_DIR)
- ✅ STEP/IGES CAD 파일 지원 (cadquery + gmsh fallback)
- ✅ Geometry Fidelity (Hausdorff 거리 기반 표면 충실도 검증)
- ✅ 불량 STL 수리 (L1 pymeshfix → L2 pyACVD+pymeshlab → L3 AI fallback)
- ✅ 회귀 테스트: 1028 테스트 (98.8% PASSED)
- ✅ E2E 검증: 8/20 성공 (Draft quality, 120s timeout)