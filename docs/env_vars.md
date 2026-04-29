# AutoTessell — Environment Variables Reference

이 문서는 AutoTessell 의 모든 환경변수를 정리합니다 (beta2452 기준).

## 사용자 권장 환경변수

### Performance / 시간 제어

| 환경변수 | 기본값 | 효과 |
|---------|--------|------|
| `AUTO_TESSELL_PARALLEL_DELAUNAY` | "auto" | "1"=강제 ON, "0"=강제 OFF, auto=cpu_count≥2 시 자동 |
| `AUTO_TESSELL_POLY_BUDGET_S` | 90 | poly Voronoi escalate 의 wall-clock budget (초) |
| `AUTO_TESSELL_HEX_BUDGET_LOG_S` | 120 | hex 가 이 값 초과 시 warning 로그 (실제 cancel 없음) |
| `AUTO_TESSELL_HEX_WWW7_BUDGET_S` | 0 (off) | hex feature snap pass skip budget (초). 설정 시 강제 cap |

### Quality / 알고리즘 토글

| 환경변수 | 기본값 | 효과 |
|---------|--------|------|
| `AUTO_TESSELL_SEED_GWN` | "auto" | "1"=강제 GWN, "0"=강제 ray-cast, auto=SI 검출 시 자동 GWN |
| `AUTO_TESSELL_STELLAR_SPLIT` | (off) | "1"=Stellar 4-op queue 의 split-pass 활성. fine 자동 ON |
| `AUTO_TESSELL_BL_FLOOR_RATIO` | 1.0 | BL curvature_adaptive_thickness floor ratio (0.0-1.0) |
| `AUTO_TESSELL_BL_ANISO_SPLIT_DIAG` | (off) | "1"=BL aniso prism split diagnostic 활성 |
| `AUTO_TESSELL_LCR_OFF` | (off) | "1"=BL per-vertex LCR (Pointwise T-Rex) 비활성 |
| `AUTO_TESSELL_QED` | "auto" | "auto"=face count > _qed_min 시 자동 simplification |
| `AUTO_TESSELL_QED_MIN_F` | 20000 | QED 활성 face count 임계 |
| `AUTO_TESSELL_ANISO_CVT_OFF` | (off) | "1"=poly aniso CVT seeds 비활성 |
| `AUTO_TESSELL_CVT3D_OFF` | (off) | "1"=tet 3D Lloyd CVT 비활성 |

### Patch / Output

| 환경변수 | 기본값 | 효과 |
|---------|--------|------|
| `AUTO_TESSELL_PATCH_CAP` | 64 | polyMesh patch count cap (이상은 wall_misc 병합) |

### P4-C fallback

| 환경변수 | 기본값 | 효과 |
|---------|--------|------|
| `AUTO_TESSELL_P4C_PYTETWILD` | "1" | "0"=pytetwild fallback 비활성 (self-only 측정) |
| `AUTO_TESSELL_P4C_EDGE_LEN_FAC` | 0.05 | pytetwild edge length factor |
| `AUTO_TESSELL_P4C_EPSILON` | 0.001 | pytetwild epsilon |
| `AUTO_TESSELL_P4C_STOP_ENERGY` | 10.0 | pytetwild stop_energy |
| `AUTO_TESSELL_P4C_NUM_OPT_ITER` | 80 | pytetwild num_opt_iter |

## CLI flags 동등

CLI 의 명시 flag 가 env 값을 override 합니다:

| CLI flag | env var | type |
|----------|---------|------|
| `--seed-gwn` | `AUTO_TESSELL_SEED_GWN=1` | flag |
| `--stellar-split` | `AUTO_TESSELL_STELLAR_SPLIT=1` | flag |
| `--parallel-delaunay` | `AUTO_TESSELL_PARALLEL_DELAUNAY=1` | flag |
| `--poly-budget-s N` | `AUTO_TESSELL_POLY_BUDGET_S=N` | float |
| `--bl-floor-ratio N` | `AUTO_TESSELL_BL_FLOOR_RATIO=N` | float |

## 권장 조합 (use case 별)

### Hard SI mesh (e.g. thingi10k self-intersecting)

```bash
auto-tessell run input.stl --quality fine \
    --seed-gwn \
    --stellar-split \
    --bl-floor-ratio 1.0 \
    --poly-budget-s 60
```

### Fast preview (낮은 quality, 빠른 시간)

```bash
auto-tessell run input.stl --quality draft \
    --parallel-delaunay
```

### Production CFD (cfMesh parity)

```bash
auto-tessell run input.stl --quality fine \
    --bl-floor-ratio 0.7   # cfMesh maxFirstLayerThickness parity
```

## V-series experimental flags (advanced)

V-series 는 sliver 격감 실험적 알고리즘들. 모두 monotone guard 적용.

| 환경변수 | 효과 |
|---------|------|
| `AUTO_TESSELL_VVV9H_APPLY` | Klingner 2008 §3.5 edge-contract real apply |
| `AUTO_TESSELL_OFFPLANE_STEINER` | Klingner-Shewchuk 2008 §4.1 off-plane Steiner |
| `AUTO_TESSELL_VVV9J_APPLY` | SLIM smoothing 강화 |
| `AUTO_TESSELL_VVV9K_APPLY` | worst-first priority queue |
| `AUTO_TESSELL_VVV9P_APPLY` | multi-face removal |
| `AUTO_TESSELL_RRR2_TARGETED` | RRR2 worst-percentile targeted AMIPS (default ON) |
| `AUTO_TESSELL_P3_SSS_REVIVAL` | SSS_REVIVAL surface vertex relocation (default ON) |
| `AUTO_TESSELL_P3_SSS_REVIVAL_PASSES` | SSS_REVIVAL pass 수 (default 3) |
| `AUTO_TESSELL_VVV2_QUEUE` | Stellar 4-op queue (default ON) |
