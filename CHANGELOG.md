# Changelog

## [0.4.0-beta] - 2026-04-22 — "Native-First"

핵심 철학 전환: 외부 라이브러리 의존 → 자체 코드 점진 전환. 라이브러리는
**참고·카피 대상** 이지 의존 대상이 아님. 최종적으로 우리 코드만으로 동작하는 것이
목표. 이번 릴리즈는 그 방향의 기반 공사 + MVP 자체 엔진 3 종 + 자체 L1/L2 + 자체
BL 완성.

### Added — 사용자 경험

- **메쉬 타입 3 카테고리 선택**: `--mesh-type {auto|tet|hex_dominant|poly}` (CLI)
  와 Qt GUI "메쉬 타입" 세그먼트 버튼. 사용자가 1차로 대분류를 고르고 품질 레벨과
  교차해 Tier 가 매핑됨. `mesh_strategy.json` 에 `mesh_type`, `strict_tier` 필드
  추가 (strategy_version 2 → 3).
- **자동 재시도 루프 제거 옵션**: `--auto-retry {off|once|continue}` (기본 off).
  off 는 1 회 시도 후 FAIL 이어도 종료, tty 환경에서는 사용자에게 `y/N` prompt.
  `continue` 는 기존 `max_iterations` 루프 동작 (하위호환).
- **사용자 재시도 prompt (CLI)**: FAIL + auto_retry=off + tty 에서 "Strategist
  권고 파라미터로 한 번 더?" 물음. `QualityReport.user_decision` 기록.

### Added — 자체 코어 (core/*)

- **자체 파일 reader** (`core/analyzer/readers/`): numpy 만으로 STL (binary +
  ASCII), OBJ, PLY (ASCII + binary little/big), OFF 파싱. trimesh 와 face/vertex
  수 / bbox parity 검증됨. `CoreSurfaceMesh` dataclass 통일.
- **자체 topology** (`core/analyzer/topology.py`): is_watertight / is_manifold /
  compute_genus / compute_euler / split_components (union-find) / dihedral_angles
  / count_sharp_edges. trimesh 속성 의존 제거.
- **자체 L1 repair** (`core/preprocessor/native_repair/`): pymeshfix 없이
  dedup_vertices, remove_degenerate_faces, remove_non_manifold_faces (edge 3+
  공유 반복 제거), fill_small_holes (boundary directed loop + fan), fix_face_winding
  (BFS consistency). `run_native_repair()` 통합.
- **자체 L2 remesh** (`core/preprocessor/native_remesh/`): isotropic remesh
  (Botsch & Kobbelt 2004, split/collapse/flip/relocate 반복), Lloyd CVT
  relaxation (area-weighted centroid, KDTree 사영 옵션).
- **자체 BL 생성** (`core/layers/native_bl.py` Phase 2 완성):
  OpenFOAM extrudeMesh+stitchMesh 의 face-orientation 한계를 우회해 Python 에서
  직접 polyMesh 위상 재구성. sphere 에서 3 layer prism 삽입 후 OpenFOAM checkMesh
  Face pyramids OK, Cell volumes OK, Skewness 0.48, open cells 0.
- **tet 전용 BL** (`core/layers/tet_bl_subdivide.py`): native_bl 의 prism wedge
  를 tet 3 개로 분할해 순수 tet 메쉬 유지. sphere 에서 10639 tet, 모두 Face
  pyramids OK.
- **NativeMeshChecker 기본화**: `--checker-engine auto` 기본값이 native 가 됨.
  OpenFOAM checkMesh 는 명시할 때만 교차 검증 용도로 사용. cells/faces/points
  정확 일치, max_non_orthogonality 5% 이내 parity 검증 (`tests/test_native_
  checker_parity.py`).

### Added — Native MVP 엔진 (core/generator/native_*)

- **native_tet** (`core/generator/native_tet/`): scipy Delaunay + uniform grid
  시드 + ray-casting inside-filter. `--tier native_tet` 로 호출. sphere 0.6 초,
  1549 tet.
- **native_hex** (`core/generator/native_hex/`): bbox 내부 uniform hex grid +
  inside filter. OpenFOAM hex vertex 순서 6 face 직접 생성. sphere checkMesh OK,
  aspect_ratio=1.0, skewness~0.
- **native_poly** (`core/generator/native_poly/`): scipy Voronoi 기반 polyhedral.
  Voronoi ridge_vertices 를 그대로 polygon face 로 사용. cells > 0 확인.

### Added — BL 타입별 자동 라우팅

- `tier_layers_post.LayersPostGenerator.run()` 의 `engine="auto"` 를 strategy
  .mesh_type 기반 자동 매핑: tet → `tet_bl_subdivide`, hex_dominant/poly →
  `native_bl`.

### Changed

- `MeshStrategy` schema: `strategy_version` 2 → 3, `mesh_type`, `strict_tier`
  필드 추가. `EvaluationSummary` 에 `user_decision`, `checker_engine_used`,
  `mesh_type` 추가.
- Orchestrator `run()` 시그니처에 `auto_retry`, `mesh_type` 추가. 기존
  `max_iterations` 는 deprecated (auto_retry=continue 일 때만 사용).
- Planner/TierSelector 가 mesh_type × quality_level 매핑 테이블로 primary tier 와
  같은 카테고리 fallback 순서를 결정.

### Documentation

- `agents/specs/*.md` 5 개 전체를 "라이브러리 참고 → 자체 코드화" 방향으로 재작성.
  각 에이전트에 "현재 의존 / 참고 출처 / 자체 구현 목표" 3-열 로드맵 표 추가.
- `CLAUDE.md` 재편: 핵심 철학 (native-first), mesh_type 3 카테고리, 재시도 루프
  제거, BL 타입별 분기 명시.

### Tests

1108 passed (v0.3.5) → **1328 passed** (v0.4.0-beta), 19 skipped, 0 failed.

신규 테스트 파일:
- `test_native_readers.py` (13)
- `test_native_topology.py` (15)
- `test_native_repair.py` (11)
- `test_native_remesh.py` (9)
- `test_native_bl.py` (8)
- `test_tet_bl_subdivide.py` (5)
- `test_native_tet.py` (4)
- `test_native_hex.py` (5)
- `test_native_poly.py` (4)
- `test_native_checker_parity.py` (6, OpenFOAM 환경에서만)

### Known Limitations (v0.4.0-beta)

- native_poly 는 boundary clipping 미완성 → OpenFOAM checkMesh 에서 open cell
  경고. cells > 0 은 확실하나 CFD quality 는 기존 cfmesh 대비 낮음.
- native_tet 은 surface envelope 유지가 엄격하지 않음 (degenerate sliver tet 일
  부 생성).
- L1 hole_fill 은 다중 loop / 큰 hole 의 winding 일관성이 완벽하지 않음.
- file_reader.py 는 여전히 trimesh 를 기본 경로로 사용 (native readers 는 별도
  경로로 준비된 상태, 통합 전환은 v0.5 예정).

---

## [0.1.0] - 2026-04-01

### Added
- 5-Agent pipeline: Analyzer → Preprocessor → Strategist → Generator ↔ Evaluator
- 2-Phase Progressive meshing: Surface (L1→L2→L3) + Volume (Draft/Standard/Fine)
- QualityLevel system (draft/standard/fine) with differentiated thresholds
- PolyMeshWriter: tet mesh → OpenFOAM polyMesh without external tools
- NativeMeshChecker: OpenFOAM-free mesh quality validation
- Geometry Fidelity: Hausdorff distance-based surface deviation check
- STEP/IGES CAD support via cadquery + gmsh fallback
- CLI: `auto-tessell run input.stl -o ./case --quality draft|standard|fine`
- Rich terminal output with quality report tables
- FastAPI WebSocket server for desktop GUI communication
- Godot 4.3 desktop GUI project (3D mesh viewer, progress tracking)
- OpenFOAM auto-detection (/usr/lib/openfoam/, /opt/, OPENFOAM_DIR)
- Retry strategy with meaningful parameter adjustments on FAIL
- PyInstaller packaging support
- Docker + docker-compose for reproducible builds
- GitHub Actions CI/CD
- 380+ tests (unit + integration + benchmark)

### Supported Input Formats
- Mesh: STL, OBJ, PLY, OFF, 3MF
- CAD: STEP, IGES, BREP
- CFD: Gmsh .msh, VTK/VTU, Fluent .msh, Nastran, Abaqus

### Volume Mesh Engines
- Draft: TetWild (pytetwild) — ~1 second
- Standard: Netgen / cfMesh — ~minutes
- Fine: snappyHexMesh + BL / MMG — ~30 minutes+
