"""AI-V3.2 — Train BL collision predictor on dataset from bl_collision_data.

Same architecture pattern as train_predictor.py (V1.1.3) but for 12-dim
BL features → log(gap) regression target.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class BLTrainResult:
    success: bool
    output_path: str = ""
    n_train_samples: int = 0
    n_val_samples: int = 0
    final_train_loss: float = 0.0
    final_val_loss: float = 0.0
    epochs: int = 0
    backend: str = ""
    elapsed: float = 0.0
    message: str = ""


def train_bl_collision_predictor(
    dataset_npz: str,
    output_pt: str,
    *,
    epochs: int = 30,
    batch_size: int = 256,
    lr: float = 1e-3,
    val_split: float = 0.1,
    seed: int = 42,
    use_cuda: bool = True,
) -> BLTrainResult:
    """Train BL collision predictor (AI-V3.2)."""
    import time
    t0 = time.perf_counter()
    try:
        import torch
        import torch.nn as nn
        from torch.utils.data import TensorDataset, DataLoader
    except ImportError:
        return BLTrainResult(
            success=False, output_path=output_pt,
            backend="skip", message="torch not available",
            elapsed=time.perf_counter() - t0,
        )

    if not Path(dataset_npz).exists():
        return BLTrainResult(
            success=False, output_path=output_pt,
            elapsed=time.perf_counter() - t0,
            message=f"dataset not found: {dataset_npz}",
        )

    data = np.load(dataset_npz)
    feats = np.asarray(data["features"], dtype=np.float32)
    gaps = np.asarray(data["gaps"], dtype=np.float32)
    K = int(feats.shape[0])
    if K < 10:
        return BLTrainResult(
            success=False, output_path=output_pt,
            elapsed=time.perf_counter() - t0,
            message=f"dataset too small: {K}",
        )

    # log-transform gap (regression target)
    target = np.log1p(gaps).reshape(-1, 1)

    rng = np.random.default_rng(seed)
    perm = rng.permutation(K)
    n_val = max(1, int(K * val_split))
    val_idx = perm[:n_val]
    train_idx = perm[n_val:]

    device = torch.device("cuda" if (use_cuda and torch.cuda.is_available()) else "cpu")
    backend_str = f"torch_{device.type}"

    X_tr = torch.tensor(feats[train_idx], device=device)
    y_tr = torch.tensor(target[train_idx], device=device)
    X_va = torch.tensor(feats[val_idx], device=device)
    y_va = torch.tensor(target[val_idx], device=device)

    model = nn.Sequential(
        nn.Linear(12, 64),
        nn.ReLU(),
        nn.Linear(64, 64),
        nn.ReLU(),
        nn.Linear(64, 1),
    ).to(device)
    optim = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    train_loader = DataLoader(TensorDataset(X_tr, y_tr), batch_size=batch_size, shuffle=True)
    final_train_loss = 0.0
    for ep in range(epochs):
        model.train()
        ep_loss, n_b = 0.0, 0
        for xb, yb in train_loader:
            optim.zero_grad()
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            optim.step()
            ep_loss += float(loss.item())
            n_b += 1
        final_train_loss = ep_loss / max(n_b, 1)

    model.eval()
    with torch.no_grad():
        final_val_loss = float(loss_fn(model(X_va), y_va).item())

    Path(output_pt).parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "state_dict": model.state_dict(),
        "n_train": int(train_idx.shape[0]),
        "n_val": int(val_idx.shape[0]),
        "epochs": epochs,
        "final_train_loss": final_train_loss,
        "final_val_loss": final_val_loss,
    }, output_pt)

    return BLTrainResult(
        success=True,
        output_path=output_pt,
        n_train_samples=int(train_idx.shape[0]),
        n_val_samples=int(val_idx.shape[0]),
        final_train_loss=final_train_loss,
        final_val_loss=final_val_loss,
        epochs=epochs,
        backend=backend_str,
        elapsed=time.perf_counter() - t0,
        message=f"BL collision predictor trained ({backend_str})",
    )
