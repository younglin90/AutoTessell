"""M3 / beta2649 — ML predictor inference batching API.

대량 mesh 의 quality predict 시 batch 단위로 GPU 활용 극대화.
backend: torch CUDA 우선, CPU fallback.

API:
    runner = BatchInferenceRunner(model_path="models/ml_smooth_model.pt")
    quality_pred = runner.predict_meshes(mesh_pts_list, mesh_tets_list, batch_size=4096)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class BatchInferenceResult:
    success: bool
    n_total_samples: int = 0
    n_meshes: int = 0
    elapsed_s: float = 0.0
    backend: str = ""
    samples_per_sec: float = 0.0
    message: str = ""


class BatchInferenceRunner:
    """Trained model 한 번 load → 여러 mesh 에 대해 batched inference."""

    def __init__(
        self,
        model_path: str | Path,
        *,
        use_cuda: bool = True,
    ) -> None:
        self.model_path = Path(model_path)
        self._model = None
        self._device_str = "cpu"
        self._loaded = False
        self._use_cuda = use_cuda

    def _ensure_loaded(self) -> bool:
        if self._loaded:
            return self._model is not None
        try:
            from .ml_tet_smoothing import load_trained_predictor
            import torch
            self._device_str = (
                "cuda" if (self._use_cuda and torch.cuda.is_available())
                else "cpu"
            )
            self._model = load_trained_predictor(
                str(self.model_path), device=self._device_str,
            )
        except Exception:
            self._model = None
        self._loaded = True
        return self._model is not None

    def predict_meshes(
        self,
        mesh_pts_list: list[np.ndarray],
        mesh_tets_list: list[np.ndarray],
        *,
        batch_size: int = 4096,
    ) -> tuple[list[np.ndarray], BatchInferenceResult]:
        """여러 mesh 의 모든 tet quality predict.

        Returns:
            (per_mesh_predictions, BatchInferenceResult).
            per_mesh_predictions[i] shape == (n_tets_i,).
        """
        import time
        t0 = time.perf_counter()

        if not self._ensure_loaded() or self._model is None:
            return [], BatchInferenceResult(
                success=False,
                backend="skip",
                message=f"model load failed: {self.model_path}",
                elapsed_s=time.perf_counter() - t0,
            )

        try:
            from .training_data import extract_features_batch
            from .ml_tet_smoothing import predict_quality_batch
        except Exception as exc:
            return [], BatchInferenceResult(
                success=False,
                backend=f"torch_{self._device_str}_skip",
                message=f"deps missing: {exc!s:.60}",
                elapsed_s=time.perf_counter() - t0,
            )

        # 모든 mesh 의 features concat → 하나의 큰 array → 큰 batch infer.
        coords_list: list[np.ndarray] = []
        ctx_list: list[np.ndarray] = []
        n_per_mesh: list[int] = []

        for pts, tets in zip(mesh_pts_list, mesh_tets_list):
            if pts.size == 0 or tets.size == 0:
                n_per_mesh.append(0)
                continue
            c, ctx, _ = extract_features_batch(pts, tets)
            coords_list.append(c)
            ctx_list.append(ctx)
            n_per_mesh.append(int(c.shape[0]))

        if not coords_list:
            return [], BatchInferenceResult(
                success=False,
                backend=f"torch_{self._device_str}",
                n_meshes=len(mesh_pts_list),
                message="no valid mesh",
                elapsed_s=time.perf_counter() - t0,
            )

        all_coords = np.concatenate(coords_list, axis=0)
        all_ctx = np.concatenate(ctx_list, axis=0)
        K = int(all_coords.shape[0])

        # batch 단위로 predict.
        all_preds: list[np.ndarray] = []
        for s in range(0, K, batch_size):
            e = min(s + batch_size, K)
            try:
                pred = predict_quality_batch(
                    self._model,
                    all_coords[s:e],
                    all_ctx[s:e],
                    use_cuda=(self._device_str == "cuda"),
                )
                all_preds.append(pred)
            except Exception:
                all_preds.append(np.zeros(e - s, dtype=np.float32))

        all_preds_arr = np.concatenate(all_preds, axis=0) if all_preds else np.zeros(K, dtype=np.float32)

        # split back per mesh.
        per_mesh: list[np.ndarray] = []
        offset = 0
        for n_i in n_per_mesh:
            if n_i == 0:
                per_mesh.append(np.zeros(0, dtype=np.float32))
            else:
                per_mesh.append(all_preds_arr[offset:offset + n_i])
                offset += n_i

        elapsed = time.perf_counter() - t0
        return per_mesh, BatchInferenceResult(
            success=True,
            n_total_samples=K,
            n_meshes=len(mesh_pts_list),
            elapsed_s=elapsed,
            backend=f"torch_{self._device_str}",
            samples_per_sec=K / max(elapsed, 1e-9),
            message=f"batched {K} samples across {len(mesh_pts_list)} meshes",
        )
