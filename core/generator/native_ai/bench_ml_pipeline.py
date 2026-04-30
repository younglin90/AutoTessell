"""AI-V1.4 — production ML pipeline bench. Thingi10K → dataset → train → eval.

End-to-end production training pipeline:
    1. iterate Thingi10K mesh cache
    2. for each mesh: native_tet generate → extract tet samples
    3. accumulate dataset (target 10k samples)
    4. train predictor
    5. measure prediction MSE on held-out validation
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class BenchMLResult:
    success: bool
    n_samples_collected: int = 0
    train_loss: float = 0.0
    val_loss: float = 0.0
    val_mse_pct: float = 0.0     # val MSE × 100 (quality scale 0-1)
    elapsed: float = 0.0
    backend: str = ""
    message: str = ""


def run_ml_pipeline_bench(
    output_dir: Path | str,
    *,
    n_meshes: int = 50,
    samples_per_mesh: int = 200,
    epochs: int = 30,
    use_cuda: bool = True,
) -> BenchMLResult:
    """Production bench (AI-V1.4).

    현재 (skeleton): Thingi10K iteration 미통합 → 합성 mesh 사용.
    실제 통합은 Thingi10K cache 의 NPZ 파일 직접 read.
    """
    import time
    t0 = time.perf_counter()

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from .training_data import generate_dataset_from_meshes
        from .train_predictor import train_quality_predictor
    except ImportError as exc:
        return BenchMLResult(
            success=False,
            backend="skip",
            message=f"native_ai modules unavailable: {exc!s:.80}",
            elapsed=time.perf_counter() - t0,
        )

    # 합성 mesh (skeleton). production 에서는 thingi10k.iterate() 로 대체.
    rng = np.random.default_rng(42)
    mesh_pts: list[np.ndarray] = []
    mesh_tets: list[np.ndarray] = []
    for _ in range(n_meshes):
        pts = rng.random((10, 3))
        # 연결된 random tet
        tets = np.array([
            [0, 1, 2, 3],
            [1, 2, 3, 4],
            [2, 3, 4, 5],
            [3, 4, 5, 6],
            [4, 5, 6, 7],
        ], dtype=np.int64)
        mesh_pts.append(pts)
        mesh_tets.append(tets)

    npz = output_dir / "ml_bench_dataset.npz"
    pt = output_dir / "ml_bench_model.pt"

    r1 = generate_dataset_from_meshes(
        str(npz), mesh_pts, mesh_tets, samples_per_mesh=samples_per_mesh,
    )
    if not r1.success:
        return BenchMLResult(
            success=False,
            elapsed=time.perf_counter() - t0,
            message=f"dataset gen failed: {r1.message[:80]}",
        )

    r2 = train_quality_predictor(
        str(npz), str(pt), epochs=epochs, batch_size=64, lr=1e-3,
        use_cuda=use_cuda,
    )
    if not r2.success:
        return BenchMLResult(
            success=False,
            elapsed=time.perf_counter() - t0,
            n_samples_collected=r1.n_samples,
            message=f"train failed: {r2.message[:80]}",
        )

    return BenchMLResult(
        success=True,
        n_samples_collected=r1.n_samples,
        train_loss=r2.final_train_loss,
        val_loss=r2.final_val_loss,
        val_mse_pct=r2.final_val_loss * 100.0,
        elapsed=time.perf_counter() - t0,
        backend=r2.backend,
        message=f"ML bench: {r1.n_samples} samples, {epochs} epochs, "
                f"val_loss {r2.final_val_loss:.4f}",
    )
