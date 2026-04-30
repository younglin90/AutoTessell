# Auto-Tessell — 통합 사용 가이드 (BETA2608)

## 1. 기본 워크플로

### 1-A. 가장 짧은 명령

```bash
auto-tessell run input.stl -o ./case --mesh-type tet --quality standard
```

→ Analyzer → Preprocessor → Strategist → Generator → Evaluator 5-agent 파이프라인 자동 실행 → `./case/constant/polyMesh/` 생성.

### 1-B. mesh_type × quality 조합

| mesh_type | quality | 적합 케이스 |
|-----------|---------|------------|
| `tet` | `draft` | 빠른 prototype (1-3 sec sphere) |
| `tet` | `standard` | 일반 CFD (sphere ~10s) |
| `tet` | `fine` | 고정밀 (sliver 회복, +AMIPS smooth) |
| `hex_dominant` | `draft/standard` | BL 친화 (snappyHexMesh-style) |
| `hex_dominant` | `fine` | + boundary layer extrusion |
| `poly` | `draft/standard` | gradient 해소, 셀 수 최소 |

## 2. 메쉬 엔진 선택 (`--tier`)

자동 선택은 `tier=auto` (default). 강제 선택:

```bash
auto-tessell run input.stl --tier native_tet      # 자체 native
auto-tessell run input.stl --tier wildmesh        # WildMesh fallback
auto-tessell run input.stl --tier tetwild         # TetWild
auto-tessell run input.stl --tier snappy          # snappyHexMesh
auto-tessell run input.stl --tier ai              # Native AI dispatch
```

전체 19 엔진 목록은 `auto-tessell run --help` 참조.

## 3. ML 학습 + 배포 (D1-D6)

### 3-A. dataset 수집

```bash
# 빠른 (7-30 STL × 200 sample, ~30s-2min)
python3 scripts/collect_ml_dataset.py --stl-dir /tmp/ml_train_stls

# 큰 dataset (28+ STL × 300 sample, ~2-5min)
python3 scripts/collect_ml_dataset.py --stl-dir /tmp/ml_train_stls --n-samples-per-mesh 300
```

→ `models/ml_dataset.npz` 생성.

### 3-B. predictor 학습

```bash
python3 scripts/train_quality_predictor.py --epochs 50
# 또는 강한 학습:
python3 scripts/train_quality_predictor.py --epochs 80 --batch-size 128
```

→ `models/ml_smooth_model.pt` 생성. 예시 결과 (CUDA, 7800 samples):
- val_loss = 0.005-0.006

### 3-C. BL collision predictor 학습

```bash
python3 scripts/collect_bl_dataset.py
python3 scripts/train_bl_predictor.py --epochs 50
```

→ `models/bl_predictor.pt`.

### 3-D. 학습한 모델 활성화

**CLI**:
```bash
auto-tessell run input.stl \
  --ml-smooth-model models/ml_smooth_model.pt \
  --bl-predict-model models/bl_predictor.pt \
  --gpu-envelope --cvt3d-quality-weight --bl-aniso-split
```

**환경변수**:
```bash
export AUTO_TESSELL_ML_SMOOTH_MODEL=models/ml_smooth_model.pt
export AUTO_TESSELL_BL_PREDICT_MODEL=models/bl_predictor.pt
export AUTO_TESSELL_GPU_ENVELOPE=1
export AUTO_TESSELL_CVT3D_QUALITY_WEIGHT=1
export AUTO_TESSELL_BL_ANISO_SPLIT=1
```

**GUI**: advanced panel 의 "ML smooth model" / "BL predict model" 입력란 + 3 체크박스.

### 3-E. ML 효과 검증

```bash
python3 scripts/verify_ml_effect.py --stl tests/stl/03_hard_bracket.stl
```

→ baseline vs ml-on 의 n_cells/min_q/mean_q/grade 비교 표 출력.

## 4. CLI flag 전체 (G7 신규)

| flag | env equivalent | 효과 |
|------|---------------|------|
| `--ml-smooth-model PATH` | `AUTO_TESSELL_ML_SMOOTH_MODEL` | tet quality predictor (5.5k MLP) |
| `--bl-predict-model PATH` | `AUTO_TESSELL_BL_PREDICT_MODEL` | BL collision predictor (5k MLP) |
| `--gpu-envelope` | `AUTO_TESSELL_GPU_ENVELOPE=1` | Eberly + torch.compile (CUDA 50-100×) |
| `--cvt3d-quality-weight` | `AUTO_TESSELL_CVT3D_QUALITY_WEIGHT=1` | quality-weighted Lloyd target |
| `--lcr-auto-reduce` | `AUTO_TESSELL_LCR_AUTO_REDUCE=1` | BL global num_layers majority reduction |
| `--bl-aniso-split` | `AUTO_TESSELL_BL_ANISO_SPLIT=1` | BL prism layer-uniform subdivide (×2) |

기존 flag (이전 카드):
- `--polyhedral`: tet→poly dual.
- `--auto-retry off|once|continue`: Evaluator FAIL 재시도 정책.
- `--export-vtk`: 완료 후 VTK 내보내기.
- `--parallel N`: MPI decomposeParDict 생성.

## 5. 출력 포맷

| 포맷 | 명령 |
|------|------|
| OpenFOAM polyMesh | default — `<case>/constant/polyMesh/` |
| VTK (.vtu) | `--export-vtk` |
| StarCCM+ ASCII | `auto-tessell export <case> -o out.ccm.txt --fmt txt` |
| StarCCM+ binary (native variant) | `auto-tessell export <case> -o out.ccm --fmt binary` |
| Siemens CCMIO HDF5 | `auto-tessell export <case> -o out.ccm --fmt ccmio` |
| CGNS HDF5 (CFD 표준) | `auto-tessell export <case> -o out.cgns --fmt cgns` |
| Fluent (.cas) | `auto-tessell export <case> -o out.cas --fmt fluent` |

## 6. 실시간 모니터링 (GUI)

PySide6 GUI 의 viewport KPI overlay (G6 신규):
- **Tier**: 사용된 엔진 이름.
- **Time**: 총 실행 시간.
- **Mean Q**: 메쉬 평균 품질.
- **Min Q**: 최저 quality (warn 시 빨간색).
- **Grade**: A/B (highlight) / C / D/F (warn).
- **Cells**: 셀 수 (천 단위 콤마).

## 7. 빠른 검증 (회귀 + bench)

### 7-A. 단위 회귀 (~30s)
```bash
timeout 120 python3 -m pytest \
  tests/test_native_tet_amips.py tests/test_native_hex.py \
  tests/test_native_poly.py tests/test_native_ai.py \
  tests/test_cvt3d_aniso_cvt.py -q
```

### 7-B. 빠른 bench (~2-3 min)
```bash
python3 tests/stl/bench_difficulty_tiers.py --quick
```

### 7-C. 전체 bench (~30 min)
```bash
timeout 1500 python3 tests/stl/bench_difficulty_tiers.py
```

## 8. 트러블슈팅

| 증상 | 해결 |
|------|------|
| `inside hex 0` | `--bl-aniso-split` 끄기 또는 `seed-density` ↑ |
| OOM (대형 mesh) | `--max-cells 1000000` 낮추기, `--quick` mode |
| pytetwild segfault (worker pool) | env `AUTO_TESSELL_P4C_PYTETWILD=0` |
| GPU envelope 실패 | `--gpu-envelope` 끄기 → CPU BVH fallback 자동 |
| ML model val_loss 너무 높음 | dataset 더 수집 (`--max-meshes 50+`) + epochs 늘리기 |

## 9. 참고 문서

- `docs/env_flags_beta2581_2598.md` — env flag 전체 표.
- `docs/ccmio_format_spec.md` — Siemens CCMIO 형식 spec.
- `docs/plans/G_series_remaining_2026-04-30.md` — 잔여 SOTA 격차 로드맵.
- `agents/specs/generator.md` — Tier × QualityLevel 매핑.
- `models/README.md` — ML 모델 학습/배포 절차.
