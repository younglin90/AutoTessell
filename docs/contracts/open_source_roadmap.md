# 오픈소스 툴 로드맵 (Open-Source Tools Roadmap)

Auto-Tessell 파이프라인에 통합 예정인 오픈소스 라이브러리 명세.
1·2·3·4차 조사 결과를 반영한 버전별 계획서.

> **라이선스 방침**: Auto-Tessell은 MIT 라이선스 (비상업 연구용).
> 신규 툴 채택 시 GPL 계열은 subprocess 격리, LGPL/MIT/BSD/Apache는 직접 임포트 허용.

---

## 설치 현황 (v0.3.5 기준, 2026-04-15 갱신)

### Tier Generator — 동작 상태 (17개 Tier, 전부 동작)

| Tier | 엔진 | 설치 상태 | 동작 | 비고 |
|------|------|---------|------|------|
| tier2_tetwild | pytetwild (TetWild) | ✅ 설치됨 | ✅ 정상 (~0.7s) | Draft 기본 엔진 |
| tier05_netgen | netgen-mesher | ✅ 설치됨 | ✅ 정상 (~0.8s) | Standard 기본 엔진 |
| tier1_snappy | OpenFOAM snappyHexMesh | ✅ 설치됨 | ✅ 정상 (~1.1s) | Fine 기본 엔진 |
| tier15_cfmesh | OpenFOAM cfMesh | ✅ 설치됨 | ✅ 정상 (~5.4s) | Standard Hex |
| tier_cinolib_hex | cinolib (CLI 래퍼) | ✅ 설치됨 | ✅ 정상 (~1.4s) | Hex 볼륨 |
| tier_voro_poly | pyvoro-mm | ✅ 설치됨 | ✅ 정상 (~0.06s) | Voronoi 폴리헤드럴 |
| tier_meshpy | MeshPy (TetGen 래퍼) | ✅ 설치됨 | ✅ 수정됨 (~0.3s) | TetGen 옵션 스위치 문자열로 수정 (v0.3.2) |
| tier_wildmesh | wildmeshing | ✅ 설치됨 | ✅ 수정됨 (~0.2s) | 3-tuple 언팩 수정, x축 비대칭 버그 수정 (v0.3.5) |
| tier_gmsh_hex | gmsh (transfinite) | ✅ 설치됨 | ✅ 수정됨 (~0.5s) | 명시적 볼륨 생성 + 완화된 실패 조건 (v0.3.2) |
| tier_hex_classy_blocks | classy_blocks + numpy | ✅ 설치됨 | ✅ 수정됨 (~1.1s) | numpy 2.x 호환 패치 + controlDict 자동 생성 (v0.3.2) |
| tier0_core | geogram CDT | ⚠️ 부분 | ✅ Graceful fail | C++ 확장 미빌드 시 AttributeError 없이 실패 처리 (v0.3.2) |
| tier_mmg3d | MMG3D 바이너리 | ✅ 설치됨 (~/.local/bin) | ✅ 정상 (~5s) | TetGen 초기 메쉬 + MMG3D 품질 최적화 (v0.3.2 신규) |
| tier_robust_hex | RobustPureHexMeshing 바이너리 | ✅ 빌드됨 (bin/) | ✅ 정상 (~240s/n=3) | Feature-Preserving Octree All-Hex. GCC13 패치 적용 (v0.3.2 신규) |
| tier_algohex | AlgoHex 바이너리 | ✅ 빌드됨 (AlgoHex/) | ✅ 정상 (~58s) | Frame-Field Tet→Hex. OVM ASCII 파서 직접 구현 (v0.3.4 신규) |
| tier_jigsaw | jigsawpy + libjigsaw.so | ✅ ctypes 바인딩 | ✅ 수정됨 (~0.6s) | ctypes binary API, jcfg_file 필수화 (v0.3.4) |
| tier_jigsaw_fallback | jigsawpy + libjigsaw.so | ✅ ctypes 바인딩 | ✅ 수정됨 (~0.0s) | jigsaw_jig_t API 전면 재작성 (v0.3.4) |
| tier_hohqmesh | HOHQMesh 바이너리 | ✅ bin/HOHQMesh | ✅ 수정됨 (~1.9s) | ISM 가변길이 직접 파서 구현 (v0.3.4) |
| tier0_2d_meshpy | MeshPy (Triangle) | ✅ 설치됨 | ⚠️ 미검증 | 2D 메쉬 전용 |
| tier_polyhedral | OpenFOAM polyDualMesh | ✅ 설치됨 | ⚠️ 미검증 | 기존 볼륨 메쉬 필요 (특수 케이스) |

### 신규 추가 라이브러리 / 기능 (v0.3.0 → v0.3.5)

| 라이브러리/기능 | 버전 | 설치 방법 | 용도 | 상태 |
|----------------|------|---------|------|------|
| pyvoro-mm | v0.3.2 | `pip install pyvoro-mm` | Voro++ Python 바인딩 (Voronoi 폴리헤드럴) | ✅ 동작 |
| rtree | v0.3.2 | `pip install rtree` | trimesh.contains() 의존성 | ✅ 동작 |
| jigsawpy | v0.3.4 | `pip install jigsawpy` + libjigsaw.so | JIGSAW ctypes API | ✅ 동작 |
| MMG3D | v0.3.2 | `~/.local/bin/mmg3d` (기존) | Tet 품질 최적화 | ✅ 동작 |
| RobustPureHexMeshing | v0.3.2 | GCC13 소스 빌드 (`bin/`) | All-Hex 메쉬 | ✅ 동작 |
| AlgoHex | v0.3.4 | COIN-OR CLP 의존성 소스 빌드 | Frame-Field Hex | ✅ 동작 |
| HOHQMesh | v0.3.4 | 바이너리 `bin/HOHQMesh` | High-Order Hex | ✅ 동작 |
| ESI OpenFOAM (Windows) | v0.3.5 | MSYS2 기반 별도 설치 | snappy/cfMesh on Windows | ✅ 지원 추가 |
| Windows NSIS Installer | v0.3.5 | `makensis installer/autotessell.nsi` | 클릭 설치 .exe | ✅ 동작 |

### 버그 수정 이력

| 버전 | 컴포넌트 | 버그 | 수정 |
|------|---------|------|------|
| v0.3.2 | tier_meshpy | `invalid option: max_volume` | TetGen 스위치 문자열 API |
| v0.3.2 | tier_wildmesh | `too many values to unpack` | 3-tuple 언팩 수정 |
| v0.3.2 | tier_hex_classy_blocks | `numpy.bool8` 제거됨 (numpy 2.x) | monkey-patch 호환 |
| v0.3.2 | tier_gmsh_hex | transfinite 복잡 형상 실패 | 실패 조건 완화 |
| v0.3.2 | tier0_core | C++ 확장 attr 없음 | graceful ImportError |
| v0.3.4 | tier_jigsaw | `Incorrect type: NAME` | ctypes API 재작성 |
| v0.3.4 | tier_jigsaw_fallback | `jigsaw_msh()` 없음 | jigsaw_jig_t API 재작성 |
| v0.3.4 | tier_hohqmesh | ISM 파싱 실패 | ISM 직접 파서 구현 |
| v0.3.4 | tier_algohex | OVM ASCII 파싱 실패 | OVM 파서 직접 구현 |
| v0.3.5 | geometry_analyzer | WildMesh x축 비대칭 | `_estimate_flow()` 기본값 internal |
| v0.3.5 | Windows installer | conda env create 실패 | python=3.12 + pip만 생성, 나머지 pip |

### Hex 메싱 라이브러리 평가 결과 (2026-04-14)

사용자 요청에 따라 Hex-dominant / All-Hex 메쉬 생성 라이브러리 전수 조사 결과:

| 라이브러리 | 설치 상태 | 이유 |
|-----------|---------|------|
| snappyHexMesh | ✅ tier1_snappy | 이미 구현됨 |
| cfMesh | ✅ tier15_cfmesh | 이미 구현됨 |
| blockMesh (OpenFOAM) | ✅ tier_hex_classy_blocks | classy_blocks를 통해 구현됨 |
| HOHQMesh | ⚠️ tier_hohqmesh | ISM 파싱 오류, 수정 필요 |
| cinolib | ✅ tier_cinolib_hex | 이미 구현됨 |
| MMG3D | ✅ tier_mmg3d | 신규 구현 (TetGen+최적화) |
| Feature-Preserving-Octree-Hex-Meshing | ✅ tier_robust_hex | **신규 빌드 성공** (GCC13 패치 적용). 순수 all-hex 메쉬. ~200s/sphere n=4. OBJ 입력 필요 |
| AlgoHex | ❌ 빌드 실패 | COIN-OR CLP 의존성: `sudo apt install coinor-libclp-dev coinor-libcbc-dev` 필요. 설치 후 재빌드 가능 |
| libHexEx | ❌ 미설치 | AlgoHex 하위 의존성. AlgoHex 설치 전제 |
| QGP3D | ❌ 미설치 | AlgoHex 하위 의존성 (COIN-OR CLP 필요) |
| HexDom/HexGen (CMU-CBML) | ❌ 포기 | LS-DYNA .k 전용 입력 포맷. STL/OBJ 미지원, 크래시 시뮬레이션 FEA 도구 |
| CE-PolyCube (msraig) | ❌ 포기 | Windows 전용 실행파일 + MOSEK 상용 라이선스 + PolyCut 월단위 라이선스 필요 |
| hexmachina | ❌ 미설치 | PyPI 미등록. 소스만 존재 |
| dds-hexmeshing | ❌ 미설치 | PyPI 미등록. C++ 데이터/스크립트 only |
| OpenVolumeMesh | ❌ 미설치 | Python 바인딩 없음. C++ only |
| HexaLab | ❌ 해당없음 | WebGL 브라우저 전용 뷰어, 메쉬 생성 기능 없음 |
| CUBIT/Sculpt | ❌ 해당없음 | 상용 소프트웨어 (Sandia, 라이선스 필요) |
| Hexotic | ❌ 해당없음 | 상용 소프트웨어 (Distene) |
| MeshGems | ❌ 해당없음 | 상용 소프트웨어 (Distene) |
| GridPro | ❌ 해당없음 | 상용 소프트웨어 (Program Development Corp.) |
| SALOME | ❌ 해당없음 | 전체 플랫폼 (CLI 래퍼 가능하나 설치 복잡) |
| HexGen (HybridOctree_Hex) | ⚠️ 빌드됨 → 포기 | 단순 형상에서 100M 셀 퇴화 메쉬, 실용성 없음 |

### Tier 수정 완료 항목 (v0.3.2, 2026-04-14)

| 항목 | 파일 | 오류 | 수정 내용 |
|------|------|------|---------|
| tier_meshpy | `core/generator/tier_meshpy.py` | `invalid option: max_volume` | TetGen 옵션을 스위치 문자열로 변경: `f"pq{min_angle}a{max_vol}"` |
| tier_wildmesh | `core/generator/tier_wildmesh.py` | `too many values to unpack` | `get_tet_mesh()` 3-tuple 반환 처리: `tet_v, tet_f = result[0], result[1]` |
| tier_hex_classy_blocks | `core/generator/tier_hex_classy_blocks.py` | `numpy.bool8` 제거됨 | numpy 2.x 호환 monkey-patch + controlDict 자동 생성 |
| tier_jigsaw | `core/generator/tier_jigsaw.py` | `Incorrect type: NAME` | `opts.jcfg_file` 설정 필수화, STL→medit 변환, binary 감지 추가 |
| tier_jigsaw_fallback | `core/generator/tier_jigsaw_fallback.py` | `jigsaw_msh()` 없음 | 전체 재작성: `jigsaw_jig_t` API 사용, binary 감지 |
| tier_gmsh_hex | `core/generator/tier_gmsh_hex.py` | transfinite 실패 | 명시적 볼륨 엔티티 생성, 실패 조건 완화 (`not hex and not tet`) |
| tier0_core | `core/generator/tier0_core.py` | C++ attr 없음 | `hasattr` 검사로 graceful ImportError 처리 |
| tier_hohqmesh | `core/generator/tier_hohqmesh.py` | ISM 파싱 실패 | ⚠️ 미완, HOHQMesh ISM 포맷 직접 파서 구현 필요 |

---

## 버전 체계

| 버전 | 상태 | 핵심 목표 | 추가 툴 수 |
|------|------|---------|----------|
| v0.1 | ✅ 완료 | 5-Agent 파이프라인 기반, CLI 기본 동작 | — |
| v0.2 | ✅ 완료 | Evaluator 강화 (NativeMeshChecker, Hausdorff) | 2 |
| v0.3 | ✅ 완료 | Generator 17-Tier 완성, Qt GUI, E2E 88% | 8 |
| v0.3.4 | ✅ 완료 | AlgoHex/HOHQMesh/JIGSAW 전부 수정, OVM 파서 구현 | 3 |
| v0.3.5 | ✅ 완료 | Windows NSIS 설치파일, WildMesh flow_type 버그, OpenFOAM Windows | 2 |
| v0.4 | 📋 예정 | 케이스 자동화 (foamlib + OFCaseGenerator) | 2 |
| v0.5 | 📋 예정 | 전처리 강화 (SDF 복구, 데시메이션, 형상 생성) | 3 |
| v1.0 | 📋 예정 | CLI 안정 릴리스, 출력 포맷 확장 (SU2/Fluent/CGNS) | — |
| v1.1 | 📋 예정 | 비매니폴드 수리 강화 (CGAL Alpha Wrap) | 2 |
| v1.2 | 📋 예정 | 포인트 클라우드 입력 (LiDAR/스캔 지원) | 2 |
| v1.3 | 📋 예정 | 포맷 확장 (CGNS, Exodus II) | 2 |
| v1.4 | 📋 예정 | 메쉬 조작 강화 (모핑, UV, Geogram API) | 3 |
| v1.5 | 📋 예정 | 파이프라인 강화 (seagullmesh, Open3D, libigl) | 4 |
| v2.0 | ✅ 완료 (조기 달성) | Qt GUI 완성 (PySide6+PyVistaQt, Godot 제거) | 2 |
| v2.1 | 📋 예정 | Quad/Hex 메쉬 경로 신설 | 2 |
| v2.2 | 📋 예정 | AI 메쉬 강화 (L3 다양화, surrogate) | 2 |
| v2.3 | ✅ 완료 (조기 달성) | Windows NSIS 설치파일 (v0.3.5 구현) | 1 |
| v3.0 | 📋 예정 | Web SaaS (FastAPI + Next.js) | — |
| v3.1 | 📋 예정 | 경계층(BL) 메쉬 (pyHyp, enGrid) | 2 |
| v3.2 | 📋 예정 | AI Surrogate CFD (PINA, GNS, Foam-Agent) | 3 |
| v3.3 | 📋 예정 | 연구 특수 툴 (FlexiCubes, PolyCut 등) | 12 |

---

## 현재 파이프라인 (v0.1 기준선)

| 툴 | 라이선스 | 용도 | 통합 방식 |
|----|---------|------|----------|
| trimesh | MIT | 표면 메쉬 로딩/분석 | import |
| pyACVD | MIT | 표면 리메쉬 L2 (Voronoi) | import |
| pymeshfix | MIT | 표면 수리 L1 | import |
| pymeshlab | GPL-3.0 | 표면 수리/리메쉬 L2 | import (GPL 격리 고려) |
| geogram (vorpalite) | BSD | 표면 리메쉬 L2 최우선, 특징 보존 | subprocess (CLI 바이너리) |
| pytetwild (TetWild) | MPL-2.0 | Volume Tet Draft | import |
| netgen-mesher | LGPL-2.1 | Volume Tet Standard | import |
| OpenFOAM (snappyHexMesh/cfMesh) | GPL-2.0+ | Volume Hex Fine | subprocess |
| MMG | LGPL-3.0 | Volume Tet Fine | subprocess |
| MeshAnythingV2 | S-Lab 1.0 | L3 AI 표면 수리 (비상업 연구 한정) | import |
| meshgpt-pytorch | MIT | AI 메쉬 생성 | import |
| cadquery | LGPL-2.1 | STEP/IGES CAD 테셀레이션 | import |
| gmsh | GPL-2.0+ | CAD 테셀레이션 fallback | import (API 모드) |
| meshio | MIT | 메쉬 포맷 변환 | import |
| pyvista | BSD | 메쉬 시각화/분석 | import |

---

## v1.0 — CLI 완성 (pip, Windows 완전 지원)

### v1.0-1. neatmesh
- **GitHub**: https://github.com/eigemx/neatmesh
- **라이선스**: MIT
- **Python**: Yes (pure Python)
- **Windows**: 완전 지원
- **용도**: OpenFOAM 없이 CFD 메쉬 품질 지표 계산
  (셀 볼륨, 면 면적, 법선, 비직교성, skewness, neighbor volume ratio)
- **파이프라인 위치**: Evaluator — OpenFOAM checkMesh 대안/보완
- **통합 방식**: `pip install neatmesh` → import
- **우선순위**: ★★★

### v1.0-2. mesh2sdf
- **GitHub**: https://github.com/wang-ps/mesh2sdf
- **라이선스**: MIT
- **Python**: Yes (pip)
- **Windows**: 완전 지원
- **용도**: 비watertight 삼각 메쉬 → SDF → 보장된 watertight 메쉬 추출
  (pymeshfix·pyACVD 실패 케이스 자동 복구)
- **파이프라인 위치**: Preprocessor L1 수리 fallback (pymeshfix 실패 후)
- **통합 방식**: `pip install mesh2sdf` → import
- **우선순위**: ★★★

### v1.0-3. MeshPy
- **GitHub**: https://github.com/inducer/meshpy
- **라이선스**: MIT (래퍼) + Triangle 비상업 / TetGen AGPL
- **Python**: Yes — Windows `win_amd64` wheel 제공
- **Windows**: 완전 지원 (pre-built wheel)
- **용도**: Triangle(2D 고품질 Delaunay 삼각화) + TetGen 래퍼
- **파이프라인 위치**: Generator — 2D 단면/입구 메쉬, TetWild 대안 Tet
- **통합 방식**: `pip install meshpy` → import
- **우선순위**: ★★★

### v1.0-4. classy_blocks
- **GitHub**: https://github.com/damogranlabs/classy_blocks
- **라이선스**: MIT
- **Python**: Yes (pure Python)
- **Windows**: 완전 지원
- **용도**: Python 클래스로 OpenFOAM blockMeshDict 프로그래밍 생성
  (구조적 Hex 메쉬를 외부 메셔 없이 파이프라인 내에서 직접 생성)
- **파이프라인 위치**: Generator — Standard/Fine 구조적 Hex 경로 신설
- **통합 방식**: `pip install classy-blocks` → import
- **우선순위**: ★★★

### v1.0-5. foamlib
- **GitHub**: https://github.com/gerlero/foamlib
- **라이선스**: MIT
- **Python**: Yes (pure Python, async 지원)
- **Windows**: 완전 지원
- **용도**: OpenFOAM 파일 타입힌트 I/O (JOSS 2025).
  `FoamFile` dict, `AsyncFoamCase` 비동기 케이스 실행, BC 자동 설정
- **파이프라인 위치**: Generator/Evaluator — 수동 파일 쓰기 대체
- **통합 방식**: `pip install foamlib` → import
- **우선순위**: ★★☆

### v1.0-6. OpenFOAMCaseGenerator
- **GitHub**: https://github.com/tomrobin-teschner/OpenFOAMCaseGenerator
- **라이선스**: MIT
- **Python**: Yes (pure Python)
- **Windows**: 완전 지원
- **용도**: Python config 하나로 `0/`, `constant/`, `system/` 전체 케이스 생성
- **파이프라인 위치**: Generator 후처리 — 메쉬 → 실행 가능한 케이스 자동 생성
- **통합 방식**: `pip install openfoam-case-generator` → import
- **우선순위**: ★★☆

### v1.0-7. fast-simplification
- **GitHub**: https://github.com/pyvista/fast-simplification
- **라이선스**: MIT
- **Python**: Yes (pip)
- **Windows**: 완전 지원
- **용도**: 고속 Quadric 메쉬 데시메이션 (VTK 대비 4-5×). 200k+ 면 입력 전처리
- **파이프라인 위치**: Preprocessor L2 전처리 (pyACVD 앞단)
- **통합 방식**: `pip install fast-simplification` → import
- **우선순위**: ★★☆

### v1.0-8. JIGSAW-Python
- **GitHub**: https://github.com/dengwirda/jigsaw-python
- **라이선스**: Custom OSS (비상업 연구 무료)
- **Python**: Yes (native Python)
- **Windows**: MSVC 빌드 공식 지원, conda-forge
- **용도**: Delaunay + Voronoi 기반 2D/3D 비구조 메셔. TetWild과 다른 트레이드오프
- **파이프라인 위치**: Generator Draft fallback 추가
- **통합 방식**: `conda install -c conda-forge jigsaw` → import
- **우선순위**: ★★☆

### v1.0-9. ofpp
- **GitHub**: https://github.com/xu-xianghua/ofpp
- **라이선스**: MIT
- **Python**: Yes (pure Python, NumPy만 의존)
- **Windows**: 완전 지원
- **용도**: OpenFOAM polyMesh 경량 Python 파서.
  points/faces/owner/neighbour/boundary → NumPy 배열. ASCII/binary 지원
- **파이프라인 위치**: Evaluator — 생성 결과 검증, PolyMeshWriter 보완
- **통합 방식**: `pip install ofpp` → import
- **우선순위**: ★★☆

### v1.0-10. fogleman/sdf
- **GitHub**: https://github.com/fogleman/sdf
- **라이선스**: MIT
- **Python**: Yes (pure Python + NumPy)
- **Windows**: 완전 지원
- **용도**: SDF CSG 연산(union/difference/intersection) + 병렬 marching cubes
  벤치마크 형상 및 테스트용 덕트/채널 기본 형상 생성
- **파이프라인 위치**: 테스트 유틸리티
- **통합 방식**: `pip install sdf` → import
- **우선순위**: ★★☆

---

## v1.5 — 파이프라인 강화 (conda/subprocess)

### v1.5-1. seagullmesh (CGAL Alpha Wrap)
- **GitHub**: https://github.com/darikg/seagullmesh
- **라이선스**: LGPL-3.0
- **Python**: Yes (pybind11)
- **Windows**: conda-forge
- **용도**: CGAL 5.5+ Alpha Wrap — 비매니폴드·자기교차·열린 soup을 지정 오프셋으로 watertight 변환.
  pymeshfix/pyACVD보다 강력한 L2 수리 fallback
- **파이프라인 위치**: Preprocessor L2 — 심각한 비매니폴드 처리
- **통합 방식**: `conda install -c conda-forge seagullmesh`
- **우선순위**: ★★★

### v1.5-2. Open3D
- **GitHub**: https://github.com/isl-org/Open3D
- **라이선스**: MIT
- **Python**: Yes (pip)
- **Windows**: 완전 지원
- **용도**: Screened Poisson, Alpha Shape, Ball-Pivoting 표면 재구성.
  포인트 클라우드 입력 경로 신설 (현재 파이프라인에 없음)
- **파이프라인 위치**: Preprocessor — 스캔/포인트 클라우드 입력
- **통합 방식**: `pip install open3d`
- **우선순위**: ★★☆

### v1.5-3. libigl
- **GitHub**: https://github.com/libigl/libigl
- **라이선스**: MPL-2.0
- **Python**: Yes (`pip install libigl`)
- **Windows**: 완전 지원
- **용도**: Laplacian 스무딩, Boolean ops, 이산 미분 연산자, 파라메트리제이션
- **파이프라인 위치**: Preprocessor/Generator — 메쉬 스무딩·Boolean 수술
- **통합 방식**: `pip install libigl`
- **우선순위**: ★★☆

### v1.5-4. PyMetis
- **GitHub**: https://github.com/inducer/pymetis
- **라이선스**: MIT + Apache-2.0 (METIS 번들)
- **Python**: Yes (pybind11)
- **Windows**: conda-forge
- **용도**: METIS 5.2 메쉬 파티셔너. 대형 메쉬(10M+ 셀) 병렬 OpenFOAM decomposition
- **파이프라인 위치**: Generator 후처리 — 병렬 케이스 decomposition
- **통합 방식**: `conda install -c conda-forge pymetis`
- **우선순위**: ★★☆

### v1.5-5. pygeogram
- **GitHub**: https://github.com/BrunoLevy/pygeogram
- **라이선스**: BSD-3-Clause
- **Python**: Yes (pybind11)
- **Windows**: Linux 우선, Windows 별도 빌드
- **용도**: Geogram 전체 Python API. vorpalite CLI 대신 직접 API 호출로 Voronoi 리메쉬
- **파이프라인 위치**: Preprocessor L2 — vorpalite subprocess 대체
- **통합 방식**: 소스 빌드
- **우선순위**: ★★☆

### v1.5-6. pyCGNS
- **GitHub**: https://github.com/pyCGNS/pyCGNS
- **라이선스**: LGPL-2.0
- **Python**: Yes (C extension)
- **Windows**: conda-forge
- **용도**: CGNS/HDF5 완전 지원 — 항공우주 표준 메쉬 포맷 입출력
- **파이프라인 위치**: Analyzer 입력 / Generator 출력 포맷 확장
- **통합 방식**: `conda install -c conda-forge pycgns`
- **우선순위**: ★★☆

### v1.5-7. SEACAS / exodus.py
- **GitHub**: https://github.com/sandialabs/seacas
- **라이선스**: BSD-3-Clause
- **Python**: Yes (exodus.py 포함)
- **Windows**: conda-forge 또는 CMake
- **용도**: Exodus II 포맷 Python I/O (Abaqus/Sierra/Cubit 연동)
- **파이프라인 위치**: Analyzer/Generator 포맷 확장
- **통합 방식**: `pip install seacas`
- **우선순위**: ★★☆

### v1.5-8. SU2
- **GitHub**: https://github.com/su2code/SU2
- **라이선스**: LGPL-2.1
- **Python**: Yes (pysu2)
- **Windows**: 공식 설치파일 제공
- **용도**: 멀티피직스 CFD 솔버. OpenFOAM 미설치 환경 검증 대안
- **파이프라인 위치**: Evaluator — CFD 솔버 검증
- **통합 방식**: installer + pysu2 import
- **우선순위**: ★★☆

### v1.5-9. PyGeM
- **GitHub**: https://github.com/mathLab/PyGeM
- **라이선스**: MIT
- **Python**: Yes (pure Python)
- **Windows**: 완전 지원
- **용도**: RBF/FFD/IDW 기반 메쉬 모핑. OpenFOAM 형식 직지원. 1,400만 셀 처리 실적
- **파이프라인 위치**: Generator — 형상 최적화 루프, 메쉬 재생성 없이 변형
- **통합 방식**: `pip install pygem`
- **우선순위**: ★★☆

### v1.5-10. Polyscope-py
- **GitHub**: https://github.com/nmwsharp/polyscope-py
- **라이선스**: MIT
- **Python**: Yes (C++ 코어 + Python 바인딩)
- **Windows**: 완전 지원 (pip wheel, Python 3.9-3.14)
- **용도**: 연구용 실시간 3D 메쉬/볼륨/포인트 클라우드 시각화. 5줄 통합
- **파이프라인 위치**: 개발/디버그 — Python 레벨 메쉬 즉시 검사
- **통합 방식**: `pip install polyscope`
- **우선순위**: ★★☆

---

## v2.0 — Qt GUI 전환 + 고급 메셔

### GUI

| 컴포넌트 | 라이브러리 | 라이선스 | 역할 |
|---------|-----------|---------|------|
| 메인 윈도우 | PySide6 (Qt 6.7) | LGPL-3.0 | 앱 프레임워크 |
| 3D 뷰어 | PyVistaQt | MIT | VTK 기반 메쉬 렌더링 (기존 pyvista 재사용) |
| 렌더 백엔드 | VTK | BSD | 3D 렌더 파이프라인 |
| 패키징 | Nuitka | Apache-2.0 | Python→C 컴파일, 2-4× 빠름 |

### v2.0 추가 메셔

#### v2.0-1. QuadWild
- **GitHub**: https://github.com/nicopietroni/quadwild
- **라이선스**: GPL-3.0
- **Python**: None (C++ CLI)
- **Windows**: CMake/Qt 빌드
- **용도**: 특징선 기반 Quad 표면 리메쉬 → Hex 볼륨 전처리. 현재 파이프라인에 없는 Quad→Hex 경로
- **파이프라인 위치**: Generator Fine — subprocess 호출
- **우선순위**: ★★☆

#### v2.0-2. InstantMesh (Tencent)
- **GitHub**: https://github.com/TencentARC/InstantMesh
- **라이선스**: Apache-2.0
- **Python**: Yes (PyTorch)
- **Windows**: CUDA GPU 필요
- **용도**: 단일 이미지 → watertight 메쉬 (FlexiCubes 기반, 2024). L3 AI MeshAnythingV2 보완
- **파이프라인 위치**: Preprocessor L3 — 대안 AI fallback
- **우선순위**: ★★☆

#### v2.0-3. GMDS (CEA)
- **GitHub**: https://github.com/LIHPC-Computational-Geometry/gmds
- **라이선스**: LGPL-2.1
- **Python**: Yes (pygmds, alpha)
- **Windows**: CI 검증됨
- **용도**: 프랑스 CEA 산업용 Quad/Hex 메쉬. 2D cross field + 3D frame field → hybrid 메쉬
- **파이프라인 위치**: Generator Fine — Quad/Hex 볼륨
- **우선순위**: ★★☆

#### v2.0-4. NeuralOperator (FNO)
- **GitHub**: https://github.com/neuraloperator/neuraloperator
- **라이선스**: MIT
- **Python**: Yes (PyTorch)
- **Windows**: PyTorch 환경
- **용도**: FNO/GINO — 임의 메쉬 위 물리 필드 예측. checkMesh 대기 없이 품질 사전 예측
- **파이프라인 위치**: Evaluator 가속 — AI surrogate
- **우선순위**: ★★☆

#### v2.0-5. xatlas-python
- **GitHub**: https://github.com/mworchel/xatlas-python
- **라이선스**: MIT
- **Python**: Yes (pip wheel)
- **Windows**: 완전 지원
- **용도**: 자동 UV 언랩. AI 모델(MeshAnythingV2) 입력 전처리
- **파이프라인 위치**: Preprocessor L3 전처리
- **우선순위**: ★★☆

#### v2.0-6. K3D-jupyter
- **GitHub**: https://github.com/K3D-tools/K3D-jupyter
- **라이선스**: MIT
- **Python**: Yes (ipywidget)
- **Windows**: 완전 지원
- **용도**: Jupyter WebGL 3D 메쉬 뷰어. PyVista 연동. 개발 중 빠른 메쉬 검사
- **파이프라인 위치**: 개발/디버그
- **우선순위**: ★★☆

---

## v3.0 — Web SaaS + 연구 특수 툴

### Web SaaS
FastAPI 백엔드 + Next.js 프론트엔드 래핑.

### 연구 특수 툴

| 툴 | 라이선스 | 용도 |
|----|---------|------|
| pyHyp | Apache-2.0 | 쌍곡선 BL 압출 (항공 경계층) |
| enGrid | GPL-2.0 | 프리즈매틱 BL 메쉬 → OpenFOAM 직출력 |
| QuadriFlow | MIT | 고품질 Quad 리메쉬 |
| robust_hex_dominant_meshing | Research | Hex-dominant 볼륨 직접 변환 (SIGGRAPH 2017) |
| AlgoHex | AGPL-3.0 | Tet→Hex 자동 변환 (ERC 연구) |
| Mesquite | LGPL-2.1 | 노드 이동 메쉬 품질 최적화 (Sandia) |
| pygalmesh | LGPL | CGAL Volume Tet (수학적 품질 보장) |
| Wildmeshing Toolkit | MIT | 메쉬 최적화 레이어 |
| Cassiopee (ONERA) | GPL-3.0 | CGNS 기반 CFD 전/후처리 (프랑스 항공우주) |
| FlexiCubes | Apache-2.0 | 미분가능 등값면 추출 (NVIDIA) |
| DMesh++ | Research | 미분가능 메쉬 최적화 (NeurIPS 2024) |
| PINA | MIT | PINN + Neural Operator 통합 (SISSA) |
| GNS/MeshNet | MIT | DeepMind MeshGraphNets PyTorch 구현 |
| Foam-Agent | MIT | LLM 기반 경계조건 자동 추론 (NeurIPS 2025) |
| pyvoro | BSD | Voronoi 폴리헤드럴 메쉬 |
| MicroStructPy | MIT | Voronoi power diagram 폴리헤드럴 메쉬 |
| FBPINNs | MIT | 도메인 분해 PINN (JAX, 10-1000× 빠름) |

---

## 우선순위 요약

```
v1.0 (pip, 즉시)
├── ★★★  neatmesh          OpenFOAM 없는 Evaluator
├── ★★★  mesh2sdf          SDF watertight 복구
├── ★★★  MeshPy            Triangle 2D + TetGen Windows wheel
├── ★★★  classy_blocks     구조적 Hex blockMesh Python 생성
├── ★★☆  foamlib           OpenFOAM I/O 현대화
├── ★★☆  OFCaseGenerator   케이스 자동 생성
├── ★★☆  fast-simplification 대용량 전처리
├── ★★☆  JIGSAW-Python     추가 3D 메셔
├── ★★☆  ofpp              polyMesh Python 파서
└── ★★☆  fogleman/sdf      벤치마크 형상 CSG

v1.5 (conda/subprocess)
├── ★★★  seagullmesh       CGAL Alpha Wrap
├── ★★☆  Open3D            포인트 클라우드 경로
├── ★★☆  libigl            스무딩·Boolean
├── ★★☆  PyMetis           메쉬 파티셔닝
├── ★★☆  pyCGNS / SEACAS   포맷 확장
├── ★★☆  SU2               대안 CFD 솔버
├── ★★☆  PyGeM             메쉬 모핑
└── ★★☆  Polyscope-py      실시간 3D 시각화

v2.0 (Qt GUI + 고급 메셔)
    PySide6 + PyVistaQt, QuadWild, InstantMesh,
    GMDS, NeuralOperator, xatlas, K3D-jupyter
    Nuitka Windows 패키징

v3.0 (Web SaaS + 연구)
    pyHyp, enGrid, AlgoHex, FlexiCubes, PINA,
    Foam-Agent, Cassiopee 등
```

---

## 파이프라인 갭 해소 현황

| 갭 | 해소 버전 | 툴 |
|----|---------|-----|
| OpenFOAM 없는 품질 검사 | v1.0 | neatmesh |
| pymeshfix 실패 복구 | v1.0 / v1.5 | mesh2sdf, seagullmesh |
| 구조적 Hex 메쉬 경로 | v1.0 / v2.0 | classy_blocks, QuadWild |
| 2D 메쉬 생성 | v1.0 | MeshPy (Triangle) |
| OpenFOAM 파일 I/O 현대화 | v1.0 | foamlib |
| 포인트 클라우드 입력 경로 | v1.5 | Open3D |
| CGNS/Exodus 포맷 | v1.5 | pyCGNS, SEACAS |
| 경계층(BL) 메쉬 | v3.0 | pyHyp, enGrid |
| AI surrogate CFD 예측 | v2.0 | NeuralOperator |
| 미분가능 메쉬 최적화 | v3.0 | FlexiCubes, DMesh++ |
| Qt GUI (Godot 대체) | v2.0 | PySide6 + PyVistaQt |
