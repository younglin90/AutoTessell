# assets/models/ — trained ML 모델 디렉터리

## 사용법

### 1. dataset 수집 (D1)

```bash
# 기본 (35 STL × 200 sample, ~5-10 min)
python3 scripts/collect_ml_dataset.py

# 빠른 검증 (7 STL × 200 sample, ~30s)
python3 scripts/collect_ml_dataset.py --stl-dir /tmp/ml_train_stls --n-samples-per-mesh 200 --max-meshes 7
```

→ `assets/models/ml_dataset.npz` 생성 (features + qualities).

### 2. predictor train (D2)

```bash
python3 scripts/train_quality_predictor.py --epochs 50
```

→ `assets/models/ml_smooth_model.pt` 생성. 예시 결과: `val_loss=0.005` (CUDA).

### 3. 활성화

```bash
# CLI / shell
export AUTO_TESSELL_ML_SMOOTH_MODEL=assets/models/ml_smooth_model.pt
auto-tessell run input.stl --mesh-type tet ...
```

또는 GUI 의 "advanced" 패널 → "ML smooth model" 입력란에 경로 입력.

## 파일 형식

| 파일 | 형식 | 키 |
|------|------|-----|
| `ml_dataset.npz` | numpy npz | `features (N, 20)`, `qualities (N,)` |
| `ml_smooth_model.pt` | torch.save | `state_dict` + `n_train` + `final_train_loss` + `final_val_loss` |

## 참고

`.gitignore` 가 `*.npz` / `*.pt` 모두 제외. 모델은 git 에 commit 하지 않음 (사용자가 직접 학습 또는 배포).
