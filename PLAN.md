# Auto-Tessell — 개발 계획서 (PLAN)

CAD/메쉬 → OpenFOAM polyMesh 자동 생성 Windows 데스크톱 도구.
비상업 연구용 (MIT 라이선스). AI + 오픈소스 메쉬 툴 통합.

---

## 목표

- 연구자/엔지니어가 Windows에서 STL/STEP 파일을 드래그앤드롭하면
  자동으로 CFD 품질 메쉬(OpenFOAM polyMesh)를 얻을 수 있는 설치형 GUI 도구
- 사용자 개입 최소화: 품질 레벨(draft/standard/fine)만 선택
- 오픈소스 메쉬 툴 총동원, AI 보조 자동 수리

---

## 버전 로드맵 전체

```
v0.1 (현재)
  │
  ├─ v0.2  Evaluator 강화
  ├─ v0.3  Generator 확장
  ├─ v0.4  케이스 자동화
  ├─ v0.5  전처리 강화
  │
v1.0  CLI 안정 릴리스
  │
  ├─ v1.1  비매니폴드 수리 강화
  ├─ v1.2  포인트 클라우드 입력
  ├─ v1.3  포맷 확장 (CGNS/Exodus)
  ├─ v1.4  메쉬 조작 강화
  ├─ v1.5  파티셔닝·솔버·시각화
  │
v2.0  Qt GUI (Godot 제거)
  │
  ├─ v2.1  Quad/Hex 메쉬 경로
  ├─ v2.2  AI 메쉬 강화
  ├─ v2.3  Windows 패키징 완성
  │
v3.0  Web SaaS
  │
  ├─ v3.1  경계층(BL) 메쉬
  ├─ v3.2  AI surrogate CFD
  └─ v3.3  연구 특수 툴
```

---

## v0.1 — 현재 ✅ 완료

**상태**: 배포 중

- 5-Agent 파이프라인: Analyzer → Preprocessor → Strategist → Generator ↔ Evaluator
- 2-Phase Progressive: 표면(L1→L2→L3) + 볼륨(Draft→Standard→Fine)
- PolyMeshWriter: OpenFOAM 없이 polyMesh 직접 생성
- STEP/IGES CAD 지원 (cadquery + gmsh fallback)
- 불량 STL 수리: pymeshfix → pyACVD + pymeshlab → MeshAnythingV2(AI)
- Hausdorff 거리 기반 표면 충실도 검증
- 458+ 테스트 통과 / MIT 라이선스

**현재 의존성**: trimesh, pymeshfix, pyACVD, pyvista, pymeshlab, geogram, pytetwild, netgen-mesher, OpenFOAM, MMG, cadquery, gmsh, meshio, MeshAnythingV2, meshgpt-pytorch, torch, fastapi, uvicorn, websockets

---

## v0.2 — Evaluator 강화

**목표**: OpenFOAM 없는 환경에서도 품질 검사 완전 동작

| 추가 툴 | 라이선스 | 설치 | 역할 |
|--------|---------|------|------|
| **neatmesh** | MIT | `pip install neatmesh` | OpenFOAM 없이 비직교성·skewness 계산 |
| **ofpp** | MIT | `pip install ofpp` | polyMesh binary/ASCII 파서, NumPy 직출력 |

**달성 기준**:
- `checkMesh` 없이 Evaluator가 PASS/FAIL 판정 가능
- polyMesh 결과를 Python에서 직접 검증

---

## v0.3 — Generator 확장

**목표**: 2D 메쉬 + 구조적 Hex 경로 신설, Draft fallback 강화

| 추가 툴 | 라이선스 | 설치 | 역할 |
|--------|---------|------|------|
| **MeshPy** | MIT+AGPL | `pip install meshpy` | Triangle 2D Delaunay + TetGen (Windows wheel) |
| **classy_blocks** | MIT | `pip install classy-blocks` | blockMeshDict Python 생성 → 구조적 Hex |
| **JIGSAW-Python** | Custom OSS | conda-forge | 추가 3D 비구조 메셔, TetWild fallback |

**달성 기준**:
- 2D 단면/입구 메쉬 생성 가능
- blockMesh 기반 구조적 Hex 메쉬 경로 동작
- Draft 품질에서 TetWild 실패 시 JIGSAW로 자동 전환

---

## v0.4 — 케이스 자동화

**목표**: 메쉬 생성 후 OpenFOAM 실행 가능한 케이스까지 원스톱 자동 생성

| 추가 툴 | 라이선스 | 설치 | 역할 |
|--------|---------|------|------|
| **foamlib** | MIT | `pip install foamlib` | OpenFOAM 파일 타입힌트 I/O, async 케이스 실행 |
| **OpenFOAMCaseGenerator** | MIT | `pip install openfoam-case-generator` | 0/, constant/, system/ 완전 자동 생성 |

**달성 기준**:
- `auto-tessell run model.stl -o ./case` 한 명령으로 실행 가능한 OF 케이스 생성
- BC 자동 설정 (벽면/입구/출구 자동 분류)
- simpleFoam, pimpleFoam 지원

---

## v0.5 — 전처리 강화

**목표**: 대용량 STL 성능 개선, SDF 기반 watertight 복구, 테스트 형상 생성

| 추가 툴 | 라이선스 | 설치 | 역할 |
|--------|---------|------|------|
| **mesh2sdf** | MIT | `pip install mesh2sdf` | 비watertight → SDF → 보장된 watertight 변환 |
| **fast-simplification** | MIT | `pip install fast-simplification` | 200k+ 면 대용량 STL 데시메이션 (VTK 대비 4-5×) |
| **fogleman/sdf** | MIT | `pip install sdf` | CSG 기반 벤치마크 형상 생성 (덕트, 채널 등) |

**달성 기준**:
- pymeshfix 실패 시 mesh2sdf로 자동 복구
- 100만 면 STL 처리 시간 50% 단축
- 테스트용 형상 5종 자동 생성

---

## v1.0 — CLI 안정 릴리스

**목표**: v0.2~v0.5 통합 완료, 전체 파이프라인 안정화, 공개 릴리스

- v0.2~v0.5 모든 툴 통합 완료
- 테스트 600+ 통과 목표
- `pyproject.toml` optional extras 정리 (`pip install auto-tessell[full]`)
- Windows 설치 문서 완성
- CHANGELOG, 사용자 가이드 작성

**완성된 파이프라인**:
```
입력 (STL/STEP/OBJ/PLY)
    │
[Analyzer]
    │
[Preprocessor]
    L1: pymeshfix → mesh2sdf(fallback)
    L2: geogram → pyACVD → pymeshlab
    L3: MeshAnythingV2 (AI)
    │
[Strategist]
    │
[Generator]
    Draft:    TetWild → JIGSAW(fallback)
    Standard: Netgen → MeshPy/TetGen(fallback)
    Fine:     snappyHexMesh → MMG → classy_blocks
    │
[Evaluator]
    neatmesh + ofpp (OF 없이) / checkMesh (OF 있을 때)
    │
polyMesh 출력 + foamlib BC 설정 + 케이스 자동 생성
```

---

## v1.1 — 비매니폴드 수리 강화

**목표**: 현재 L2 수리 실패 케이스 처리 능력 대폭 향상

| 추가 툴 | 라이선스 | 설치 | 역할 |
|--------|---------|------|------|
| **seagullmesh** | LGPL-3.0 | conda-forge | CGAL Alpha Wrap — 비매니폴드 soup → watertight |
| **libigl** | MPL-2.0 | `pip install libigl` | Laplacian 스무딩, Boolean ops |

**달성 기준**:
- 자기교차·열린 경계 등 극심한 불량 메쉬 watertight 변환 성공률 90%+
- L2 수리 실패율 현재 대비 50% 감소

---

## v1.2 — 포인트 클라우드 입력

**목표**: 스캔 데이터(LiDAR, 포토그래메트리) 직접 입력 지원

| 추가 툴 | 라이선스 | 설치 | 역할 |
|--------|---------|------|------|
| **Open3D** | MIT | `pip install open3d` | Poisson/Alpha Shape 표면 재구성 |
| **PDAL** | BSD-3 | `pip install pdal` | LAS/LAZ/E57 LiDAR 포맷 읽기 |

**달성 기준**:
- `.las`, `.e57`, `.ply` 포인트 클라우드 직접 입력 → polyMesh 생성
- Poisson 재구성 표면에서 볼륨 메쉬까지 end-to-end 동작

---

## v1.3 — 포맷 확장 (CGNS/Exodus)

**목표**: 항공우주·FEA 업계 표준 포맷 완전 지원

| 추가 툴 | 라이선스 | 설치 | 역할 |
|--------|---------|------|------|
| **pyCGNS** | LGPL-2.0 | conda-forge | CGNS/HDF5 항공우주 표준 포맷 |
| **SEACAS/exodus.py** | BSD-3 | `pip install seacas` | Exodus II (Abaqus/Sierra/Cubit) |

**달성 기준**:
- CGNS 메쉬 입력 → polyMesh 출력
- Exodus II 메쉬 입력 → polyMesh 출력
- meshio로 커버 안 되는 포맷 갭 해소

---

## v1.4 — 메쉬 조작 강화

**목표**: 메쉬 품질 후처리 및 형상 최적화 루프 지원

| 추가 툴 | 라이선스 | 설치 | 역할 |
|--------|---------|------|------|
| **pygeogram** | BSD-3 | 소스 빌드 | Geogram Python API (vorpalite subprocess 대체) |
| **PyGeM** | MIT | `pip install pygem` | RBF/FFD/IDW 메쉬 모핑, OpenFOAM 형식 직지원 |
| **xatlas-python** | MIT | `pip install xatlas` | UV 언랩 (AI 모델 입력 전처리) |

**달성 기준**:
- vorpalite CLI 없이도 Geogram 리메쉬 Python에서 직접 호출
- 메쉬 재생성 없이 형상 파라메트릭 변형 (최적화 루프)

---

## v1.5 — 파티셔닝·솔버·시각화

**목표**: 대형 병렬 케이스 지원, 대안 CFD 솔버, 개발자 시각화 강화

| 추가 툴 | 라이선스 | 설치 | 역할 |
|--------|---------|------|------|
| **PyMetis** | MIT | conda-forge | METIS 5.2 메쉬 파티셔닝 (10M+ 셀 병렬) |
| **SU2** | LGPL-2.1 | installer | OpenFOAM 대안 CFD 솔버 (검증) |
| **Polyscope-py** | MIT | `pip install polyscope` | 실시간 3D 메쉬 시각화 (5줄 통합) |
| **K3D-jupyter** | MIT | `pip install k3d` | Jupyter WebGL 3D 뷰어 |

**달성 기준**:
- 1000만 셀 이상 메쉬에서 decomposePar 대체 파티셔닝 동작
- OpenFOAM 미설치 시 SU2로 자동 fallback 검증
- 개발 중 Python 5줄로 메쉬 시각화 확인

---

## v2.0 — Qt GUI (Godot 제거)

**목표**: Godot 4.3 제거, PySide6 + PyVistaQt 기반 Windows 네이티브 GUI

### GUI 아키텍처

```
PySide6 (Qt 6.7) 메인 윈도우
    ├── PyVistaQt BackgroundPlotter  ← 3D 메쉬 뷰어 (기존 pyvista 코드 재사용)
    ├── 품질 레벨 선택 패널          ← draft / standard / fine
    ├── 진행 상황 패널               ← WebSocket 실시간 스트리밍
    └── 로그 뷰어                   ← structlog JSON 렌더링
FastAPI + WebSocket (유지)           ← GUI ↔ 파이프라인 통신
```

| 추가 툴 | 라이선스 | 설치 | 역할 |
|--------|---------|------|------|
| **PySide6** | LGPL-3.0 | `pip install PySide6` | Qt 6.7 GUI 프레임워크 |
| **PyVistaQt** | MIT | `pip install pyvistaqt` | VTK 3D 뷰어 Qt 임베드 |

**달성 기준**:
- Godot 의존성 완전 제거
- Windows에서 드래그앤드롭 → 메쉬 생성 → 3D 뷰어 표시 end-to-end 동작
- 진행 상황 실시간 표시 (Preprocessor L1→L2→L3, Generator Tier 전환 등)

---

## v2.1 — Quad/Hex 메쉬 경로

**목표**: 현재 파이프라인에 없는 Quad 리메쉬 → Hex 볼륨 경로 신설

| 추가 툴 | 라이선스 | 설치 | 역할 |
|--------|---------|------|------|
| **QuadWild** | GPL-3.0 | subprocess (빌드) | 특징선 기반 Quad 표면 리메쉬 |
| **GMDS** | LGPL-2.1 | conda-forge | CEA 산업용 Quad/Hex 메셔 (pygmds) |

**달성 기준**:
- Fine 품질에서 Quad 표면 → Hex 볼륨 경로 동작
- snappyHexMesh 없이도 hex-dominant 볼륨 메쉬 생성 가능

---

## v2.2 — AI 메쉬 강화

**목표**: L3 AI fallback 다양화, AI surrogate 품질 예측

| 추가 툴 | 라이선스 | 설치 | 역할 |
|--------|---------|------|------|
| **InstantMesh** | Apache-2.0 | import (GPU) | 단일 이미지→watertight 메쉬 (L3 대안) |
| **NeuralOperator** | MIT | `pip install neuraloperator` | FNO — 임의 메쉬 위 물리 필드 예측 |

**달성 기준**:
- MeshAnythingV2 실패 시 InstantMesh로 자동 전환 (GPU 환경)
- checkMesh 전 NeuralOperator로 품질 사전 예측 → 불필요한 재시도 감소

---

## v2.3 — Windows 패키징 완성

**목표**: 단일 설치파일(.exe)로 배포 가능한 완성형 Windows 앱

| 추가 툴 | 라이선스 | 설치 | 역할 |
|--------|---------|------|------|
| **Nuitka** | Apache-2.0 | `pip install nuitka` | Python→C 컴파일, PyInstaller 대비 2-4× 빠름 |

**달성 기준**:
- NSIS 또는 Inno Setup 기반 Windows 설치파일 생성
- 설치 후 OpenFOAM(WSL2) 없이도 Draft/Standard 메쉬 생성 동작
- 앱 크기 목표: 설치 후 3GB 이하 (AI 모델 제외)

---

## v3.0 — Web SaaS

**목표**: CLI/데스크톱을 FastAPI + Next.js로 래핑, 브라우저 접근 지원

- FastAPI 백엔드: 파이프라인 REST API 래핑
- Next.js 프론트엔드: 파일 업로드, 진행 상황, 3D 뷰어 (Three.js)
- 인증: 연구기관 이메일 또는 GitHub OAuth
- 스토리지: S3 호환 (MinIO 또는 AWS S3)

---

## v3.1 — 경계층(BL) 메쉬

**목표**: 항공/터보 CFD 수준의 경계층 메쉬 전용 지원

| 추가 툴 | 라이선스 | 역할 |
|--------|---------|------|
| **pyHyp** | Apache-2.0 | 쌍곡선 BL 압출 → 구조적 O-grid 볼륨 메쉬 |
| **enGrid** | GPL-2.0 | 프리즈매틱 BL 메쉬 생성 → OpenFOAM 직출력 |

---

## v3.2 — AI Surrogate CFD

**목표**: 실제 CFD 솔버 없이 AI로 유동장 예측, 경계조건 자동 추론

| 추가 툴 | 라이선스 | 역할 |
|--------|---------|------|
| **PINA** | MIT | PINN + Neural Operator 통합 (N-S 방정식 surrogate) |
| **GNS/MeshNet** | MIT | DeepMind MeshGraphNets — 메쉬 기반 유동 예측 |
| **Foam-Agent** | MIT | LLM + RAG 기반 경계조건 자동 추론 (NeurIPS 2025) |

---

## v3.3 — 연구 특수 툴

**목표**: 학술 연구 수준 메쉬 알고리즘 통합

| 추가 툴 | 라이선스 | 역할 |
|--------|---------|------|
| **AlgoHex** | AGPL-3.0 | Tet→Hex 자동 변환 (ERC 최신 학술 구현) |
| **QuadriFlow** | MIT | 고품질 Quad 리메쉬 |
| **robust_hex_dominant_meshing** | Research | Hex-dominant 볼륨 직접 변환 (SIGGRAPH 2017) |
| **Mesquite** | LGPL-2.1 | 노드 이동 메쉬 품질 최적화 (Sandia Labs) |
| **pygalmesh** | LGPL | CGAL Volume Tet (수학적 품질 보장) |
| **Wildmeshing Toolkit** | MIT | 메쉬 최적화 레이어 |
| **FlexiCubes** | Apache-2.0 | 미분가능 등값면 추출 (NVIDIA) |
| **DMesh++** | Research | 미분가능 메쉬 최적화 (NeurIPS 2024) |
| **Cassiopee (ONERA)** | GPL-3.0 | CGNS 기반 CFD 전/후처리 (프랑스 항공우주) |
| **pyvoro** | BSD | Voronoi 폴리헤드럴 메쉬 |
| **MicroStructPy** | MIT | Voronoi power diagram 폴리헤드럴 메쉬 |
| **FBPINNs** | MIT | 도메인 분해 PINN (JAX, 10-1000× 빠름) |

---

## 파이프라인 아키텍처 (v1.0 목표 기준)

```
입력 (STL/STEP/OBJ/PLY/CGNS/Exodus/포인트 클라우드)
    │
    ▼
[Analyzer]  — 파일 로딩, 지오메트리 분석 → geometry_report.json
    │
    ▼
[Preprocessor]  — 표면 수리/리메쉬
    L1: pymeshfix → mesh2sdf(fallback)
    L2: geogram/vorpalite → pyACVD → pymeshlab → seagullmesh(fallback)
    L3: MeshAnythingV2 / InstantMesh (AI, 비상업 연구 한정)
    │
    ▼
[Strategist]  — 품질 레벨·Tier 선택, 파라미터 결정 → mesh_strategy.json
    │
    ▼
[Generator]  — 볼륨 메쉬 생성
    Draft:    TetWild → JIGSAW(fallback)
    Standard: Netgen → MeshPy/TetGen(fallback)
    Fine:     snappyHexMesh/cfMesh → MMG → classy_blocks(구조적 Hex)
    │
    ▼ (최대 3회 반복)
[Evaluator]  — 품질 검증
    neatmesh + ofpp (OpenFOAM 없이)
    checkMesh (OpenFOAM 있을 때)
    Hausdorff 거리 표면 충실도
    │
    ▼
OpenFOAM polyMesh 출력
    + foamlib으로 BC 자동 설정
    + OpenFOAMCaseGenerator로 실행 가능한 케이스 생성
```
