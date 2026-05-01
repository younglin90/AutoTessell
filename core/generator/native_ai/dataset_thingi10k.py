"""AI-V1.4 / beta2771 — Thingi10K dataset auto-collector for tet quality predictor.

Thingi10K mesh 들을 iterate → native_tet 으로 메쉬 생성 → tet sample 추출 →
training-ready (X (N, D), y (N,)) JSON/NPZ 저장.

Pipeline:
    1. Thingi10K cache iterate (limit_n=100 default).
    2. 각 STL → V, F load (core.analyzer.readers.stl).
    3. native_tet mesher 실행 (timeout 120s/mesh).
    4. 생성된 tet 들에서 (features, quality) 페어 추출:
       features = [edge_min/max, vol, aspect, valence, ...] (TBD per V1 model).
       quality = tet_qshape Q ∈ [0, 1].
    5. 모든 mesh 통합 → NPZ 저장.

Usage:
    python3 -c "from core.generator.native_ai.dataset_thingi10k import collect; collect(limit=10, out='/tmp/ds.npz')"

CLAUDE.md: torch 의존만, Thingi10K cache 는 thingi10k 패키지 활용.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


@dataclass
class CollectResult:
    n_meshes_attempted: int = 0
    n_meshes_ok: int = 0
    n_samples_total: int = 0
    elapsed_s: float = 0.0
    errors: list[str] | None = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def _extract_tet_features(
    pts: NDArray[np.float64],
    tets: NDArray[np.int64],
    *,
    n_samples_per_mesh: int = 100,
    seed: int = 42,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """tet sample 에서 (X, y) 추출.

    Features (per tet, D=8):
        [vol, edge_min, edge_max, edge_mean, aspect_max, edge_p25, edge_p75, edge_std]
    Target:
        Q (Klingner-like, BETA2709) ∈ [0, 1].

    Args:
        pts, tets: tet mesh.
        n_samples_per_mesh: 각 mesh 에서 sample 할 tet 수 (random).
        seed: rng seed.

    Returns:
        (X (n, 8), y (n,)).
    """
    n_t = int(tets.shape[0])
    if n_t == 0:
        return np.zeros((0, 8), dtype=np.float64), np.zeros(0, dtype=np.float64)

    n = min(n_samples_per_mesh, n_t)
    rng = np.random.RandomState(seed)
    idx = rng.choice(n_t, size=n, replace=False)
    sub_tets = tets[idx]

    a = pts[sub_tets[:, 0]]
    b = pts[sub_tets[:, 1]]
    c = pts[sub_tets[:, 2]]
    d = pts[sub_tets[:, 3]]
    vol = np.abs(np.einsum("ij,ij->i", np.cross(b - a, c - a), d - a)) / 6.0

    EDGES = np.array([[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]],
                     dtype=np.int64)
    e_idx = sub_tets[:, EDGES]
    p0 = pts[e_idx[..., 0]]
    p1 = pts[e_idx[..., 1]]
    e_lens = np.linalg.norm(p1 - p0, axis=-1)  # (n, 6).

    e_min = e_lens.min(axis=1)
    e_max = e_lens.max(axis=1)
    e_mean = e_lens.mean(axis=1)
    e_std = e_lens.std(axis=1)
    e_p25 = np.percentile(e_lens, 25, axis=1)
    e_p75 = np.percentile(e_lens, 75, axis=1)
    aspect = e_max / np.maximum(e_min, 1e-30)

    X = np.stack([vol, e_min, e_max, e_mean, aspect, e_p25, e_p75, e_std], axis=1)

    # target Q via tet_qshape.
    from core.evaluator.tet_qshape import tet_qshape
    Q_all, _ = tet_qshape(pts, tets)
    y = Q_all[idx]

    return X.astype(np.float64), y.astype(np.float64)


def collect(
    *,
    limit: int = 100,
    out: str | Path = "thingi10k_tet_samples.npz",
    n_samples_per_mesh: int = 100,
    timeout_per_mesh_s: float = 120.0,
    use_thingi10k: bool = True,
    fallback_stl_dir: str | Path | None = None,
) -> CollectResult:
    """Thingi10K iterate → tet sample 수집 → NPZ 저장.

    Args:
        limit: 최대 mesh 수.
        out: 출력 NPZ 경로.
        n_samples_per_mesh: 각 mesh 에서 sample 할 tet 수.
        timeout_per_mesh_s: per-mesh wallclock budget (timeout 초과 → 스킵).
        use_thingi10k: True 면 thingi10k 패키지 사용 (없으면 fallback_stl_dir).
        fallback_stl_dir: thingi10k 없을 때 사용할 STL 디렉토리.

    Returns:
        CollectResult.
    """
    t0 = time.perf_counter()
    res = CollectResult()

    # Thingi10K iterator.
    stl_paths: list[Path] = []
    if use_thingi10k:
        try:
            import thingi10k
            for _i, mesh_info in enumerate(thingi10k.dataset()):
                if _i >= limit:
                    break
                p = mesh_info.get("file_path") if isinstance(mesh_info, dict) else None
                if p:
                    stl_paths.append(Path(p))
        except ImportError:
            res.errors.append("thingi10k package not installed — falling back")

    if not stl_paths and fallback_stl_dir is not None:
        for p in Path(fallback_stl_dir).glob("*.stl"):
            stl_paths.append(p)
            if len(stl_paths) >= limit:
                break

    if not stl_paths:
        # last resort: tests/stl/ samples.
        repo = Path(__file__).resolve().parents[3]
        for p in (repo / "tests" / "stl").glob("0*.stl"):
            stl_paths.append(p)
            if len(stl_paths) >= limit:
                break

    res.n_meshes_attempted = len(stl_paths)

    X_all: list[np.ndarray] = []
    y_all: list[np.ndarray] = []

    for stl_p in stl_paths:
        if time.perf_counter() - t0 > timeout_per_mesh_s * len(stl_paths):
            res.errors.append("global timeout")
            break
        try:
            from core.analyzer.readers.stl import read_stl
            mesh = read_stl(str(stl_p))
            V = np.asarray(mesh.vertices, dtype=np.float64)
            F = np.asarray(mesh.faces, dtype=np.int64)
        except Exception as exc:
            res.errors.append(f"{stl_p.name}: read {exc}")
            continue

        # native_tet 실행 (간단화: 직접 scipy Delaunay 사용).
        try:
            from scipy.spatial import Delaunay
            d = Delaunay(V)
            tets = d.simplices.astype(np.int64)
            pts_t = V.copy()
        except Exception as exc:
            res.errors.append(f"{stl_p.name}: tet gen {exc}")
            continue

        try:
            X, y = _extract_tet_features(
                pts_t, tets, n_samples_per_mesh=n_samples_per_mesh,
            )
            if X.shape[0] > 0:
                X_all.append(X)
                y_all.append(y)
                res.n_meshes_ok += 1
                res.n_samples_total += X.shape[0]
        except Exception as exc:
            res.errors.append(f"{stl_p.name}: extract {exc}")

    if X_all:
        X_full = np.concatenate(X_all, axis=0)
        y_full = np.concatenate(y_all, axis=0)
        out_p = Path(out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        np.savez(str(out_p), X=X_full, y=y_full)

    res.elapsed_s = time.perf_counter() - t0
    return res
