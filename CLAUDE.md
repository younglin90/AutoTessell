# Auto-Tessell — CLAUDE.md

CAD/메쉬 파일 → OpenFOAM polyMesh 자동 생성 도구.
**핵심 철학**: 외부 라이브러리에 의존하지 않고 우리 코드로 직접 제작·지속 고도화.
외부 라이브러리 (TetWild, WildMesh, snappyHexMesh, cfMesh, pymeshfix, pyACVD 등) 는 **참고용**
으로만 사용하며, 핵심 알고리즘을 `core/` 내부로 카피·이식·고도화해 최종적으로 외부 의존 없이
동작하는 것을 목표로 한다.

## 개발 단계

**Phase 1 (현재): CLI + Qt GUI** — 리눅스/Windows 직접 실행·테스트
**Phase 2: Web SaaS** — CLI 완성 후 FastAPI + Next.js 래핑

```bash
auto-tessell input.stl -o ./case --mesh-type hex_dominant --quality standard
auto-tessell input.step -o ./case --mesh-type tet --quality fine --tier wildmesh --verbose
```

## 5-Agent 하네스 아키텍처

```
Analyzer → Preprocessor → Strategist → Generator → Evaluator
                                                        │
                                                   FAIL │ → 사용자에게 "재시도 할까요?" 질문 (y/N)
                                                        │
                                                   PASS │ → 종료
```

**변경 사항** : Generator ⇄ Evaluator 자동 재시도 루프 **제거**. FAIL 시 Evaluator 가
recommendation 을 출력하고 사용자가 재시도 여부를 결정. Generator 내부 fallback (같은 mesh_type
다른 Tier) 은 유지.

에이전트 간 통신은 JSON 파일 기반. 상세 스펙은 `agents/specs/*.md` 참조.

| 에이전트 | 상세 스펙 | 핵심 역할 |
|---------|----------|----------|
| Analyzer | `agents/specs/analyzer.md` | 입력 파일 로딩 + 자체 분석, geometry_report.json |
| Preprocessor | `agents/specs/preprocessor.md` | 자체 repair/remesh L1→L2→L3 |
| Strategist | `agents/specs/strategist.md` | mesh_type × QualityLevel → Tier + 파라미터 |
| Generator | `agents/specs/generator.md` | 볼륨 메쉬 생성 (자체 엔진 우선 + Tier fallback) |
| Evaluator | `agents/specs/evaluator.md` | NativeMeshChecker(자체) + PASS/FAIL, 사용자 확인 |

## 2-Phase Progressive 파이프라인

### Phase 1: 표면 메쉬 (Surface Mesh)

저품질 → 고품질 순서로 점진적 개선. 각 단계는 gate 통과 시에만 다음 단계로 이행.
**모든 단계 자체 구현 목표** (외부 라이브러리는 참고용, 점진적 제거).

| 레벨 | 자체 구현 상태 | 참고 라이브러리 | 조건 |
|------|----------------|-----------------|------|
| L1 (Repair) | 🔧 진행 (native topology repair) | pymeshfix + trimesh | 기본 수리 |
| L2 (Remesh) | 🔧 진행 (isotropic / CVT / RVD) | pyACVD + geogram + pymeshlab | edge_length_ratio > 100 또는 > 200k 면 |
| L3 (AI fix) | — (외부 의존 유지) | MeshGPT / MeshAnything (GPU) | L2 실패 시 최후 수단 |

Gate: watertight + manifold 통과 시 Volume Phase 진입.

### Phase 2: 볼륨 메쉬 (Volume Mesh) — 3-카테고리 사용자 선택

사용자가 **mesh_type** 을 선택: `tet` / `hex_dominant` / `poly`.
각 타입 × QualityLevel 조합으로 Tier 자동 매핑.

| 메쉬 타입 | 특징 | 참고 라이브러리 (카피 대상) | 자체 구현 모듈 |
|-----------|------|-----------------------------|----------------|
| **tet** | 복잡 형상 강건, isotropic | TetWild, fTetWild (WildMesh), Netgen | `core/generator/native_tet/` |
| **hex_dominant** | BL 품질 우수, 셀 수 효율 | snappyHexMesh, cfMesh, classy_blocks | `core/generator/native_hex/` |
| **poly** | 셀 수 최소, gradient 해소 | OpenFOAM polyDualMesh, geogram Voronoi | `core/generator/native_poly/` |

### mesh_type × QualityLevel → Tier 매핑

| 메쉬 타입 | draft | standard | fine |
|-----------|-------|----------|------|
| tet | tetwild (coarse ε) | netgen 또는 wildmesh | wildmesh (tight ε) |
| hex_dominant | cfmesh (fast) | cfmesh | snappyHexMesh (+BL) |
| poly | voro_poly | polydual | polydual + 품질 개선 |

### Tier 4 (Layers Post) — Boundary Layer

주 볼륨 엔진 이후 BL 추가. **메쉬 타입별 다른 기법**:

- **tet**: 전체 tet 유지 (prism → tet 3 분할)
- **hex_dominant**: 전통적 prism 층 (shrink+extrude+snap+merge+stitch)
- **poly**: prism 층 + polyhedral 전환 or anisotropic poly 셀

참고: cfMesh `generateBoundaryLayers`, OpenFOAM `refineWallLayer`, snappy `addLayers`,
netgen_bl, gmsh_bl, MeshKit, SU2 HexPress, Salome SMESH — 핵심 로직을 `core/layers/native_bl.py`
로 점진적 이식.

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

**현재 의존 (점진적 제거 대상)** :
- 표면 처리: trimesh, meshio, pyvista, pyacvd, pymeshfix, pymeshlab
- 볼륨: pytetwild, netgen-mesher, OpenFOAM (snappyHexMesh/cfMesh), pyvoro-mm, rtree
- 후처리: MMG3D, geogram (vorpalite)
- CAD: cadquery, gmsh

**유지 의존** :
- 수치/알고리즘: numpy, scipy
- UI: PySide6, PyVistaQt, matplotlib
- CLI/테스트: click, rich, pydantic, pytest, structlog
- AI fallback (L3): torch, meshgpt-pytorch, MeshAnythingV2

## 컨벤션

- black + ruff + mypy strict
- 에이전트 통신: Pydantic 모델 (JSON Schema 검증)
- 에러: Tier 실패 시 work_dir 초기화 → 다음 Tier, 전체 중단 금지
- Generator ⇄ Evaluator 자동 재시도 루프 **없음**. FAIL 시 사용자 확인 (`y/N`).
- 로깅: structlog JSON
- 외부 라이브러리 신규 추가는 **반드시 "참고 → 자체 구현 계획"** 과 함께
- CLI 파라미터 상세: `agents/specs/generator.md` 참조

## 현재 구현 상태 (1328 tests, v0.4.0-beta "Native-First")

```bash
auto-tessell run input.stl -o ./case --mesh-type tet --quality draft
auto-tessell run input.stl -o ./case --mesh-type hex_dominant --quality fine    # + BL
auto-tessell run input.stl -o ./case --mesh-type poly --quality standard
auto-tessell run input.stl -o ./case --tier native_hex --auto-retry off         # 자체 엔진 강제
```

- ✅ 전체 파이프라인: Analyzer → Preprocessor → Strategist → Generator → Evaluator
- ✅ Generator↔Evaluator **자동** 재시도 루프 제거 완료 (`--auto-retry off` 기본). FAIL 시 `y/N` prompt.
- ✅ **mesh_type 3 카테고리** (tet / hex_dominant / poly) 사용자 선택 (CLI + Qt GUI)

### 자체 구현 (v0.4 Native-First)

- ✅ **자체 파일 reader** (`core/analyzer/readers/`): STL binary+ASCII, OBJ, PLY, OFF — trimesh 와 parity 검증
- ✅ **자체 topology** (`core/analyzer/topology.py`): watertight / manifold / genus / dihedral / sharp edges
- ✅ **자체 L1 repair** (`core/preprocessor/native_repair/`): dedup / degenerate / non-manifold / hole / winding
- ✅ **자체 L2 remesh** (`core/preprocessor/native_remesh/`): isotropic (Botsch 2004), Lloyd CVT
- ✅ **자체 BL 생성** (`core/layers/native_bl.py`): Phase 2 완성 — polyMesh 위상 직접 재구성, OpenFOAM checkMesh pass
- ✅ **tet 전용 BL** (`core/layers/tet_bl_subdivide.py`): prism wedge → 3 tet 분할, 순수 tet 메쉬 유지
- ✅ **NativeMeshChecker 기본화**: `--checker-engine auto` 기본이 native. OpenFOAM parity 테스트 통과
- ✅ **native_tet MVP** (`core/generator/native_tet/`): scipy Delaunay + envelope, sphere 0.6s
- ✅ **native_hex MVP** (`core/generator/native_hex/`): uniform grid + inside filter, checkMesh OK
- ✅ **native_poly MVP** (`core/generator/native_poly/`): scipy Voronoi + ridge polygon
- ✅ **17-Tier Volume Mesh 전부 동작 (v0.3.4)**:
  - ✅ tier2_tetwild (TetWild, Draft)
  - ✅ tier05_netgen (Netgen, Standard)
  - ✅ tier1_snappy (snappyHexMesh, Fine)
  - ✅ tier15_cfmesh (cfMesh, Standard Hex)
  - ✅ tier_cinolib_hex (cinolib Hex)
  - ✅ tier_voro_poly (Voronoi Polyhedral, pyvoro-mm)
  - ✅ tier_mmg3d (MMG3D TetGen+Optimize)
  - ✅ tier_robust_hex (Feature-Preserving Octree All-Hex, OVM parser)
  - ✅ tier_algohex (AlgoHex Frame Field Tet→Hex, OVM ASCII parser 수정)  ← v0.3.4
  - ✅ tier_meshpy (TetGen)
  - ✅ tier_wildmesh (WildMesh)
  - ✅ tier_gmsh_hex (GMSH Hex)
  - ✅ tier_hex_classy_blocks (blockMesh + snappy fallback)
  - ✅ tier0_core (Geogram CDT)
  - ✅ tier_hohqmesh (HOHQMesh, ISM 가변길이 파서 수정)  ← v0.3.4
  - ✅ tier_jigsaw (jigsawpy ctypes API, libjigsaw.so)  ← v0.3.4
  - ✅ tier_jigsaw_fallback (jigsawpy ctypes API)  ← v0.3.4
- ✅ Qt GUI (PySide6 + PyVistaQt): 드래그앤드롭, 19개 엔진 선택, 실시간 메쉬 뷰어
  - 뷰포트 품질 색상화 드롭다운 (Aspect / Skewness / Non-ortho)
  - Quality 탭 인터랙티브 matplotlib 히스토그램 (메시 로드 즉시 자동 갱신)
  - Export·프로젝트 저장·WYSIWYG 스크린샷, 로그 필터·검색, Tier 노드 파라미터 팝업
  - Stop 시 서브프로세스 안전 정리 (requestInterruption) + UI 상태 복원
- ✅ PolyMeshWriter: tet/hex mesh → OpenFOAM polyMesh 직접 변환
- ✅ OpenFOAM 자동 감지 (/usr/lib/openfoam/, /opt/, OPENFOAM_DIR)
- ✅ STEP/IGES CAD 파일 지원 (cadquery + gmsh fallback)
- ✅ Geometry Fidelity (Hausdorff 거리 기반 표면 충실도 검증)
- ✅ 불량 STL 수리 (L1 pymeshfix → L2 pyACVD+pymeshlab → L3 AI fallback)
- ✅ 회귀 테스트: **1328 passed, 19 skipped** (v0.3.5 1108 → +220 신규, 0 failed)
- ✅ E2E 검증: 88% 달성 (Phase D-E 기준)
- ✅ **Windows 클릭 설치 인스톨러** (NSIS .exe, v0.3.5): `installer/dist/AutoTessell-0.3.5-Setup.exe`
  - Miniconda3 자동 다운로드/설치, pip으로 전체 라이브러리 설치
  - conda create -n autotessell python=3.12 pip → pip 5단계 분할 설치
  - ESI OpenFOAM for Windows 지원 (MSYS2 bash 경유)
  - mmg3d.exe / HOHQMesh.exe / libjigsaw.dll 자동 다운로드
  - NSIS Modern UI 2: Welcome → License → Directory → Install → Finish 마법사
- ✅ **WildMesh x축 비대칭 버그 수정**: `geometry_analyzer._estimate_flow()` — 단일 폐곡면(genus=0) 기본값 `external` → `internal` 변경
  - 외부: 풍동 도메인 생성 (9×5×5 비대칭), 내부: bbox 기반 [-0.6,0.6]³ 대칭 도메인
- ✅ **OpenFOAM Windows 지원**: `core/utils/openfoam_utils.py` — ESI OpenFOAM MSYS2 bash + WSL2 fallback
- ✅ **Tier 바이너리 Windows 경로 지원**: mmg3d, HOHQMesh, AlgoHex, RobustHex — .exe 확장자 + Windows 설치 경로 자동 탐색

### Tier 동작 현황 요약 (sphere STL 기준)

| 엔진 | 상태 | 시간 |
|------|------|------|
| tetwild | ✅ | ~0.7s |
| netgen | ✅ | ~0.8s |
| snappy | ✅ | ~1.1s |
| cfmesh | ✅ | ~5.4s |
| voro_poly | ✅ | ~0.06s |
| cinolib_hex | ✅ | ~1.4s |
| meshpy | ✅ | ~0.3s (수정됨) |
| wildmesh | ✅ | ~0.2s (수정됨) |
| gmsh_hex | ✅ | ~0.5s (수정됨) |
| hex_classy | ✅ | ~1.1s (수정됨) |
| mmg3d | ✅ | ~5s |
| robust_hex | ✅ | ~240s n=3 (all-hex) |
| algohex | ✅ | ~58s tet_size=0.3 (frame-field hex, OVM parser) |
| core | ✅ | ~0.2s |
| jigsaw | ✅ | ~0.6s (ctypes API) |
| jigsaw_fallback | ✅ | ~0.0s (ctypes API) |
| hohqmesh | ✅ | ~1.9s (ISM 가변길이 파서) |
| **native_tet** | ✅ | ~0.6s (scipy Delaunay MVP, v0.4) |
| **native_hex** | ✅ | ~0.1s (uniform grid, checkMesh OK, v0.4) |
| **native_poly** | ✅ | ~0.3s (scipy Voronoi MVP, v0.4) |

> 상세: `agents/specs/open_source_roadmap.md` → "설치 현황" 섹션
> v0.4 "Native-First" 변경 이력: `CHANGELOG.md`
## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
