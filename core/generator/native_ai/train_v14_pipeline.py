"""AI-V1.4 / beta2772 — production training pipeline (Thingi10K → trained .pt).

End-to-end driver:
    1. dataset_thingi10k.collect (10k+ samples)
    2. FeatureScaler.fit (BETA2712)
    3. MLP train (40-100 epochs, Adam, MSE)
    4. save_checkpoint (BETA2753) with stamp_version (BETA2739) + history (BETA2718).
    5. emit ModelDescriptor (BETA2726) JSON for portability.

CLI 사용:
    python3 -c "from core.generator.native_ai.train_v14_pipeline import run; run(limit=50, epochs=20)"

CLAUDE.md: torch 의존만, 외부 lib 신규 없음.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class TrainV14Result:
    n_train: int = 0
    n_val: int = 0
    n_features: int = 0
    final_train_loss: float = 0.0
    final_val_loss: float = 0.0
    elapsed_s: float = 0.0
    model_path: str = ""
    descriptor_path: str = ""
    history_path: str = ""


class _MLPv1:
    """Lightweight MLP: in→32→16→1 (ReLU)."""
    def __init__(self, in_dim: int):
        import torch.nn as nn
        self.net = nn.Sequential(
            nn.Linear(in_dim, 32), nn.ReLU(),
            nn.Linear(32, 16), nn.ReLU(),
            nn.Linear(16, 1),
        )


def run(
    *,
    limit: int = 50,
    out_dir: str | Path = "models",
    epochs: int = 30,
    batch_size: int = 64,
    lr: float = 1e-3,
    val_frac: float = 0.2,
    seed: int = 42,
    n_samples_per_mesh: int = 100,
    use_thingi10k: bool = False,
    fallback_stl_dir: str | None = None,
) -> TrainV14Result:
    """Production training driver.

    Args:
        limit: dataset 수집 mesh 수.
        out_dir: model 저장 경로.
        epochs: training epochs.
        batch_size, lr, val_frac, seed: 학습 hparam.
        n_samples_per_mesh: 각 mesh 에서 추출할 tet sample 수.
        use_thingi10k: True 면 thingi10k 패키지 사용.
        fallback_stl_dir: 없을 때 STL 디렉토리.

    Returns:
        TrainV14Result.
    """
    import torch
    import torch.nn as nn

    t0 = time.perf_counter()
    res = TrainV14Result()
    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)

    # 1. dataset.
    from core.generator.native_ai.dataset_thingi10k import collect
    npz_path = out_dir_p / "thingi10k_v14.npz"
    cr = collect(
        limit=limit, out=str(npz_path),
        n_samples_per_mesh=n_samples_per_mesh,
        use_thingi10k=use_thingi10k,
        fallback_stl_dir=fallback_stl_dir,
    )
    if cr.n_samples_total < 10:
        res.elapsed_s = time.perf_counter() - t0
        return res

    ds = np.load(str(npz_path))
    X_all = ds["X"].astype(np.float32)
    y_all = ds["y"].astype(np.float32)
    n_total = int(X_all.shape[0])
    in_dim = int(X_all.shape[1])

    # 2. shuffle + split.
    rng = np.random.RandomState(seed)
    perm = rng.permutation(n_total)
    n_val = max(1, int(n_total * val_frac))
    val_idx = perm[:n_val]; tr_idx = perm[n_val:]
    X_tr = X_all[tr_idx]; y_tr = y_all[tr_idx]
    X_va = X_all[val_idx]; y_va = y_all[val_idx]

    # 3. FeatureScaler (BETA2712).
    from core.generator.native_ai.feature_norm import FeatureScaler
    sc = FeatureScaler.fit(X_tr.astype(np.float64))
    X_tr_n = sc.transform(X_tr.astype(np.float64)).astype(np.float32)
    X_va_n = sc.transform(X_va.astype(np.float64)).astype(np.float32)
    sc.save(str(out_dir_p / "scaler_v14.json"))

    # 4. model + opt.
    model = _MLPv1(in_dim).net
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    crit = nn.MSELoss()

    # 5. history logger (BETA2718).
    from core.generator.native_ai.train_history import TrainHistoryLogger
    history_path = out_dir_p / "history_v14.csv"
    log = TrainHistoryLogger(path=history_path)

    X_tr_t = torch.from_numpy(X_tr_n)
    y_tr_t = torch.from_numpy(y_tr).unsqueeze(1)
    X_va_t = torch.from_numpy(X_va_n)
    y_va_t = torch.from_numpy(y_va).unsqueeze(1)

    n_tr = X_tr_t.shape[0]
    final_tr_loss = 0.0
    final_va_loss = 0.0
    best_val = float("inf")

    for ep in range(1, int(epochs) + 1):
        # mini-batch.
        perm_ep = torch.randperm(n_tr)
        ep_loss = 0.0; n_b = 0
        model.train()
        for i in range(0, n_tr, batch_size):
            idx = perm_ep[i:i + batch_size]
            x = X_tr_t[idx]; y = y_tr_t[idx]
            opt.zero_grad()
            yhat = model(x)
            loss = crit(yhat, y)
            loss.backward()
            opt.step()
            ep_loss += float(loss.item())
            n_b += 1
        tr_loss = ep_loss / max(n_b, 1)

        model.eval()
        with torch.no_grad():
            va_loss = float(crit(model(X_va_t), y_va_t).item())
        log.append(epoch=ep, train_loss=tr_loss, val_loss=va_loss, lr=lr,
                   elapsed_s=time.perf_counter() - t0)
        final_tr_loss = tr_loss
        final_va_loss = va_loss
        if va_loss < best_val:
            best_val = va_loss

    # 6. save checkpoint.
    from core.generator.native_ai.train_resume import save_checkpoint
    model_path = out_dir_p / "v14_quality_predictor.pt"
    save_checkpoint(
        model_path, model, opt, epoch=epochs,
        best_val_loss=best_val,
        extra={
            "architecture": "mlp_v14",
            "input_dim": in_dim,
            "n_train": int(X_tr.shape[0]),
            "n_val": int(X_va.shape[0]),
            "epochs": int(epochs),
            "batch_size": int(batch_size),
            "lr": float(lr),
            "seed": int(seed),
            "final_train_loss": float(final_tr_loss),
            "final_val_loss": float(final_va_loss),
            "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "backend": "cpu",
        },
    )

    # 7. descriptor (BETA2726).
    from core.generator.native_ai.model_descriptor import export_descriptor_to_file
    desc_path = out_dir_p / "v14_descriptor.json"
    export_descriptor_to_file(model_path, desc_path)

    res.n_train = int(X_tr.shape[0])
    res.n_val = int(X_va.shape[0])
    res.n_features = in_dim
    res.final_train_loss = float(final_tr_loss)
    res.final_val_loss = float(final_va_loss)
    res.elapsed_s = time.perf_counter() - t0
    res.model_path = str(model_path)
    res.descriptor_path = str(desc_path)
    res.history_path = str(history_path)
    return res
