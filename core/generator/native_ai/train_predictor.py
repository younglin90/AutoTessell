"""AI-V1.1.3 — train tet quality predictor.

generate_dataset_from_meshes 가 만든 .npz 를 읽어 quality_predictor 학습.
학습 결과 model.pt 저장. inference 는 ml_tet_smoothing.py 에서 load.

API:
    train_quality_predictor(dataset_npz, output_pt, epochs=50, batch_size=512)
        → TrainResult

CLAUDE.md 정책: torch 만 사용. CUDA 자동 감지.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class TrainResult:
    success: bool
    output_path: str = ""
    n_train_samples: int = 0
    n_val_samples: int = 0
    final_train_loss: float = 0.0
    final_val_loss: float = 0.0
    epochs: int = 0
    elapsed: float = 0.0
    backend: str = ""
    message: str = ""


def train_quality_predictor(
    dataset_npz: str,
    output_pt: str,
    *,
    epochs: int = 50,
    batch_size: int = 512,
    lr: float = 1e-3,
    val_split: float = 0.1,
    seed: int = 42,
    use_cuda: bool = True,
) -> TrainResult:
    """Train quality predictor on dataset.

    Args:
        dataset_npz: .npz file with arrays coords/context/quality.
        output_pt: torch .pt save path for trained model state_dict.
        epochs: training epochs.
        batch_size: minibatch.
        lr: Adam learning rate.
        val_split: fraction held out for validation.
        seed: random seed.
        use_cuda: CUDA 사용 시도.

    Returns:
        TrainResult.
    """
    import time
    from pathlib import Path
    t0 = time.perf_counter()

    try:
        import torch
        import torch.nn as nn
        from torch.utils.data import TensorDataset, DataLoader
    except ImportError:
        return TrainResult(
            success=False,
            output_path=output_pt,
            elapsed=time.perf_counter() - t0,
            backend="skip",
            message="torch not available",
        )

    if not Path(dataset_npz).exists():
        return TrainResult(
            success=False,
            output_path=output_pt,
            elapsed=time.perf_counter() - t0,
            message=f"dataset not found: {dataset_npz}",
        )

    data = np.load(dataset_npz)
    coords = np.asarray(data["coords"], dtype=np.float32)
    context = np.asarray(data["context"], dtype=np.float32)
    quality = np.asarray(data["quality"], dtype=np.float32)

    K = int(coords.shape[0])
    if K < 10:
        return TrainResult(
            success=False,
            output_path=output_pt,
            elapsed=time.perf_counter() - t0,
            message=f"dataset too small: {K} samples (need >= 10)",
        )

    # Combine coords + context → 20-dim input
    X = np.concatenate([coords, context], axis=1)  # (K, 20)
    y = quality.reshape(-1, 1)  # (K, 1)

    # Train/val split
    rng = np.random.default_rng(seed)
    perm = rng.permutation(K)
    n_val = max(1, int(K * val_split))
    val_idx = perm[:n_val]
    train_idx = perm[n_val:]

    device = torch.device("cuda" if (use_cuda and torch.cuda.is_available()) else "cpu")
    backend_str = f"torch_{device.type}"

    X_train = torch.tensor(X[train_idx], device=device)
    y_train = torch.tensor(y[train_idx], device=device)
    X_val = torch.tensor(X[val_idx], device=device)
    y_val = torch.tensor(y[val_idx], device=device)

    model = nn.Sequential(
        nn.Linear(20, 64),
        nn.ReLU(),
        nn.Linear(64, 64),
        nn.ReLU(),
        nn.Linear(64, 1),
        nn.Sigmoid(),
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    train_ds = TensorDataset(X_train, y_train)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)

    final_train_loss = 0.0
    for ep in range(epochs):
        model.train()
        ep_loss = 0.0
        n_b = 0
        for xb, yb in train_loader:
            optimizer.zero_grad()
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            optimizer.step()
            ep_loss += float(loss.item())
            n_b += 1
        final_train_loss = ep_loss / max(n_b, 1)

    model.eval()
    with torch.no_grad():
        val_pred = model(X_val)
        final_val_loss = float(loss_fn(val_pred, y_val).item())

    # Save state_dict + meta
    Path(output_pt).parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "state_dict": model.state_dict(),
        "n_train": int(train_idx.shape[0]),
        "n_val": int(val_idx.shape[0]),
        "epochs": epochs,
        "final_train_loss": final_train_loss,
        "final_val_loss": final_val_loss,
    }, output_pt)

    return TrainResult(
        success=True,
        output_path=output_pt,
        n_train_samples=int(train_idx.shape[0]),
        n_val_samples=int(val_idx.shape[0]),
        final_train_loss=final_train_loss,
        final_val_loss=final_val_loss,
        epochs=epochs,
        elapsed=time.perf_counter() - t0,
        backend=backend_str,
        message=f"saved trained model to {output_pt}",
    )
