# Auto-Tessell Release Notes

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
- **G9**: `docs/USAGE.md` — 9-섹션 통합 사용 가이드.
- **H9**: `docs/algorithms/index.md` — 17 알고리즘 reference + 출처.
- **F4**: `docs/ccmio_format_spec.md` — Siemens CCMIO 형식 spec.

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
