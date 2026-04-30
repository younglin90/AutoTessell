# Auto-Tessell CLI Reference (auto-generated)

Total commands: 16

| Command | Description (1-line) | # Options |
|---------|---------------------|-----------|
| `analyze` | 입력 파일을 분석하고 geometry_report.json을 생성한다. | 2 |
| `convert` | beta2278 — Direct mesh format conversion (meshio-style). | 0 |
| `doctor` | 런타임 의존성 탐지 결과(설치/미설치/선택)를 표로 출력한다. | 0 |
| `evaluate` | 생성된 메쉬 품질을 검증하고 quality_report.json을 생성한다. | 6 |
| `export` | 생성된 메쉬를 CFD/FEA/시각화 포맷으로 내보낸다. | 2 |
| `export-native` | N2 / beta2654 — 자체 native writer 12 포맷 직접 dispatch. | 2 |
| `export-vtk` | 생성된 메쉬를 VTK (.vtu) 포맷으로 내보낸다. ParaView에서 품질 컬러맵 시각화 가능. | 2 |
| `generate` | mesh_strategy.json에 따라 메쉬를 생성하고 polyMesh를 출력한다. | 5 |
| `interactive` | 대화형 모드 — 각 단계를 확인하며 진행한다. | 1 |
| `list-tiers` | N6 / beta2658 — 등록된 모든 Tier + alias 표시. | 0 |
| `mesh-info` | L2 / beta2641 — polyMesh 종합 info (topology + 선택적 histogram). | 1 |
| `preprocess` | 표면 수리, 포맷 변환, 리메쉬를 수행하고 preprocessed.stl을 생성한다. | 8 |
| `run` | 전체 파이프라인(Analyze→Preprocess→Strategize→Generate→Evaluate)을 실행한다. | 72 |
| `smoketest` | beta2276 — Installation smoke test. 단순 cube → 메쉬 + BL → 검증. | 1 |
| `stats` | beta2279 — Mesh quality stats report (commercial-grade table). | 0 |
| `strategize` | 메쉬 생성 전략(mesh_strategy.json)을 수립한다. | 7 |

## `analyze`

입력 파일을 분석하고 geometry_report.json을 생성한다.

| Option | Type | Default | Help |
|--------|------|---------|------|
| `--output` / `-o` | <click.types.Path object at 0x | — | geometry_report.json 저장 경로 (기본: <input>.geometry_report.json) |
| `--dry-run` | BOOL | False | 분석만 수행, 파일 저장 없음 |

## `evaluate`

생성된 메쉬 품질을 검증하고 quality_report.json을 생성한다.

| Option | Type | Default | Help |
|--------|------|---------|------|
| `--case` | <click.types.Path object at 0x | Sentinel.UNSET |  |
| `--geometry-report` | <click.types.Path object at 0x | Sentinel.UNSET |  |
| `--generator-log` | <click.types.Path object at 0x | — |  |
| `--strategy` | <click.types.Path object at 0x | — |  |
| `--iteration` | INT | 1 |  |
| `--output` / `-o` | <click.types.Path object at 0x | — | quality_report.json 저장 경로 (기본: <case>/quality_report.json) |

## `export`

생성된 메쉬를 CFD/FEA/시각화 포맷으로 내보낸다.

    지원 포맷 (17 종, commercial-grade):
      - CFD volume: SU2, Fluent (.msh), CGNS, VTU, VTK, VTP, XDMF
      - Mesh: Gmsh 2.2/4.0/4.1, Medit, Tecplot
      - FEA: Nastran (.bdf), Abaqus (.inp)
      - Surface: STL, OBJ, PLY

    예시::

        auto-tessell export ./case -o mesh.vtu       # auto-detect VTU
        auto-tessell export ./case -f stl -o s.stl   # explicit STL
        auto-tessell export ./case -f abaqus         # default path

| Option | Type | Default | Help |
|--------|------|---------|------|
| `--format` / `-f` | Choice(['su2', 'fluent', 'cgns | — | 출력 포맷. 미지정 시 --output 확장자로 자동 감지. |
| `--output` / `-o` | <click.types.Path object at 0x | — | 출력 파일 경로 (기본: <case_dir>/mesh.<ext>) |

## `export-native`

N2 / beta2654 — 자체 native writer 12 포맷 직접 dispatch.

    기존 export 와 별개 — 내장 raw writer 사용 (meshio 의존 없음).

    예시::

        auto-tessell export-native ./case -f vtu-binary -o mesh.vtu
        auto-tessell export-native ./case -f starccm-ccmio -o mesh.ccm
        auto-tessell export-native ./case -f nastran-bdf -o mesh.bdf

| Option | Type | Default | Help |
|--------|------|---------|------|
| `--format` / `-f` | Choice(['vtu', 'vtu-binary', ' | Sentinel.UNSET | N2 / beta2654 — AutoTessell 자체 native writer 12 포맷. |
| `--output` / `-o` | <click.types.Path object at 0x | Sentinel.UNSET |  |

## `export-vtk`

생성된 메쉬를 VTK (.vtu) 포맷으로 내보낸다. ParaView에서 품질 컬러맵 시각화 가능.

| Option | Type | Default | Help |
|--------|------|---------|------|
| `--output` / `-o` | <click.types.Path object at 0x | — |  |
| `--no-quality` | BOOL | False | 품질 필드 제외 |

## `generate`

mesh_strategy.json에 따라 메쉬를 생성하고 polyMesh를 출력한다.

| Option | Type | Default | Help |
|--------|------|---------|------|
| `--strategy` | <click.types.Path object at 0x | Sentinel.UNSET |  |
| `--preprocessed` | <click.types.Path object at 0x | — | 전처리된 STL/CAD 파일 경로 (기본: strategy의 surface_mesh.input_file) |
| `--tier` | STRING | — | Tier 강제 지정 (strategy.selected_tier 무시). 선택: core, netgen, snappy, cfmesh, tetwil |
| `--quality` | Choice(['draft', 'standard', ' | — | 품질 레벨 재정의 (strategy.quality_level 무시) |
| `--output` / `-o` | <click.types.Path object at 0x | case |  |

## `interactive`

대화형 모드 — 각 단계를 확인하며 진행한다.

| Option | Type | Default | Help |
|--------|------|---------|------|
| `--output` / `-o` | <click.types.Path object at 0x | case |  |

## `mesh-info`

L2 / beta2641 — polyMesh 종합 info (topology + 선택적 histogram).

    예시:
        auto-tessell mesh-info ./case
        auto-tessell mesh-info ./case --histogram

| Option | Type | Default | Help |
|--------|------|---------|------|
| `--histogram` | BOOL | False | quality histogram 표시 |

## `preprocess`

표면 수리, 포맷 변환, 리메쉬를 수행하고 preprocessed.stl을 생성한다.

| Option | Type | Default | Help |
|--------|------|---------|------|
| `--geometry-report` | <click.types.Path object at 0x | — |  |
| `--output` / `-o` | <click.types.Path object at 0x | — |  |
| `--tier` | STRING | — | Tier 힌트 (netgen이면 CAD 패스스루) |
| `--no-repair` | BOOL | False |  |
| `--force-repair` | BOOL | False |  |
| `--surface-remesh` | BOOL | False |  |
| `--remesh-target-faces` | INT | — |  |
| `--allow-ai-fallback` | BOOL | False | L3 AI 표면 재생성 허용 (GPU 필요) |

## `run`

전체 파이프라인(Analyze→Preprocess→Strategize→Generate→Evaluate)을 실행한다.

| Option | Type | Default | Help |
|--------|------|---------|------|
| `--output` / `-o` | <click.types.Path object at 0x | case |  |
| `--tier` | Choice(['auto', 'core', 'netge | auto | 볼륨 메쉬 엔진 (auto=품질레벨에 따라 자동) |
| `--quality` | Choice(['draft', 'standard', ' | standard | 품질 레벨 (draft=빠른검증 / standard=엔지니어링 / fine=최종CFD) |
| `--repair-engine` | Choice(['auto', 'pymeshfix', ' | auto | L1 표면 수리 라이브러리 |
| `--remesh-engine` | Choice(['auto', 'quadwild', 'v | auto | L2 표면 리메쉬 라이브러리 (vorpalite=geogram, 최고 품질) |
| `--volume-engine` | Choice(['auto', 'tetwild', 'ne | auto | 볼륨 메쉬 엔진 (--tier와 동일, 더 명시적 이름) |
| `--checker-engine` | Choice(['auto', 'openfoam', 'n | auto | 품질 검증 엔진. v0.4 이후 auto=NativeMeshChecker 기본 (openfoam 명시 시에만 OpenFOAM checkMesh  |
| `--cad-engine` | Choice(['auto', 'cadquery', 'g | auto | CAD 파일(STEP/IGES) 변환 라이브러리 |
| `--postprocess-engine` | Choice(['auto', 'mmg', 'none'] | auto | 볼륨 메쉬 후처리 (mmg=MMG3D 품질 개선) |
| `--element-size` | FLOAT | — | 표면 셀 크기 override [m] |
| `--base-cell-size` | FLOAT | — | 배경 셀 크기 override [m] |
| `--min-cell-size` | FLOAT | — | 최소 셀 크기 override [m] |
| `--base-cell-num` | INT | — | 특성길이 대비 분할 수 (기본: 50, 작을수록 거친 메쉬) |
| `--domain-upstream` | FLOAT | — | 업스트림 배수 (기본: draft=3, std=5, fine=10) |
| `--domain-downstream` | FLOAT | — | 다운스트림 배수 (기본: draft=5, std=10, fine=20) |
| `--domain-lateral` | FLOAT | — | 측면 배수 (기본: draft=2, std=3, fine=5) |
| `--domain-scale` | FLOAT | 1.0 | 도메인 전체 스케일 팩터 |
| `--max-cells` | <IntRange x>=1> | — | 최대 셀 수 제한 (초과 시 셀 크기 자동 확대) |
| `--bl-layers` | INT | — | BL 레이어 수 (0=비활성) |
| `--bl-first-height` | FLOAT | — | 첫 번째 BL 높이 [m]. --target-yplus 와 함께 쓰면 자동 계산값 override. |
| `--fluid` | Choice(['air', 'water', 'oil', | air | 유체 종류 — y⁺ 자동 계산 시 동점성 계수 조회 기준. |
| `--target-yplus` | FLOAT | — | 목표 y⁺ 값 (예: 1.0 = low-Re, 30 = 벽함수). 지정 시 --flow-velocity + geometry bbox 로 첫 BL |
| `--kinematic-viscosity` | FLOAT | — | 직접 동점성 계수 지정 [m²/s]. --fluid 무시됨. |
| `--bl-growth-ratio` | FLOAT | — | BL 성장비 (기본: 1.2) |
| `--no-repair` | BOOL | False | 표면 수리 건너뛰기 |
| `--force-remesh` | BOOL | False | L2 리메쉬 강제 실행 |
| `--remesh-target-faces` | INT | — | 리메쉬 목표 삼각형 수 |
| `--allow-ai-fallback` | BOOL | False | L3 AI 표면 재생성 허용 (GPU 필요) |
| `--strict-tier` | BOOL | False | 명시 tier(auto 아님)에서 fallback tier 비활성화 |
| `--tetwild-epsilon` | FLOAT | — | TetWild epsilon (draft=0.02, std=0.001) |
| `--tetwild-stop-energy` | FLOAT | — | TetWild stop energy (draft=20, std=10) |
| `--snappy-castellated-level` | STRING | — | castellated refinement [min,max] (예: 2,3) |
| `--snappy-snap-tolerance` | FLOAT | — | snap tolerance (기본: 2.0) |
| `--snappy-snap-iterations` | INT | — | snap solve iterations (기본: 5) |
| `--tier-param` | STRING | Sentinel.UNSET | generic tier 파라미터 override (반복 가능, 예: --tier-param seed_density=20 --tier-param  |
| `--mesh-type` | Choice(['auto', 'tet', 'hex_do | auto | 메쉬 타입 (v0.4 신규): tet / hex_dominant / poly. auto=Strategist 가 quality/geometry 기 |
| `--prefer-native` | BOOL | True | v0.4.0-beta26+ 기본 True. Preprocessor L1 을 자체 native_repair 로 수행. --legacy-repair |
| `--prefer-native-tier` | BOOL | False | v0.4.0-beta23+ native-first tier: Strategist 가 native_tet/hex/poly 를 primary 로 선 |
| `--cross-engine-fallback` | BOOL | False | v0.4.0-beta68+ poly mesh_type 이 완전 실패하면 hex_dominant 로 1회 자동 재시도. 실패 시 결과 error  |
| `--enable-vvv9h-apply` | BOOL | False | beta2319 fix + beta2344 — Klingner 2008 §3.5 edge-contract real apply 활성. 환경변수 A |
| `--enable-offplane-steiner` | BOOL | False | beta2318 + beta2344 — Klingner-Shewchuk 2008 §4.1 off-plane Steiner exudation re |
| `--enable-vvv9j-apply` | BOOL | False | beta2346 — VVV9J SLIM global-pass real apply (smoothing 강화). 환경변수 AUTO_TESSELL_V |
| `--enable-vvv9k-apply` | BOOL | False | beta2346 — VVV9K priority-queue main-loop real apply. 환경변수 AUTO_TESSELL_VVV9K_AP |
| `--enable-vvv9p-apply` | BOOL | False | beta2346 — VVV9P multi-face removal real apply. 환경변수 AUTO_TESSELL_VVV9P_APPLY=1  |
| `--parallel-delaunay` | BOOL | False | beta2365-2366 — V > 30000 시 ProcessPoolExecutor 기반 chunked Delaunay 병렬화. 환경변수 AU |
| `--seed-gwn` | BOOL | False | beta2392 — 시드 inside test 에 Jacobson 2013 generalized winding number 사용 (SI/non- |
| `--stellar-split` | BOOL | False | beta2374-2378 — Stellar 4-op queue 의 split-pass 활성. fine quality 는 자동 ON; 명시 for |
| `--poly-budget-s` | FLOAT | — | beta2381 — poly Voronoi escalate 의 wall-clock budget (초). 기본 90s. 환경변수 AUTO_TESS |
| `--bl-floor-ratio` | FLOAT | — | beta2447 — BL curvature_adaptive_thickness floor ratio (base_thickness 의 fractio |
| `--hex-snap-budget-s` | FLOAT | — | beta2457 — hex feature snap pass 의 wall-clock budget (초). 0=off (기본). 설정 시 강제 ca |
| `--lloyd-plateau-thresh` | FLOAT | — | beta2454/beta2458 — poly Lloyd CVT plateau early-exit threshold (rel-disp/bbox). |
| `--patch-cap` | INT | — | beta2459 — polyMesh patch count 상한 (이상은 wall_misc 로 병합). 기본 64. 늘리면 patch 별 BC 세 |
| `--no-cvt3d` | BOOL | False | beta2464 — tet 3D Lloyd CVT 비활성 (디버깅/측정용). 환경변수 AUTO_TESSELL_CVT3D_OFF=1 동등. |
| `--no-aniso-cvt` | BOOL | False | beta2464 — poly anisotropic CVT seeds 비활성 (디버깅/측정용). 환경변수 AUTO_TESSELL_ANISO_CVT |
| `--no-lcr` | BOOL | False | beta2464 — BL per-vertex LCR (Pointwise T-Rex) 비활성 (디버깅/측정용). 환경변수 AUTO_TESSELL_ |
| `--flow-velocity` | FLOAT | 1.0 | v0.4.0-beta78+ 유입 속도 [m/s]. 0/U 자동 생성 기준값. turbulence 필드 (k, epsilon/omega) 에 반영 |
| `--turbulence-model` | Choice(['kEpsilon', 'kOmegaSST | kEpsilon | 난류 모델 선택. |
| `--auto-retry` | Choice(['off', 'once', 'contin | off | Evaluator FAIL 시 자동 재시도 모드. off(기본, 사용자가 결정) / once / continue(예전 max_iterations |
| `--max-iterations` | INT | 3 | 최대 재시도 횟수 (auto_retry=continue 일 때만 사용됨; deprecated, 하위호환용) |
| `--dry-run` | BOOL | False | 전략 수립까지만 (메쉬 생성 안 함) |
| `--profile` | BOOL | False | 성능 프로파일링 (단계별 소요 시간) |
| `--export-vtk` | BOOL | False | 완료 후 VTK (.vtu) 내보내기 |
| `--polyhedral` | BOOL | False | Tet→Polyhedral 듀얼 변환 (polyDualMesh) |
| `--parallel` | INT | — | MPI 병렬 프로세서 수 (decomposeParDict 생성) |
| `--verbose-mesh` | BOOL | False | 메쉬 생성 상세 로그 |
| `--config` | <click.types.Path object at 0x | — | JSON config 파일. {env: {KEY: VALUE}} 형식. 여러 환경변수 한 번에 설정 (--ml-smooth-model 등 대신  |
| `--ml-smooth-model` | <click.types.Path object at 0x | — | trained tet quality predictor model 경로 (.pt). AUTO_TESSELL_ML_SMOOTH_MODEL 동등. |
| `--bl-predict-model` | <click.types.Path object at 0x | — | trained BL collision predictor model 경로 (.pt). AUTO_TESSELL_BL_PREDICT_MODEL 동등. |
| `--gpu-envelope` | BOOL | False | Eberly + torch.compile envelope check 활성 (AUTO_TESSELL_GPU_ENVELOPE=1, CUDA 50-1 |
| `--cvt3d-quality-weight` | BOOL | False | Volumetric Lloyd 가 quality-weighted target 사용 (AUTO_TESSELL_CVT3D_QUALITY_WEIGHT |
| `--lcr-auto-reduce` | BOOL | False | BL LCR global num_layers majority reduction (AUTO_TESSELL_LCR_AUTO_REDUCE=1). |
| `--bl-aniso-split` | BOOL | False | BL prism layer-uniform subdivide (AUTO_TESSELL_BL_ANISO_SPLIT=1, num_layers 2배). |

## `smoketest`

beta2276 — Installation smoke test. 단순 cube → 메쉬 + BL → 검증.

    상용 도구의 "Verify Installation" 동등. 모든 의존성 + native engine + BL +
    quality JSON 동작 확인.

| Option | Type | Default | Help |
|--------|------|---------|------|
| `--engine` | Choice(['tet', 'hex', 'poly',  | tet |  |

## `strategize`

메쉬 생성 전략(mesh_strategy.json)을 수립한다.

| Option | Type | Default | Help |
|--------|------|---------|------|
| `--geometry-report` | <click.types.Path object at 0x | Sentinel.UNSET |  |
| `--preprocessed-report` | <click.types.Path object at 0x | — |  |
| `--quality-report` | <click.types.Path object at 0x | — |  |
| `--tier` | STRING | auto |  |
| `--quality` | Choice(['draft', 'standard', ' | standard | 품질 레벨 (draft=빠른검증 / standard=엔지니어링 / fine=최종CFD) |
| `--iteration` | INT | 1 |  |
| `--output` / `-o` | <click.types.Path object at 0x | — |  |
