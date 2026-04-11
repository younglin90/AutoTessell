# Auto-Tessell — 기술 명세서 (SPEC)

비상업 연구용 CFD 메쉬 자동 생성 도구.
오픈소스 라이브러리 전체 목록, 라이선스, 통합 방식 명세.

> 상세 로드맵: `agents/specs/open_source_roadmap.md`
> 에이전트별 명세: `agents/specs/*.md`
> 기준선/백로그: `CURRENT_STATUS_AND_BACKLOG.md`
> 오너십: `TRACK_OWNERSHIP.md`

---

## 소프트웨어 정보

| 항목 | 내용 |
|------|------|
| 이름 | Auto-Tessell |
| 버전 | 1.0.0 |
| 라이선스 | MIT (비상업 연구용) |
| 플랫폼 | Windows 10/11 (설치형), Linux (개발) |
| Python | 3.12+ |
| Primary Track | `core + cli` |
| GUI | Godot + desktop.server (현재), PySide6 + PyVistaQt (전환 경로) |

---

## 현재 사용 중인 오픈소스 라이브러리

### 핵심 CLI / 공통

| 라이브러리 | 버전 | 라이선스 | 용도 | 통합 방식 |
|-----------|------|---------|------|----------|
| click | ≥8.1 | BSD-3 | CLI 진입점 | import |
| rich | ≥13.0 | MIT | 터미널 출력/진행바 | import |
| pydantic | ≥2.0 | MIT | JSON Schema 검증, 에이전트 통신 | import |
| structlog | ≥24.0 | MIT | JSON 구조적 로깅 | import |
| numpy | ≥2.0 | BSD-3 | 수치 연산 | import |
| meshio | ≥5.3 | MIT | 메쉬 포맷 변환 (30+ 포맷) | import |

### 표면 메쉬 처리 (Preprocessor)

| 라이브러리 | 버전 | 라이선스 | 용도 | 통합 방식 |
|-----------|------|---------|------|----------|
| trimesh | ≥4.5 | MIT | 표면 메쉬 로딩·분석·watertight 검사 | import |
| pymeshfix | ≥0.16 | MIT | 표면 수리 L1 (구멍 채우기, 자기교차 제거) | import |
| pyACVD | ≥0.3 | MIT | 표면 리메쉬 L2 (Voronoi 기반 균일화) | import |
| pyvista | ≥0.44 | BSD-3 | 메쉬 시각화·분석, pyACVD 인터페이스 | import |
| pymeshlab | ≥2023.12 | GPL-3.0 | 표면 수리·리메쉬 L2 (200+ MeshLab 필터) | import |
| geogram (vorpalite) | 최신 | BSD-3 | 표면 리메쉬 L2 최우선, 특징 보존 고품질 | subprocess (CLI) |

### 볼륨 메쉬 생성 (Generator)

| 라이브러리 | 버전 | 라이선스 | 용도 | 통합 방식 |
|-----------|------|---------|------|----------|
| pytetwild | ≥0.2 | MPL-2.0 | Volume Tet Draft (TetWild) | import |
| netgen-mesher | ≥6.2 | LGPL-2.1 | Volume Tet Standard | import |
| OpenFOAM | 2406 | GPL-2.0+ | Volume Hex Fine (snappyHexMesh/cfMesh) | subprocess |
| MMG | 최신 | LGPL-3.0 | Volume Tet Fine (품질 최적화) | subprocess |

### CAD 지원

| 라이브러리 | 버전 | 라이선스 | 용도 | 통합 방식 |
|-----------|------|---------|------|----------|
| cadquery | ≥2.4 | LGPL-2.1 | STEP/IGES/BREP CAD 테셀레이션 | import |
| gmsh | 최신 | GPL-2.0+ | CAD 테셀레이션 fallback (OCC 내장) | import (API) |

### AI 메쉬 (선택)

| 라이브러리 | 버전 | 라이선스 | 용도 | 통합 방식 |
|-----------|------|---------|------|----------|
| MeshAnythingV2 | 최신 | S-Lab 1.0 ⚠️ | L3 AI 표면 수리 (비상업 연구 한정) | import |
| meshgpt-pytorch | ≥1.0 | MIT | AI 메쉬 생성 | import |
| torch | ≥2.0 | BSD-3 | PyTorch (AI 모델 공통) | import |

> ⚠️ MeshAnythingV2: 비상업 연구 목적 전용. 상업 사용 시 S-Lab 별도 허가 필요.

### 데스크톱 서버

| 라이브러리 | 버전 | 라이선스 | 용도 | 통합 방식 |
|-----------|------|---------|------|----------|
| fastapi | ≥0.100 | MIT | REST API 서버 | import |
| uvicorn | ≥0.20 | BSD-3 | ASGI 서버 | import |
| websockets | ≥12.0 | BSD-3 | 실시간 진행 상황 스트리밍 | import |
| python-multipart | ≥0.0.6 | Apache-2.0 | 파일 업로드 | import |

---

## 통합 예정 오픈소스 라이브러리

### v1.0 — CLI 완성 (pip, Windows 완전 지원)

| 라이브러리 | 라이선스 | 용도 | 파이프라인 위치 | 설치 |
|-----------|---------|------|--------------|------|
| **neatmesh** | MIT | OpenFOAM 없는 CFD 품질 검사 | Evaluator | `pip install neatmesh` |
| **mesh2sdf** | MIT | SDF 기반 watertight 변환 | Preprocessor L1 fallback | `pip install mesh2sdf` |
| **MeshPy** | MIT+AGPL | Triangle 2D + TetGen | Generator 2D / Draft | `pip install meshpy` |
| **classy_blocks** | MIT | blockMesh 구조적 Hex Python 생성 | Generator Fine | `pip install classy-blocks` |
| **foamlib** | MIT | OpenFOAM 파일 I/O 현대화 | Generator/Evaluator | `pip install foamlib` |
| **OpenFOAMCaseGenerator** | MIT | 완전한 케이스 자동 생성 | Generator 후처리 | `pip install openfoam-case-generator` |
| **fast-simplification** | MIT | 대용량 메쉬 데시메이션 | Preprocessor L2 전처리 | `pip install fast-simplification` |
| **JIGSAW-Python** | Custom OSS | 3D 비구조 메셔 추가 | Generator Draft fallback | conda-forge |
| **ofpp** | MIT | OpenFOAM polyMesh 파서 | Evaluator / 결과 검증 | `pip install ofpp` |
| **fogleman/sdf** | MIT | SDF CSG 벤치마크 형상 생성 | 테스트 유틸리티 | `pip install sdf` |

### v1.5 — 파이프라인 강화 (conda/subprocess)

| 라이브러리 | 라이선스 | 용도 | 파이프라인 위치 | 설치 |
|-----------|---------|------|--------------|------|
| **seagullmesh** | LGPL-3.0 | CGAL Alpha Wrap — 비매니폴드 watertight 변환 | Preprocessor L2 | conda-forge |
| **Open3D** | MIT | 포인트 클라우드→메쉬 (Poisson, alpha) | Preprocessor (스캔 입력) | `pip install open3d` |
| **libigl** | MPL-2.0 | Laplacian 스무딩, Boolean ops | Preprocessor/Generator | `pip install libigl` |
| **PyMetis** | MIT | METIS 메쉬 파티셔닝 | Generator 후처리 | conda-forge |
| **pygeogram** | BSD-3 | Geogram Python API (vorpalite 대체) | Preprocessor L2 | 소스 빌드 |
| **pyCGNS** | LGPL-2.0 | CGNS 포맷 완전 지원 | Analyzer/Generator | conda-forge |
| **SEACAS/exodus.py** | BSD-3 | Exodus II 포맷 I/O | Analyzer/Generator | `pip install seacas` |
| **SU2** | LGPL-2.1 | OpenFOAM 대안 CFD 솔버 | Evaluator (검증) | installer |
| **PyGeM** | MIT | RBF/FFD 메쉬 모핑 | Generator (형상 최적화) | `pip install pygem` |
| **Polyscope-py** | MIT | 실시간 3D 메쉬 시각화 | 개발/디버그 | `pip install polyscope` |

### v2.0 — Qt GUI 전환 + 고급 메셔

| 라이브러리 | 라이선스 | 용도 | 파이프라인 위치 | 설치 |
|-----------|---------|------|--------------|------|
| **PySide6** | LGPL-3.0 | Qt GUI 프레임워크 | GUI 메인 윈도우 | `pip install PySide6` |
| **PyVistaQt** | MIT | VTK 3D 뷰어 Qt 임베드 | GUI 3D 뷰어 | `pip install pyvistaqt` |
| **Nuitka** | Apache-2.0 | Python→C 컴파일 Windows EXE | 패키징 | `pip install nuitka` |
| **QuadWild** | GPL-3.0 | Quad 표면 리메쉬 → Hex 전처리 | Generator Fine | subprocess (빌드) |
| **InstantMesh** | Apache-2.0 | 이미지→watertight L3 AI | Preprocessor L3 | import (GPU) |
| **GMDS** | LGPL-2.1 | 산업용 Quad/Hex 메쉬 (CEA) | Generator Fine | conda-forge |
| **NeuralOperator** | MIT | FNO — 물리 필드 예측 surrogate | Evaluator 가속 | `pip install neuraloperator` |
| **xatlas-python** | MIT | UV 언랩 (AI 전처리) | Preprocessor L3 | `pip install xatlas` |
| **K3D-jupyter** | MIT | Jupyter 3D 메쉬 뷰어 | 개발/디버그 | `pip install k3d` |

### v3.0 — Web SaaS + 연구 특수 툴

| 라이브러리 | 라이선스 | 용도 |
|-----------|---------|------|
| pyHyp | Apache-2.0 | 쌍곡선 BL 압출 (항공 경계층) |
| enGrid | GPL-2.0 | 프리즈매틱 BL 메쉬 → OpenFOAM 직출력 |
| QuadriFlow | MIT | 고품질 Quad 리메쉬 |
| robust_hex_dominant_meshing | Research | Hex-dominant 볼륨 직접 변환 (SIGGRAPH 2017) |
| AlgoHex | AGPL-3.0 | Tet→Hex 자동 변환 학술 최신 구현 (ERC) |
| Mesquite | LGPL-2.1 | 노드 이동 기반 메쉬 품질 최적화 (Sandia) |
| pygalmesh | LGPL | CGAL Volume Tet (수학적 품질 보장) |
| Wildmeshing Toolkit | MIT | 메쉬 최적화 레이어 |
| Cassiopee (ONERA) | GPL-3.0 | CGNS 기반 CFD 전/후처리 |
| FlexiCubes | Apache-2.0 | 미분가능 등값면 추출 (NVIDIA) |
| DMesh++ | Research | 미분가능 메쉬 최적화 (NeurIPS 2024) |
| PINA | MIT | PINN + Neural Operator 통합 (SISSA) |
| GNS/MeshNet | MIT | DeepMind MeshGraphNets PyTorch 구현 |
| Foam-Agent | MIT | LLM 기반 경계조건 자동 추론 (NeurIPS 2025) |
| pyvoro | BSD | Voronoi 폴리헤드럴 메쉬 |
| MicroStructPy | MIT | Voronoi power diagram 폴리헤드럴 메쉬 |
| FBPINNs | MIT | 도메인 분해 PINN (JAX) |
| MetaOpenFOAM | GPL-3.0 | LLM 경계조건 추론 참고 |
| toughio | BSD-3 | meshio 기반 CFD 포맷 변환 확장 |

---

## GUI 명세

### 현재
- **Godot**: 3D 뷰어 + 메쉬 생성 UI
- **FastAPI + WebSocket**: GUI ↔ 파이프라인 통신

### 전환 계획 (Phase 2)

| 컴포넌트 | 라이브러리 | 라이선스 | 역할 |
|---------|-----------|---------|------|
| 메인 윈도우 | PySide6 (Qt 6.7) | LGPL-3.0 | 앱 프레임워크 |
| 3D 뷰어 | PyVistaQt | MIT | VTK 기반 메쉬 렌더링 |
| 렌더 백엔드 | VTK | BSD | 3D 렌더 파이프라인 |
| 파이프라인 서버 | FastAPI + WebSocket | MIT/BSD | 비동기 진행 상황 |

---

## 라이선스 호환성 매트릭스

| 라이선스 | 직접 import | subprocess 격리 | 재배포 조건 |
|---------|-----------|----------------|------------|
| MIT / BSD / Apache | ✅ | ✅ | 저작권 고지 유지 |
| MPL-2.0 | ✅ | ✅ | 수정 파일 동일 라이선스 |
| LGPL-2.1 / LGPL-3.0 | ✅ (동적 링크) | ✅ | 라이브러리 소스 제공 |
| GPL-2.0 / GPL-3.0 | ⚠️ subprocess 권장 | ✅ | 재배포 시 전체 GPL |
| S-Lab 1.0 (MeshAnythingV2) | ✅ | ✅ | **비상업 연구 전용** |
| Custom OSS (JIGSAW 등) | ✅ 연구 목적 | ✅ | 비상업 연구 무료 |

---

## 입출력 포맷

### 입력 포맷 — CAD 표준 중립

| 포맷 | 확장자 | 라이브러리 | 상태 |
|------|--------|-----------|------|
| STL | .stl | trimesh | ✅ |
| STEP | .stp, .step | cadquery / gmsh | ✅ |
| IGES | .igs, .iges | cadquery / gmsh | ✅ |
| VDA-FS | .vda | pythonocc-core | 예정 |
| OBJ/PLY/OFF/3MF | | trimesh | ✅ |
| BREP | .brep | cadquery | ✅ |
| Parasolid | .x_t, .x_b | pythonocc-core | 예정 |
| ACIS | .sat, .sab | pythonocc-core | 예정 |

### 입력 포맷 — 네이티브 CAD (상용)

| 포맷 | 확장자 | 라이브러리 | 비고 |
|------|--------|-----------|------|
| CATIA V4/V5/V6 | .model, .CATPart, .CATProduct | pythonocc-core / IfcOpenShell | 라이선스 필요할 수 있음 |
| SolidWorks | .sldprt, .sldasm | pythonocc-core | |
| PTC Creo/Pro·E | .prt, .asm | pythonocc-core | |
| Siemens NX | .prt | pythonocc-core | |
| Rhino 3D | .3dm | rhino3dm (MIT) | |
| Autodesk Inventor | .ipt, .iam | IfcOpenShell / OCC | |
| Solid Edge | .par, .asm | pythonocc-core | |

### 입력 포맷 — 격자 데이터

| 포맷 | 확장자 | 라이브러리 | 상태 |
|------|--------|-----------|------|
| CGNS | .cgns | pyCGNS / meshio | ✅ |
| PLOT3D | .p3d, .x, .q | meshio | 예정 |
| Gmsh | .msh | meshio | ✅ |
| Fluent | .msh, .cas | meshio | ✅ |
| VTK/VTU/VTP | | pyvista / meshio | ✅ |
| Nastran/Abaqus | | meshio | ✅ |
| XDMF/Medit | | meshio | ✅ |
| OpenFOAM polyMesh | | 내장 파서 | ✅ |
| NASA VGRID/FELISA | | meshio (부분) | 예정 |
| PATRAN | .pat | meshio | 예정 |
| LAS/LAZ | | laspy | ✅ |
| E57 (LiDAR) | .e57 | pye57 | 예정 |

### 출력 포맷 — CFD 솔버

| 솔버 | 포맷 | 라이브러리 | 상태 |
|------|------|-----------|------|
| OpenFOAM | polyMesh 디렉터리 | PolyMeshWriter (내장) | ✅ |
| ANSYS Fluent | .cas, .msh | meshio | ✅ |
| CGNS | .cgns | pyCGNS / meshio | ✅ |
| Star-CCM+ | .ccm | meshio (부분) | 예정 |
| ANSYS CFX | .gtm | meshio | 예정 |
| SU2 | .su2 | meshio | ✅ |
| PLOT3D | .p3d, .x | meshio | 예정 |
| NASA FUN3D | | meshio | 예정 |
| OVERFLOW | | meshio | 예정 |
| CFL3D | | meshio | 예정 |
| CFD++/Cobalt/SC/Tetra/CRUNCH/ADINA | | meshio (부분) | 예정 |

### 출력 포맷 — 지오메트리 재출력

| 포맷 | 라이브러리 |
|------|-----------|
| IGES | cadquery / pythonocc |
| STEP | cadquery / pythonocc |
| STL | trimesh |
| Parasolid (.x_t) | pythonocc-core |

### 지원 볼륨 메쉬 타입

| 타입 | 설명 | 주요 엔진 | 출력 포맷 |
|------|------|---------|---------|
| 정렬격자 (Structured) | 블록 기반 정렬 격자 | ICEM-CFD style, gridgen | CGNS, PLOT3D |
| 비정렬 Tetrahedral | 복잡 형상 범용 | TetWild, Netgen, TetGen(MeshPy), MMG3D, JIGSAW | OpenFOAM, Fluent, SU2, CGNS |
| Hex-dominant | 경계층·정확도 우수 | snappyHexMesh, cfMesh, classy_blocks | OpenFOAM polyMesh, CGNS |
| Polygonal/Polyhedral | 셀 수 최소, 수렴성 우수 | OpenFOAM polyDualMesh, geogram | OpenFOAM polyMesh |

**선택 기준**: 형상 복잡도·품질 레벨·솔버 요구사항에 따라 Generator가 자동 선택.
- Draft → Tetrahedral (속도 우선)
- Standard → Tet 또는 Hex-dominant (정확도 균형)
- Fine → Hex-dominant 또는 Polyhedral (최고 품질)

### 엔진 선택 로직 (코드 1:1)

- 구현 위치:
`core/strategist/tier_selector.py`, `core/strategist/strategy_planner.py`, `core/generator/pipeline.py`
- 우선순위:
`tier_hint` 강제 > `surface_quality_level=l3_ai` 강제 > 품질/형상 기반 자동 선택
- 자동 선택 규칙:
`draft -> tier2_tetwild`
`standard -> cad_brep:tier05_netgen | external+watertight:tier1_snappy | internal+watertight:tier15_cfmesh | watertight+simple:tier0_core | else:tier2_tetwild`
`fine -> cad_brep:tier05_netgen | external+watertight:tier1_snappy | watertight:tier15_cfmesh | else:tier2_tetwild`
- 자동 선택 결과 기록:
`mesh_strategy.json -> tier_specific_params.engine_selection`
로그 이벤트: `tier_auto_selected`, `strategy_planned(selection_source/selection_reason)`
- fine auto 실행 순서:
`label=64`: `classy_blocks -> cfmesh -> snappy -> netgen -> tetwild`
`label=32`: `classy_blocks -> cfmesh -> netgen -> tetwild -> snappy` (snappy 뒤로 이동)

---

## 품질 레벨 명세

| 레벨 | 표면 처리 | 볼륨 엔진 | 예상 시간 |
|------|---------|---------|---------|
| **Draft** | L1 (pymeshfix) | TetWild → JIGSAW | ~1초 |
| **Standard** | L1-L2 (pyACVD/pymeshlab) | Netgen → pygalmesh → TetGen | ~수분 |
| **Fine** | L1-L2 (geogram) | snappyHexMesh / cfMesh / MMG | ~30분+ |

### max-cells 정책

- 단일 정책 소스: `core/max_cells_policy.py`
- cap은 `quality` + OpenFOAM label(Int32/Int64) 조합으로 결정한다.
- 적용 지점:
`cli/main.py`(입력 clamp), `core/strategist/param_optimizer.py`(초기 도메인 크기), `core/pipeline/orchestrator.py`(재시도 시 재적용)
- 목표: 품질별 drift 방지 + Int32 오버플로 보호

### 런타임 의존성 탐지

- 명령: `auto-tessell doctor`
- 상태 분류: `required/optional`, `installed/missing`, fallback, 사용자 액션(설치 가이드)
- 탐지 기준: import 가능 여부 + binary `which(...)` + OpenFOAM label 감지

---

## 테스트 요구사항

- pytest ≥8.3
- 단위 테스트: 각 에이전트 모듈별
- 통합 테스트: 전체 파이프라인 end-to-end
- 벤치마크: `tests/` 디렉터리 내 STL/STEP 샘플
- 현재 테스트 스위트 운영 (단위/통합 포함)
- 신규 툴 통합 시 해당 모듈 테스트 추가 필수

### 최근 개선 사항 (2026-04)

#### 1) Matrix QA 실행 정책 고도화

- 구현 위치: `scripts/run_mesh_matrix.py`
- `runtime-profile` 추가/강화:
`balanced` / `fast` 프로파일로 실행 전략 분리.
- `fast` 프로파일 정책:
quality/tier별 timeout floor 적용, fine 조합에서 과도한 거친화 방지,
tier별 실행 파라미터 보정.
- 조합별 실행 가시성 개선:
각 조합 시작 시 `quality/tier/remesh/timeout/max_iter` 즉시 출력.

#### 2) 재시도/시간 예산 외부화

- matrix 실행에서 조합별 재시도 횟수 제어 지원:
`--max-iter-by-quality QUALITY=N`, `--max-iter-by-tier TIER=N`
- 기본 프로파일 로직과 override를 함께 적용해 운영자가 코드 수정 없이
실험 조건을 조절할 수 있도록 함.

#### 3) 실패 원인 분류 정확도 개선

- 최종 실패 문구 우선 추출:
`Failed after N iterations`, `All mesh generation tiers failed`를
중간 `FOAM FATAL` 로그보다 우선 해석.
- failure category 정합성 개선:
`openfoam_failure` 오분류를 줄이고 `iteration_exhausted`,
`all_tiers_failed`, `timeout` 중심으로 분류.

#### 4) CLI/Orchestrator 실행 일관성 보강

- `run` 명령에 `--strict-tier` 옵션 추가:
명시 tier(auto 아님)에서 fallback tier 비활성화 가능.
- 오케스트레이터에 `strict_tier` 옵션 반영:
전략 수립/재수립 시 fallback 체인 일관 제어.
- CLI 파라미터 전달 버그 수정:
`tier_specific_params`가 실제 `orchestrator.run(...)`에 전달되도록 수정
(`tetwild_epsilon`, `tetwild_stop_energy` 등 runtime override 정상 반영).

#### 5) 운영 커맨드 정리

- Make target 추가:
`qa-matrix-mini-fast`, `qa-matrix-fine-fast`
- `qa-matrix-fine-fast`는 fine 운영 진단을 위해 tier별 재시도 override
(`auto=2`, `netgen=2`, `tetwild=3`)를 기본 포함.

#### 6) 회귀 테스트 보강

- `tests/test_run_mesh_matrix.py`:
프로파일 파라미터, timeout floor, max-iteration override, 에러 추출 로직 검증.
- `tests/test_cli.py`:
CLI tier-specific 파라미터가 orchestrator로 전달되는 회귀 테스트 추가.
