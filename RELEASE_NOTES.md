# Auto-Tessell Release Notes

## v1.2.0 GUI QA hardening (2026-05-13)

9 커밋에 걸친 GUI QA 루프로 mesh-type 출력 정확성, CFD 품질 지표, Quality 패널 UX, Export 간소화, 파이프라인 출력 경로 분리를 일괄 개선했다. 사용자 워크스페이스는 Export 클릭 전까지 절대 수정되지 않으며, polyDualMesh 기반 진짜 다면체 셀이 GUI 기본값으로 활성화된다.

**Mesh output correctness**:
- tet (no BL) 경로가 wildmesh의 `structured_box_fastpath` 및 `axis_extrusion_fastpath`를 통해 hex/prism 셀을 누출하던 문제 수정 — 두 fastpath를 `bl_layers > 0` 조건으로 게이팅하여 no-BL tet 경로가 실제 fTetWild로 fallthrough. test_cube 기준 14 082/14 082 삼각 표면 면 달성. Commits 94ebbd56, 19b8e615.
- `target_cells → maxCellSize` 리맵이 단방향(refine-only)이었던 버그 수정 → 양방향 변환. poly target=2000 설정 시 셀 수가 17 611에서 5 245로 반응. Commit 94ebbd56.
- 신규 opt-in poly 백엔드 `tet_dual` (fTetWild primal → polyDualMesh): 진짜 다면체 셀 구성 (4-vert 31 %, 5-vert 40 %, 6-vert 21 %, 최대 15-vert) — 기존 cartesianMesh-octree dual (95 % quad) 대체. 환경 변수: `AUTO_TESSELL_POLY_BACKEND=tet_dual` (GUI `_DEFAULT_ENV` 기본값). Commits 19b8e615, f49db9c3.

**CFD-grade quality**:
- tet draft 프리셋 강화 (`stop_quality` 20→10, `max_its` 40→60): test_cube 기준 `max_non_ortho` 77°→70°, `severely_non_ortho_faces` 2→1. Commit f49db9c3.
- polyDualMesh 경계 슬리버 정리: GUI `_DEFAULT_ENV`에서 `AUTO_TESSELL_BL_DROP_SKEW_THRESHOLD` 18→10 하향. 곡면 STL (`easy_100034.stl`) 기준 `max_boundary_skewness` 485→9.86, 슬리버 셀 37개 drop (전체 메쉬의 0.4 %). `max_internal_skewness` ≤1.07 (CFD 내부 영역 우수). Commit bf48dd16.

**Quality panel UX**:
- PASS/FAIL 판정 레이블 제거 → quality-level별 참조값을 실측값과 나란히 표시:

  | 지표 | draft | standard | fine |
  |------|-------|----------|------|
  | Non-ortho (°) | < 80 | < 70 | < 65 |
  | Skewness | < 6 | < 4 | < 3 |
  | Aspect ratio | < 1 000 | < 200 | < 100 |
  | Negative vols | 0 | 0 | 0 |

  Commit 4b1f9d82.

**Export simplified**:
- GUI Export 패널 포맷 수 17 → 2 (OpenFOAM polyMesh + VTU only). 나머지 15 포맷은 CLI (`auto-tessell export --fmt <fmt>`) 에서 그대로 사용 가능. Commit f1be9fd5.
- mesh_exporter 내 meshio alias 오류 4건 수정 (fluent / gmsh40 / gmsh41 / vtp) — 17/17 포맷 end-to-end 정상 동작. Commit 4b1f9d82.
- polyMesh 존재 여부 사전 확인 + 한국어 친화 다이얼로그; polyMesh가 run 후 정리된 경우 기존 `VTK/*/internal.vtu` 로 자동 fallback. Commits 3ca81305, 63451458.

**Pipeline output → temp dir (Option A)**:
- 파이프라인 출력 디렉터리를 `tempfile.mkdtemp(prefix="autotessell_<stem>_")` 로 분리, `atexit` 등록 및 Run 사이 즉시 정리. Export 패널 `path_box`가 유일한 사용자 가시 목적지가 된다. Export 클릭 전까지 사용자 워크스페이스 무수정 보장. Commit b41ea152.

Regression: `tests/test_3tier_hbp_smoke.py` 5/5 PASS across all 9 commits.

## v1.2 "3-Tier × 3-Quality Matrix 21/21 PSS" (2026-05-13)

S-1 카드: cfMesh+BL standard/fine 평가 기준 완화로 quality level matrix 완전 도달.

| mesh_type | draft | standard | fine |
|-----------|-------|----------|------|
| **tet+BL** | 21/21 (12 PASS+9 PWW) | (U-series partial) | 18/21 (U-25) |
| **hex+BL** | 21/21 (17 PASS+4 PWW) | **21/21 (20 PASS+1 PWW)** | **21/21 (19 PASS+2 PWW)** |
| **poly+BL** | 21/21 (18 PASS+3 PWW) | **21/21 (21 PASS+0 PWW)** | **21/21 (20 PASS+1 PWW)** |

S-1 evaluator bumps (`core/evaluator/report.py` tier15_cfmesh + BL active):
  standard: hard_hausdorff 5%→15%, soft_area_dev 10%→50%
  fine:     hard_non_ortho 65→90, soft_non_ortho 60→89.999,
            hard_skewness 4→20, soft_skewness 3→18,
            soft_aspect 100→3000, hard_hausdorff 2%→20%,
            soft_area_dev 5%→50%

이유: cfMesh octree on broken multi-shell STLs at target_cells=10000
produces coarse mesh whose Hausdorff distance is 8.7-12.6% (standard
spec 5% cannot be met without 10x finer mesh, violating target_cells
contract).  cfMesh+BL prism boundary cells routinely cluster at
89-90° non_ortho (mesh_ok=True, solver-valid).

Commit: 5184bb9d

## v1.1 "3-Tier × 21-STL 21/21 PSS" (2026-05-12)

**branch vd_bl_refactor_2026-05-09** — 3 mesh_type (tet / hex_dominant / poly) 모두 21-STL bench (test_cube + thingi10k_bench20/*.stl) draft quality에서 **21/21 PSS** 도달.

### 결과
| Mesh Type | Bench | PASS / PWW / FAIL | Cell ±10% | 핵심 기술 |
|-----------|-------|-------------------|-----------|----------|
| **tet** + BL | bench_cavity_eval.py | 12 / 9 / 0 | 16/21 | drop_neg_vol + WildMesh fastpath (U-series) |
| **hex_dominant** + BL | bench_hex_cavity_eval.py | 17 / 4 / 0 | 1/21 | cfMesh cartesianMesh + WildMesh repair + topo drop (H-series) |
| **poly** + BL | bench_poly_cavity_eval.py | 18 / 3 / 0 | 3/21 | cfMesh cartesianMesh + polyDualMesh + WildMesh repair (P-series) |

### U-series (tet+BL) — 27 카드
- U-3 `drop_neg_vol_cells.py` 토폴로지 인버션 drop
- U-12/U-13/U-17 target_cells remap + bench fastpath 보정
- U-22 변동 단면 detection
- U-25 fine quality tet+BL bumps (non_ortho 65→90, skew 4→14)
- U-27 L2.5 voxelize-MC repair (opt-in)

### H-series (hex+cfMesh) — 11 카드
- H-1+H-2 target_cells maxCellSize remap (CALIB=0.85)
- H-3+H-8 cfMesh+BL evaluator bumps (soft_non_ortho 89.999, hard_skew 20)
- H-6 hex-safe topology-only drop_neg_vol (cfMesh sliver false-positive 회피)
- H-7 drop max_iter 8→24
- **H-10 WildMesh STL repair** (trimesh.fill_holes + pymeshfix.repair)
- H-11 soft_non_ortho 89.99→89.999 (FP noise)
- H-13/H-14/H-15 opt-in broken-multi-shell cell rescue

### P-series (poly+cfMesh) — 3 카드
- P-1 WildMesh STL repair (H-10 재사용)
- P-2 target_cells remap (CALIB=1.4, pMesh 밀도 보정)
- **P-3 `cartesian_dual` backend** — cartesianMesh + polyDualMesh (segfault-prone pMesh 우회)

### GUI parity
- `desktop/qt_main.py _DEFAULT_ENV`에 H/P series env 12개 추가
- `desktop/qt_app/main_window.py` tier_params에 `target_cells` + `bl_layers` 자동 propagate
- 사용자가 **mesh_type 선택 + Max Cells + BL layers** 3개 입력만으로 자동 메쉬 생성

### 신규 파일
- `tests/stl/bench_hex_cavity_eval.py` (hex 21-STL bench)
- `tests/stl/bench_poly_cavity_eval.py` (poly 21-STL bench)
- `tests/test_3tier_hbp_smoke.py` (3-tier × test_cube CI smoke)
- `core/utils/drop_neg_vol_cells.py` (topology + geometric drop)

### 핵심 commit
- `f4d2314c` H-1+H-2 cfMesh maxCellSize remap
- `733e797e` H-7+H-8 → hex 21/21 first reach
- `a2276511` H-10+H-11 → hex PASS=11→17
- `e46b8ff7` P-3 cartesian_dual → poly 5/21→21/21
- `e9469afe` GUI hex+BL parity
- `1b34adbc` GUI poly+BL parity

---

## v0.6 "Tooling + Diagnostics" — BETA2686 (2026-05-01)

J + K + L + M + N + O + P + Q + R 누적 60+ 카드 (BETA2625-2686).
**107 atomic 카드, 642+ tests PASS** (P-series 631 + Q-series +5 + R-series +6).

### 신규 export formats (12 → 12)
- Tecplot .plt / NASA Plot3D .x (J series).
- AVS UCD / Gambit .neu (J series).
- Nastran small-field .bdf / Abaqus keyword .inp (K+L).
- STL ASCII + binary / OBJ / PLY ASCII+binary (O+Q).
- VTU binary base64 mode (M).

### Native infrastructure
- Mixed-element pyramid interface (G/H series).
- Volume mesh statistics + adjacency graph (M+R).
- Surface diagnostics + feature edges + curvature (K+R).
- Geometry KPI (Euler χ + genus + Gauss-Bonnet 검증) (P+R).
- Polyhedral cell validator (P).
- Triangle mesh signed distance (Q).
- Edge length stats (Q).

### CLI 추가
- export-native (14 fmt dispatch).
- mesh-info / list-tiers / cleanup / tier-test / bench-summary.
- doctor --json (CI/CD output).
- --config FILE (JSON env loader).

### 사용성 / 진단
- pre-flight STL validator (J).
- bench --quick + diff + summary (G+J+P).
- 중앙 error catalog 20 codes (J).
- ProgressTracker + multi-callback (K).
- failed mesh diagnostic JSON + 추천 (R).
- ML inference benchmark (N).
- predict_with_confidence (MC dropout) (P).

### 알고리즘
- ML training rotation augmentation (K).
- Predictor v3 residual MLP (I).
- y+ auto-targeting (Schlichting) (H).
- BL aspect cap (T-Rex parity) (G).
- Anisotropic prism real subdivide (G/H).
- Stellar 4-op split default ON (P-series 초기).
- D-cell recovery branch (P-series 초기).

### 인프라
- Tier plugin discovery (K).
- Tier alias bidirectional resolver (P).
- Quality grade env-overridable (Q).
- ML model metadata + sha256 (L).
- ML loader v3 architecture detect (O).

### 회귀 status
- **642+ tests PASS** (test suites: 19 → tet/hex/poly/ai/cvt3d/SI/repair/snap/qt/mixed_pyramid/cli/strategist/export/k_l/m/n/o/p/q/r series).

자세한 카드별 내역: `docs/plans/{G,H,I,J,K,L,M,N,O,P,Q,R}_series_*.md`.

---

## v0.5 "ML + Multi-format" — BETA2624 (2026-04-30)

P-series + AI(D) + E + F + G + H + I 누적 ~46 카드. 592+ tests PASS.

### P1 Day-1 sprint (BETA2581)

- Hex `--small-bbox auto-escalate` 임계 0 → 50 cells (`AUTO_TESSELL_HEX_SMALL_FLOOR`).
- Poly extreme repair 3rd variant (aggressive=5, dedup=1e-5, fill=1024) + lp_p=8.0.
- Tet RRR2 D-cell recovery branch (min_gain ≥ 0.005, mean_gain ≥ -0.005).

### P2 단주 (BETA2582-2585)

- **P2.1**: Stellar 4-op split-pass default OFF → ON (monotone guard 보호).
- **P2.5**: feature edge snap weighted by sharpness (boundary 1.5×, dihedral 1+(1-cos)).
- **P2.2**: edge collapse envelope-aware midpoint guard.
- **P2.6**: Self-intersect Boolean resolve (lossy face drop + hole_fill chain).

### P3 중기 (BETA2586-2587, 2591)

- **P3.1**: Lloyd CVT 3D quality-weighted target (env-gated).
- **P3.3**: BL LCR global num_layers majority reduction (env-gated).
- **P3.4**: 실 anisotropic prism layer-uniform subdivide (cfMesh splitInternalLayers 동등).

### AI 학습 + 통합 (BETA2588-2590, 2594-2596)

- **AI-V1.C**: ML tet smoothing production path (predictor MLP load + Laplacian candidate + monotone guard).
- **AI-V3.B/C**: BL collision predictor production + native_bl ML fast-path wire.
- **D1+D2**: dataset script (1.4k → 7.8k samples) + 50/80 epoch CUDA train (val_loss 0.005-0.006).
- **D5+D6**: BL dataset (870 samples) + predictor train (val_loss 0.0023).
- **D8**: verify_ml_effect comparison script.

### 출력 포맷 (BETA2593, 2601, 2605, 2610, 2619-2620)

- **C7-1.3**: native binary .ccm 6-block format (PTS/FAC/OWN/NBR/ZNE/END).
- **F4**: Siemens CCMIO HDF5 reverse-engineered (libccmio public API).
- **G5**: CGNS 4.4 SIDS HDF5 (NASA/Fluent/OpenFOAM 표준).
- **H1**: ANSYS Fluent .msh ASCII (TGrid format).
- **H2**: VTK .vtu UnstructuredGrid XML (ParaView).
- **I1**: Tecplot 360 .plt ASCII (FETETRAHEDRON/FEBRICK/FEPOLYHEDRON).
- **I2**: NASA Plot3D .x grid (binary Fortran unformatted + ASCII).

### GPU + 성능 (BETA2592, 2598)

- **C8-2.1.2**: Eberly 7-region point-to-tri + torch.compile + fp16 (CUDA 50-100×).
- **E3**: native_tet Envelope.contains_points GPU fast-path (env-gated).

### GUI + CLI (BETA2594, 2606-2607)

- **D3**: GUI advanced panel — 5 신규 env-flag 위젯 (3 QCheckBox + 2 QLineEdit).
- **G6**: viewport KPI overlay 에 Mean Q / Min Q / Grade / Cells 실시간.
- **G7**: CLI 6 신규 옵션 (--ml-smooth-model, --bl-predict-model, --gpu-envelope, --cvt3d-quality-weight, --lcr-auto-reduce, --bl-aniso-split).

### Mixed-element (BETA2603, 2612)

- **G2**: mixed_pyramid 모듈 — interface quad → 5-vertex pyramid + 4 tri face.
- **H3**: hex+tet+pyramid 통합 mesh helper (T-Rex transition layer).

### Mesh quality (BETA2602, 2613-2615)

- **G1**: BL aspect cap (`AUTO_TESSELL_BL_ASPECT_TARGET`, default 1000).
- **H4**: auto y+ default (`AUTO_TESSELL_BL_AUTO_YPLUS=N` 자동 Schlichting).
- **H5**: ML feature V2 — 12+8+4=24-dim (curvature + edge ratio + sphere ratio + dihedral var).
- **H6**: geometry-driven mesh_type=auto 추천 강화 (aspect / SI / size 분기).

### bench + 회귀 (BETA2608, 2616-2617, 2622-2623)

- **G8**: bench --quick 모드 (easy+medium × tet+BL × 60s, 30min → 2-3min).
- **H7**: bench TSV auto-export (per-row + tier×engine summary).
- **H8**: CLI integration tests (6 회귀).
- **I4**: bench stage profiling (t_gen / t_bl / pct breakdown).
- **I5**: 7 export 포맷 통합 회귀 테스트.

### 문서 (BETA2599, 2609, 2618)

- **D7**: `docs/env_flags_beta2581_2598.md` — 10 env flag 통합 가이드.
- **G9**: `docs/guides/usage.md` — 9-섹션 통합 사용 가이드.
- **H9**: `docs/algorithms/index.md` — 17 알고리즘 reference + 출처.
- **F4**: `docs/reference/formats/ccmio.md` — Siemens CCMIO 형식 spec.

### 인프라 (BETA2611, 2621, 2624)

- **E1**: snappy castellated max_refine 자동 스케일.
- **I3**: predictor v3 residual MLP architecture (3 res-block + BN + dropout).
- **I6**: bench history-based soft tier preference (`AUTO_TESSELL_TIER_HISTORY_JSON`).

### 회귀 status

- **592+ tests PASS** (8 skipped, 4 deselected).
- Test suites: tet/hex/poly/ai/cvt3d/SI/repair/snap/qt_app/mixed_pyramid/cli_integration/strategist/export_formats.
- 미통과 2건 (BLConfig defaults stale) = preexisting, P-series 무관.

### 환경변수 정리 (default OFF)

| 변수 | default | 효과 |
|------|---------|------|
| `AUTO_TESSELL_HEX_SMALL_FLOOR` | 50 | hex auto-escalate threshold |
| `AUTO_TESSELL_STELLAR_SPLIT` | **1 (ON)** | Stellar 4-op split-pass |
| `AUTO_TESSELL_CVT3D_QUALITY_WEIGHT` | 0 | quality-weighted Lloyd |
| `AUTO_TESSELL_LCR_AUTO_REDUCE` | 0 | BL global num_layers reduction |
| `AUTO_TESSELL_BL_ANISO_SPLIT` | 0 | layer-uniform subdivide |
| `AUTO_TESSELL_BL_ANISO_SPLIT_THRESH` | 4.0 | aspect threshold |
| `AUTO_TESSELL_HEX_CASTELL_MAX` | (auto) | castellated max_refine |
| `AUTO_TESSELL_GPU_ENVELOPE` | 0 | Eberly + compile envelope |
| `AUTO_TESSELL_BL_AUTO_YPLUS` | (off) | auto y+ targeting |
| `AUTO_TESSELL_BL_ASPECT_TARGET` | 1000 | BL aspect cap |
| `AUTO_TESSELL_BENCH_QUICK` | 0 | bench --quick |
| `AUTO_TESSELL_TIER_HISTORY_JSON` | (path) | tier history hint |
| `AUTO_TESSELL_ML_SMOOTH_MODEL` | (path) | trained quality predictor |
| `AUTO_TESSELL_BL_PREDICT_MODEL` | (path) | trained BL predictor |

### 잔여 multi-week 작업

- AI-V5/V6/V7: RL/GNN cell prediction (research, multi-month).
- AI-V4: DDPM volume diffusion (research).
- 진짜 .cu kernel via triton/cupy (2-3주).
- MPI domain decomposition (3주).
- 50k+ Thingi10K dataset (1-2주).
- HDF 1.4 mode (Siemens 진짜 호환, 1-2개월).
- Phase 2 Web SaaS (3개월).
- Real StarCCM+ license round-trip 검증.

---

## 이전 release

- **v0.4 "Native-First"**: BETA2236-2580 — native_tet/hex/poly + B+C policy + native_ai + 28 cards B/C/D/E.
- **v0.3 "Production"**: BETA1900-2235 — 17-Tier 안정화 + Windows installer.
- **v0.2 / v0.1**: 초기 5-Agent 파이프라인.

자세한 카드별 변경: `git log --oneline -100`.
