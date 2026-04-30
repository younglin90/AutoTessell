"""AI-V1.1 — ML training dataset generator (stub).

ml_tet_smoothing.py 의 quality predictor 학습용 dataset 생성:
    - 입력 mesh 에서 random tet sample 추출
    - 각 tet 의 12-dim coords + 8-dim 1-ring context features 계산
    - Klingner mean-ratio quality 를 ground truth label 로 산출
    - HDF5 / npz 형식으로 저장

현재 (skeleton): API + feature extraction stub.
실제 dataset generation 은 별도 카드:
    AI-V1.1.1: feature extractor 구현 (1-ring stats, dihedral, etc) — 본 카드
    AI-V1.1.2: Thingi10K 100 mesh × 100 tet/mesh = 10k samples 생성 (3일)
    AI-V1.1.3: train/val 분할 + scaler stats 계산 (1일)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class TetSample:
    """Single tet training sample."""

    coords_12: np.ndarray         # (12,) 4 vertex × 3 coords
    context_8: np.ndarray         # (8,) 1-ring stats
    quality: float                 # Klingner mean-ratio (0-1)


@dataclass
class DatasetGenResult:
    success: bool
    n_samples: int = 0
    output_path: str = ""
    elapsed: float = 0.0
    message: str = ""


def extract_tet_features(
    pts: np.ndarray,
    tets: np.ndarray,
    tet_idx: int,
    *,
    include_context: bool = True,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Extract feature vector + quality for single tet.

    Args:
        pts: (N, 3) all vertex coords.
        tets: (T, 4) all tets.
        tet_idx: target tet index.
        include_context: True 면 1-ring context features 도 계산.

    Returns:
        (coords_12, context_8, quality).
    """
    a, b, c, d = tets[tet_idx]
    p_a, p_b, p_c, p_d = pts[a], pts[b], pts[c], pts[d]

    # 12-dim coords (centered at centroid for translation-invariance)
    centroid = (p_a + p_b + p_c + p_d) / 4.0
    coords_12 = np.concatenate([p_a, p_b, p_c, p_d]) - np.tile(centroid, 4)

    # 8-dim context (1-ring stats — placeholder here)
    if include_context:
        # Real implementation: count incident tets, mean neighbor quality, etc.
        # Skeleton: 8 zeros.
        context_8 = np.zeros(8, dtype=np.float64)
    else:
        context_8 = np.zeros(8, dtype=np.float64)

    # Klingner mean-ratio quality
    edges = np.stack([
        p_b - p_a, p_c - p_a, p_d - p_a,
        p_c - p_b, p_d - p_b, p_d - p_c,
    ])
    e_sq_sum = float((edges ** 2).sum())
    vol_6 = float((np.cross(p_b - p_a, p_c - p_a) * (p_d - p_a)).sum())
    vol = abs(vol_6) / 6.0
    if e_sq_sum < 1e-30:
        quality = 0.0
    else:
        quality = float(np.clip(
            12.0 * ((3.0 * vol) ** (2.0 / 3.0)) / e_sq_sum,
            0.0, 1.0,
        ))

    return coords_12.astype(np.float64), context_8, quality


def generate_dataset_skeleton(
    output_path: str,
    *,
    n_samples: int = 10000,
    seed: int = 42,
) -> DatasetGenResult:
    """ML training dataset generator (skeleton).

    실제 구현 (AI-V1.1.2 카드): Thingi10K 100 mesh × 100 sample = 10k.
    현재 stub: 미구현 → not_implemented 반환.

    Args:
        output_path: .npz 출력 경로.
        n_samples: target sample count.
        seed: random seed.

    Returns:
        DatasetGenResult.
    """
    import time
    t0 = time.perf_counter()
    return DatasetGenResult(
        success=False,
        n_samples=0,
        output_path=output_path,
        elapsed=time.perf_counter() - t0,
        message=(
            f"AI-V1.1 dataset generator not yet implemented. "
            f"Target: n_samples={n_samples} (placeholder)."
        ),
    )


def extract_features_batch(
    pts: np.ndarray,
    tets: np.ndarray,
    tet_indices: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Batch feature extraction for multiple tets.

    Args:
        pts: (N, 3).
        tets: (T, 4).
        tet_indices: (K,) target indices. None → all tets.

    Returns:
        (coords (K, 12), context (K, 8), qualities (K,)).
    """
    if tet_indices is None:
        tet_indices = np.arange(tets.shape[0], dtype=np.int64)
    K = int(tet_indices.shape[0])
    coords = np.zeros((K, 12), dtype=np.float64)
    contexts = np.zeros((K, 8), dtype=np.float64)
    quals = np.zeros(K, dtype=np.float64)
    for i, ti in enumerate(tet_indices.tolist()):
        c12, c8, q = extract_tet_features(pts, tets, int(ti))
        coords[i] = c12
        contexts[i] = c8
        quals[i] = q
    return coords, contexts, quals
