# Changelog

## [0.4.0-beta13] - 2026-04-22 — "poly_bl_transition hybrid pass-through"

### Added

- **`core/layers/poly_bl_transition._classify_cells_by_vertex_count`**: polyMesh
  의 각 cell 을 unique vertex 개수로 분류 (tet=4, prism=6, hex=8, polyhedron=n).
  내부 helper 지만 테스트 가능하도록 public-style.
- **`tests/test_poly_bl_transition.py`** (5 tests): hybrid (prism+tet) 합성
  polyMesh 에 대해 `_try_native_poly_dual` 이 graceful pass-through 하는지 +
  순수 tet 경로가 여전히 dual 변환을 실행하는지 회귀.

### Changed

- `_try_native_poly_dual`: 혼합 mesh (non-tet cell 존재) 입력에서 "실패" 대신
  **graceful pass-through** (원본 hybrid polyMesh 보존). 반환값은 여전히
  `(False, "hybrid mesh preserved — full hybrid dual deferred …")` 로 호출측은
  `bulk_dual_applied=False` 로 기록. 완전한 interface stitching (prism 삼각형
  ↔ dual 폴리곤 정합) 은 beta15+ 로드맵.

---

## [0.4.0-beta14] - 2026-04-22 — "Qt e2e + README beta12 동기화"

### Added

- **`tests/test_qt_app.py::test_qt_pipeline_native_tet_e2e`**: AutoTessellWindow
  (set_mesh_type=tet) + PipelineWorker(tier=native_tet, prefer_native=True) 가
  PipelineOrchestrator.run() 을 올바른 인자로 호출하는지 headless 에서 검증.
  orchestrator 는 monkeypatch stub.

### Changed

- README.md "자체 코드화 진행" 표를 beta12 기준으로 갱신 (Hausdorff / inside-
  winding / tier wrapper / generic polyMesh writer 행 추가). bench matrix
  30/30 으로 갱신. Harness 패턴 설명 블록 추가.

---

## [0.4.0-beta12] - 2026-04-22 — "PolyMeshGenericWriter 통합"

### Added

- **`core/generator/polymesh_writer.write_generic_polymesh`**: 임의 cell
  (tet/hex/poly 공용) 의 외향 face vertex 리스트를 받아 face dedup +
  owner/neighbour 정렬 + FoamFile 쓰기를 일원화하는 범용 writer.

### Changed

- `PolyMeshWriter.write()` (tet 전용) 는 normalize_tet_winding 후 cell_faces 를
  만들어 generic writer 에 위임하는 얇은 wrapper 로 축소.
- `native_hex/mesher._write_polymesh_hex` / `native_poly/voronoi._write_polymesh_poly`
  도 각자 cell_faces 를 만들어 generic writer 위임. 약 150 라인 중복 제거.
- `core/layers/native_bl._write_labels()` 에 optional `note` kwarg 추가 → owner
  파일에 `nPoints/nCells/nFaces/nInternalFaces` 주석 복구. Ofpp 파서 호환 회복.
- native_bl FoamFile 헤더에 OpenFOAM 표준 preamble(`/*---*/`) + footer separator
  삽입 → 외부 도구 호환성 향상.

---

## [0.4.0-beta11] - 2026-04-22 — "Hausdorff 자체 구현"

### Changed

- `core/evaluator/fidelity._compute_hausdorff`: `trimesh.sample.sample_surface`
  와 `scipy.spatial.cKDTree` 의존 제거. 자체 `_native_sample_surface` (면적 가중
  barycentric sampling, numpy RNG seed 고정) + `_native_kdist_chunked` (brute-
  force chunked kNN, pair_limit=1e7) 로 교체. 실패 시 기존 trimesh+scipy 경로
  로 graceful fallback 유지.

---

## [0.4.0-beta10] - 2026-04-22 — "tier_native_* DRY"

### Added

- **`core/generator/_tier_native_common.run_native_tier`**: STL read +
  target_edge 파싱 + TierAttempt 조립을 공통화한 공용 entry.

### Changed

- `tier_native_tet.py` / `tier_native_hex.py` / `tier_native_poly.py` 각 Generator
  의 `run()` 메서드가 `run_native_tier(...)` 한 줄 호출로 축약. seed_density 등
  엔진별 기본값은 runner_fn / extra_kwargs 로 전달.

---

## [0.4.0-beta9] - 2026-04-22 — "inside_winding_number 공용화"

### Added

- **`core/utils/geometry.inside_winding_number`**: Möller-Trumbore ray-triangle
  intersection + y/z bbox prefilter 로 3D point-in-mesh 테스트. native_tet 의
  검증된 구현을 추출해 3 엔진 공용 모듈로 승격.

### Changed

- `core/generator/native_tet/mesher.py` / `native_hex/mesher.py` /
  `native_poly/voronoi.py` 의 로컬 `_inside_winding_number` / `_inside_ray_cast`
  구현을 삭제하고 `core.utils.geometry.inside_winding_number` import 로 교체.
  cell 수 drift 0 (tet=1196, hex=136, poly=26 on sphere baseline 불변).

---

## [0.4.0-beta8] - 2026-04-22 — "harness 확장 + 성능 안정화"

### Added

- **`core/generator/native_tet/harness.py`** (`run_native_tet_harness`):
  native_tet Generator ↔ Evaluator 반복으로 non_ortho 개선. sphere 에서 iter=1
  PASS, non_ortho 81.2° → **76.8°** (draft 임계 < 80 통과).
- `tier_native_tet` 이 harness 기본 경로로 전환 (실패 시 기본 generate_native_tet
  fallback).

### Fixed

- native_poly harness 에 **max_tet_cells cap** (default 30000): target_edge_length
  가 Strategist 에서 매우 작게 전달될 경우 tet mesh 가 121k cells 로 폭증 → dual
  변환 이 timeout 되는 문제 해결. bbox_diag/50 하한 + cell 수 초과 시 target_edge
  1.6×, seed 0.6× 로 재조정.
- CLI 에서 `--tier native_poly` 로 easy_cube 실행 시 300s+ timeout → **30s 이하**
  로 완주.

---

## [0.4.0-beta7] - 2026-04-22 — "poly mesh 자체 완성 + harness 패턴"

### Added — poly mesh 완성 (OpenFOAM 의존 제거)

- **`core/generator/native_poly/dual.py`**: tet→polyhedral dual 변환 자체 구현.
  OpenFOAM `polyDualMesh` 를 대체. 각 input vertex 주위의 tet centroid +
  boundary face midpoint 로 dual cell 구성 + scipy ConvexHull 로 polyhedron +
  coplanar triangle 병합 → polygon face + SVD plane basis + CCW sort + cell
  centroid 기준 winding 보정.
- **`core/generator/native_poly/harness.py`**: NativePolyHarness — Generator
  (native_tet → tet_to_poly_dual) ↔ Evaluator (NativeMeshChecker) 반복.
  FAIL 시 seed_density 1.5× 증가 후 최대 3 iter. sphere 에서 iter=1 에 PASS
  (698 polyhedra, negative_volumes=0, skewness 0.22, mesh_ok=True).
- **`core/layers/poly_bl_transition.py`**: OpenFOAM `polyDualMesh` 호출을 자체
  `_try_native_poly_dual` 로 교체 (순수 tet 입력 지원).
- **`core/generator/tier_native_poly.py`**: harness 경로 기본화, scipy Voronoi
  는 fallback.

### Tests
- **`tests/test_native_poly_dual.py`** (5 tests):
  - tet_to_poly_dual 이 sphere 에서 polyMesh 5 파일 생성.
  - NativeMeshChecker 로 negative_volumes=0 확인.
  - harness 가 1-3 iter 안에 PASS.
  - 빈 입력 fail.
  - polyMesh 포맷 호환 (reader 로 재읽기 가능).

### Native vs OpenFOAM parity
- **sphere (seed=10)**: native harness 결과 = 698 polyhedral cells,
  max_non_ortho 87°, skewness 0.22, **negative_volumes=0, mesh_ok=True**.
- 이전 `scipy Voronoi 기반 voronoi.py` 는 `open_cells=52/52` 였던 것과 비교해
  topology 품질이 크게 향상 (dual 경로는 input mesh 위상을 보존).

### Bench v0.4.0-beta7 matrix (5 난이도 × 3 엔진 × draft+standard)
```
| STL             | native_tet (d/s)       | native_hex (d/s)            | native_poly (d/s)      |
|-----------------|------------------------|-----------------------------|------------------------|
| 01_easy_cube    | ✓ 174s PASS / ✓ 265s   | ✓ 37s PASS / ✓ 36s          | ✗ 300s TO / ✗ 300s TO  |
| 02_cylinder     | ✓ 36s / ✓ 186s         | ✓ 10s PASS / ✓ 30s PASS     | ✓ 226s / ✗ 300s TO     |
| 03_bracket      | ✓ 4s PASS / ✓ 22s      | ✓ 3s PASS / ✓ 7s PASS       | ✓ 22s / ✓ 137s         |
| 04_gear         | ✓ 13s / ✓ 34s          | ✓ 5s PASS / ✓ 8s PASS       | ✓ 74s / ✓ 215s         |
| 05_ultra_knot   | ✓ 13s / ✓ 23s          | ✓ 5s PASS / ✓ 7s PASS       | ✓ 94s / ✓ 149s         |
```
**30 중 27 polyMesh 생성 (90%)**. native_hex 는 10/10 Evaluator PASS. native_poly
는 harness 가 dual 변환을 포함해 느림 — easy_cube 등 일부 timeout. 향후 dual
변환 ConvexHull 최적화 또는 seed grid 캐싱으로 해결 가능.

회귀: 1336 → **1341 passed** (+5 native_poly_dual 테스트).

---

## [0.4.0-beta3] - 2026-04-22 — "Native-First" 후속 개선

### Added
- **poly_bl_transition** (`core/layers/poly_bl_transition.py`): mesh_type=poly
  용 BL. native_bl 로 prism 삽입 후 (옵션) OpenFOAM polyDualMesh 로 bulk tet
  을 polyhedral dual 로 변환. sphere 에서 2783 polyhedral cells, Skewness OK.
- **L1 hole_fill ear-clipping** (`core/preprocessor/native_repair/hole_fill.py`):
  fan triangulation 대신 boundary loop 의 평균 평면 basis + 2D ear-clipping.
  max_boundary 64 → 128, 큰 hole / non-convex 영역도 처리.
- **file_reader.py native-first**: STL/OBJ/PLY/OFF 는 자체 `core/analyzer/readers/`
  로 기본 로드, trimesh 는 자동 fallback. `loaded_via_native_reader` 로그 기록.
- **Qt GUI 재시도 다이얼로그**: Evaluator FAIL + auto_retry=off 시 QMessageBox
  로 "재시도 / 수락" 묻고, 재시도 선택 시 동일 설정으로 파이프라인 재실행.
- **tests/stl/bench_v04_matrix.py**: 5 난이도 × native_tet/hex/poly 매트릭스
  실행 스크립트. 결과는 `bench_v04_result.json` 으로 저장.

### v0.4 Bench Matrix 결과 (5 난이도 × 3 native 엔진 × draft+standard)

**beta4+ (standard quality 확장 — 30 조합):**
```
| STL                      | native_tet           | native_hex           | native_poly         |
|                          | draft    | standard  | draft    | standard  | draft   | standard  |
|--------------------------|----------|-----------|----------|-----------|---------|-----------|
| 01_easy_cube             | ✓ 168s   | ✓ 268s    | ✓ 37s OK | ✓ 36s OK  | ✓ 50s   | ✓ 50s     |
| 02_medium_cylinder       | ✓ 35s    | ✓ 189s    | ✓ 11s OK | ✓ 30s OK  | ✓ 59s   | ✓ 59s     |
| 03_hard_bracket          | ✓ 4s     | ✓ 22s     | ✓ 3s OK  | ✓ 7s OK   | ✓ 6s    | ✓ 15s     |
| 04_extreme_gear          | ✓ 13s    | ✓ 35s     | ✓ 5s OK  | ✓ 8s OK   | ✓ 13s   | ✓ 27s     |
| 05_ultra_knot            | ✓ 13s    | ✓ 23s     | ✓ 5s OK  | ✓ 7s OK   | ✓ 224s  | ✓ 263s    |
```
**30/30 polyMesh 생성 성공 (100%)**. native_hex 는 draft+standard 둘 다 모두
Evaluator PASS (rc=0). native_tet/poly 는 polyMesh 는 생성되나 품질 판정 FAIL
(향후 개선 대상).

**beta3 최종 (inside-test AABB prefilter 적용 후):**
```
| STL                      | native_tet  | native_hex  | native_poly |
|--------------------------|-------------|-------------|-------------|
| 01_easy_cube             | ✓ 170s      | ✓ 33s OK    | ✓ 49s       |
| 02_medium_cylinder       | ✓ 36s       | ✓ 11s OK    | ✓ 52s       |
| 03_hard_bracket          | ✓ 4s        | ✓ 3s OK     | ✓ 5s        |
| 04_extreme_gear          | ✓ 13s       | ✓ 6s OK     | ✓ 11s       |
| 05_ultra_knot            | ✓ 13s       | ✓ 179s OK   | ✓ 125s      |
```
총 15 조합 중 **15 polyMesh 생성 성공 (100%)**. native_hex 는 5/5 Evaluator PASS.
ultra_knot native_tet 이전 300s timeout → 13s 완주 (inside-test 23× 가속).

### Fixed
- native_tet 의 sliver tet 제거 (q = 8.48·V/edge_max³ < 0.02 탈락). sphere 에서
  negative volume 5 → 0, Mesh OK.
- native_bl per-vertex local collision safety: wall vertex 별 인접 cell 중심까지
  거리 × 0.8 을 local cap 으로 사용. 극점 sliver prism 제거.

### Changed
- Preprocessor `--prefer-native` opt-in: pymeshfix 없이 자체 native_repair 경로
  로 L1 수행. `pyproject.toml` 의 pymeshfix/pyacvd/pymeshlab 을
  `legacy-preprocess` extras 로 격하.

---

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
