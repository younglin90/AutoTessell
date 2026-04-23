# Auto-Tessell

CAD/메쉬 파일 → OpenFOAM polyMesh 자동 생성 도구.
**v0.4 "Native-First"**: 외부 라이브러리 의존 → 자체 코드 점진 전환. 라이브러리는
참고·카피 대상이지 의존 대상이 아님.

## v0.4 신규 사용법

```bash
# 메쉬 타입 3 카테고리 (tet / hex_dominant / poly)
auto-tessell run input.stl -o ./case --mesh-type tet --quality draft
auto-tessell run input.stl -o ./case --mesh-type hex_dominant --quality fine   # + BL
auto-tessell run input.stl -o ./case --mesh-type poly --quality standard

# 자체 native 엔진 직접 호출 (OpenFOAM / trimesh / pymeshfix 없이)
auto-tessell run input.stl -o ./case --tier native_tet --quality draft
auto-tessell run input.stl -o ./case --tier native_hex --quality standard
auto-tessell run input.stl -o ./case --tier native_poly

# 자동 재시도 off (기본, FAIL 시 사용자 y/N prompt)
auto-tessell run input.stl -o ./case --auto-retry off

# L1/L2 수리/리메쉬 native 경로 (pymeshfix/pyACVD/pymeshlab 없이)
auto-tessell run input.stl -o ./case --prefer-native

# NativeMeshChecker 기본 (OpenFOAM 불필요)
auto-tessell run input.stl -o ./case --checker-engine native
```

## 자체 코드화 진행 (v0.4.0-beta29)

| 영역 | 기본 경로 | legacy fallback |
|------|-----------|-----------------|
| STL/OBJ/PLY/OFF reader | `core/analyzer/readers/` native | trimesh |
| Topology | `core/analyzer/topology.py` native (trimesh 완전 제거 @beta15) | — |
| MeshChecker | `NativeMeshChecker` 기본 | OpenFOAM checkMesh (명시 시) |
| L1 repair | **기본 native** (`--legacy-repair` 로 opt-out @beta26) | pymeshfix/trimesh |
| L2 remesh | `--prefer-native` → isotropic + CVT | pyACVD/pymeshlab |
| BL 생성 (hex) | `native_bl` Phase 2 polyMesh 직접 | cfMesh/snappy |
| BL 생성 (tet) | `tet_bl_subdivide` prism → 3 tet 분할, 순수 tet | - |
| BL 생성 (poly) | `poly_bl_transition` + best-effort hybrid dual @beta25 | - |
| Volume 엔진 | `native_tet/hex/poly` (+harness) | 17 legacy Tier |
| Strategist tier 매핑 | `--prefer-native-tier` 로 native_* primary @beta23 | legacy primary |
| BL 기본 활성화 | fine quality → mesh_type 별 BL 자동 @beta24 | `--bl-layers N` 명시 |
| Hausdorff 거리 | `fidelity._native_sample_surface` + chunked kNN | trimesh.sample/scipy.cKDTree |
| inside-test | `core/utils/geometry.inside_winding_number` 공용 | — |
| Tier wrapper | `core/generator/_tier_native_common.run_native_tier` 공용 | — |
| polyMesh writer | `polymesh_writer.write_generic_polymesh` 공용 | — |
| KDTree | `core/utils/kdtree.NumpyKDTree` @beta28 | scipy.cKDTree (fidelity fallback 만) |
| HARNESS_PARAMS | tier × quality × {seed_density, max_iter, snap_boundary} @beta17 | — |

### mesh_type × BL 파이프라인 (v0.4.0-beta27)

| mesh_type | 볼륨 엔진 (native) | BL 엔진 | 특징 |
|-----------|---------------------|---------|------|
| `tet` | `native_tet` (harness) | `tet_bl_subdivide` | 순수 tet 유지 (wedge → 3 tet) |
| `hex_dominant` | `native_hex` (+ surface snap @ fine) | `native_bl` | prism wedge, OpenFOAM checkMesh OK |
| `poly` | `native_poly` (tet→poly dual) | `poly_bl_transition` | hybrid (prism+tet) best-effort dual |

**Bench matrix (5 난이도 × 3 native 엔진 × 2 quality = 30 조합):** 30/30 polyMesh 생성.
세부는 `tests/stl/bench_v04_result.json` + timestamped snapshots. 진화 이력은
`CHANGELOG.md`.

**Harness 패턴 (v0.4.0-beta6~)**: Generator ⇄ Evaluator (NativeMeshChecker) 반복.
safety cap (`max_tet_cells`, target_edge clamp) 로 cell 폭증 방지. 자세한 내용은
`core/generator/native_{tet,poly}/harness.py` 참조.

### scipy 잔존 (v0.5+ 로드맵)

v0.4 에서 의도적으로 유지하는 scipy 의존:
- `scipy.spatial.Delaunay` (native_tet 코어) — incremental Bowyer-Watson 자체
  구현은 v0.5.
- `scipy.spatial.Voronoi` (native_poly voronoi fallback) — dual of Delaunay.
- `scipy.spatial.ConvexHull` (native_poly dual cell polyhedron) — QuickHull 이식.
- `scipy.spatial.cKDTree` (evaluator/fidelity.py legacy fallback 경로만) — 기본
  경로는 `NumpyKDTree` @beta28.

scipy 는 "수치 toolkit" 범주로 허용 (trimesh/pymeshfix 같은 mesh-specific
라이브러리와 구분). 자체 구현은 beta32+ 연구 phase.

## 외부 라이브러리 정리

`pyproject.toml` 의 `legacy-preprocess` extras 로 이동 (기본 미설치):
- `pymeshfix` / `pyacvd` / `pymeshlab`

`--prefer-native` + `--checker-engine native` + `--tier native_*` 로 위 legacy
라이브러리 없이도 전체 파이프라인 완주 가능.

## 현재 기준선 (Primary Track)

- **Primary Track**: `core + cli` (메인 제품 경로)
- **Desktop**: Godot + `desktop.server` 운용, Qt는 프로토타입 병행
- **Web SaaS**: `backend + frontend`는 데모/검증 경로
- **버전 기준**: `1.0.0`

관련 문서:

- `CURRENT_STATUS_AND_BACKLOG.md`
- `TRACK_OWNERSHIP.md`
- `OWNERSHIP_DECISIONS.md`
- `RELEASE_CHECKLIST.md`
- `TEST_COUNTING_POLICY.md`

```bash
auto-tessell run model.stl -o ./case --quality draft      # ~1초, 빠른 검증
auto-tessell run model.stl -o ./case --quality standard    # ~수분, 엔지니어링
auto-tessell run model.step -o ./case --quality fine        # ~30분+, 최종 CFD
auto-tessell doctor                                          # 런타임 의존성 설치/미설치 표
```

## 주요 기능

- **2-Phase Progressive 파이프라인**: 표면 메쉬(L1→L2→L3) + 볼륨 메쉬(Draft→Standard→Fine)
- **5-Agent 아키텍처**: Analyzer → Preprocessor → Strategist → Generator ↔ Evaluator
- **Windows 네이티브 지원**: OpenFOAM 없이도 메쉬 생성 + 품질 검증 가능
- **다양한 입력 포맷**: STL, OBJ, PLY, STEP, IGES, BREP, Gmsh .msh, VTK 등
- **자동 품질 검증**: NativeMeshChecker + Hausdorff 거리 기반 표면 충실도
- **데스크톱 경로**: Godot + `desktop.server` (현재), Qt 프로토타입 병행
- **테스트 스위트**: 단위 + 통합 + 벤치마크

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

# 2. Godot에서 godot/project.godot 열기
# 3. F5 (Play) → 파일 선택 → 메쉬 생성
```

### 데스크톱 GUI (Qt, 빠른 로컬 테스트)

```bash
# Qt 의존성 포함 설치
pip install -e ".[desktop]"

# 실행 (둘 중 하나)
auto-tessell-qt
python -m desktop.qt_main
```

Qt GUI에서 아래 파라미터를 사용자가 직접 조정할 수 있습니다.
- `Element Size` (전체 셀 크기 오버라이드)
- `Max Cells` (최대 셀 수 제한)
- `Snappy Tol` (`snappy_snap_tolerance`)
- `Snappy Iter` (`snappy_snap_iterations`)
- `Snappy Level` (`snappy_castellated_level`, `min,max`)
- `TetWild Eps` (`tetwild_epsilon`)
- `TetWild Energy` (`tetwild_stop_energy`)
- `cfMesh MaxCell` (`cfmesh_max_cell_size`)
- `No Repair` (`no_repair`)
- `Force Surface Remesh` (`surface_remesh`)
- `Remesh Engine` (`remesh_engine`: `auto|mmg|quadwild`)
- `Allow AI Fallback` (`allow_ai_fallback`)
- `Extra Tier Params (JSON)` (임의 `tier_specific_params` 키/값 직접 주입)

모든 파라미터 옆 `?` 버튼을 누르면 의미/용도 설명 팝업이 표시됩니다.
또한 `Advanced Tier Params` 패널에서 core/netgen/snappy/tetwild/mmg/meshpy/jigsaw 관련 세부 키를 직접 조정할 수 있습니다.

### 헤드리스 Linux에서 Qt 화면 보기 (Xvfb + VNC)

```bash
# 런타임 도구 설치 (Ubuntu/Debian)
sudo apt install -y xvfb x11vnc

# 오프스크린 스모크 체크
make gui-offscreen-smoke

# 가상 디스플레이 + VNC로 실행
make gui-headless
```

`make gui-headless` 실행 후 VNC 클라이언트로 `127.0.0.1:5900`에 접속하면 Qt 창을 볼 수 있습니다.

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

### 엔진 자동 선택 규칙 (코드 기준)

- `--tier`를 명시하면 자동 선택을 건너뛰고 해당 tier를 고정한다.
- 표면 품질이 `l3_ai`이면 `tier2_tetwild`를 강제한다.
- `draft`: `tier2_tetwild` 우선, fallback은 `tier05_netgen`.
- `standard`:
`CAD B-Rep -> tier05_netgen`, `external+watertight -> tier1_snappy`,
`internal+watertight -> tier15_cfmesh`, `watertight+simple -> tier0_core`, 그 외 `tier2_tetwild`.
- `fine`:
`CAD B-Rep -> tier05_netgen`, `external+watertight -> tier1_snappy`,
`watertight -> tier15_cfmesh`, 그 외 `tier2_tetwild`.
- 자동 선택 결과는 `mesh_strategy.json`의 `tier_specific_params.engine_selection`과 로그(`tier_auto_selected`, `strategy_planned`)에 기록된다.

### `--max-cells` 동작

- `--max-cells`는 `base_cell_size`를 자동 확대해 셀 수 상한을 강제한다.
- 상한 cap은 OpenFOAM `label` 크기(Int32/Int64)와 `quality`에 따라 자동 적용된다.
- 요청값이 cap을 넘으면 CLI에서 `max_cells clamp` 경고를 출력한다.

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

# 문서 기준선/테스트 수 점검
make checks-strict
make smoke-check

# 필수 안전장치 회귀 세트 (빠른 로컬 게이트)
make safeguard-regression

# 메쉬 엔진 조합 스모크 매트릭스 (quality x tier)
make qa-matrix-mini
# 결과: reports/mini_matrix_results.json, reports/mini_matrix_summary.json

# 타임아웃 완화 fast 프로파일 매트릭스
make qa-matrix-mini-fast
# 결과: reports/mini_matrix_fast_results.json, reports/mini_matrix_fast_summary.json

# 전체 조합 매트릭스 (quality x tier x remesh_engine)
make qa-matrix-full-cube
# 결과: reports/full_matrix_results.json, reports/full_matrix_summary.json

# fine 전용 fast 매트릭스 (tier별 timeout/fail 진단)
make qa-matrix-fine-fast
# 결과: reports/fast_fine_tiers_auto_remesh_results.json, reports/fast_fine_tiers_auto_remesh_summary.json
# 참고: fine fast 타겟은 tier별 max-iterations override(auto=2, netgen=2, tetwild=3)를 포함
```

CI note: baseline strict checks are centralized in
`.github/workflows/common-checks.yml` and reused by test/release flows.

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
├── godot/                  # Godot GUI
├── tests/                  # 테스트 스위트
└── agents/specs/           # 에이전트 스펙 문서
```

## 라이선스

**Auto-Tessell** 자체는 **MIT 라이선스**로 배포됩니다 (연구·오픈소스 목적).

### 의존 라이브러리 라이선스

| 라이브러리 | 라이선스 | 연구/오픈소스 |
|-----------|---------|-------------|
| trimesh, pyACVD, pymeshfix | MIT/BSD | ✅ |
| TetWild (pytetwild) | MPL-2.0 | ✅ |
| Netgen | LGPL-2.1 | ✅ |
| OpenFOAM | GPL-2.0+ | ✅ |
| MMG | LGPL-3.0 | ✅ |
| Godot | MIT | ✅ |
| meshgpt-pytorch | MIT | ✅ |
| MeshAnythingV2 | S-Lab 1.0 | ✅ (비상업 연구 한정) |

> **주의:** MeshAnythingV2 (L3 AI 표면 수리)는 비상업 연구 목적으로만 사용 가능합니다.
> 상업적 사용 시 원저자의 별도 허가가 필요합니다.
