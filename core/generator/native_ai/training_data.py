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

    # 8-dim context (1-ring stats — AI-V1.1.1 real impl).
    if include_context:
        # 1: incident tet count for vertex a
        # 2: incident tet count for vertex b
        # 3: incident tet count for vertex c
        # 4: incident tet count for vertex d
        # 5: 4 face area mean
        # 6: 4 face area std
        # 7: 4 dihedral angle min (cosine)
        # 8: 4 dihedral angle max (cosine)
        verts_in_tet = (
            (tets == a).any(axis=1)
            | (tets == b).any(axis=1)
            | (tets == c).any(axis=1)
            | (tets == d).any(axis=1)
        )
        n_incident_a = int((tets == a).any(axis=1).sum())
        n_incident_b = int((tets == b).any(axis=1).sum())
        n_incident_c = int((tets == c).any(axis=1).sum())
        n_incident_d = int((tets == d).any(axis=1).sum())

        # 4 face areas
        f1 = 0.5 * float(np.linalg.norm(np.cross(p_b - p_a, p_c - p_a)))
        f2 = 0.5 * float(np.linalg.norm(np.cross(p_b - p_a, p_d - p_a)))
        f3 = 0.5 * float(np.linalg.norm(np.cross(p_c - p_a, p_d - p_a)))
        f4 = 0.5 * float(np.linalg.norm(np.cross(p_c - p_b, p_d - p_b)))
        face_areas = np.array([f1, f2, f3, f4])

        # 4 dihedral angles (cosines along edges 0-1, 0-2, 0-3, 1-2)
        # via face normals.
        n1 = np.cross(p_b - p_a, p_c - p_a)
        n2 = np.cross(p_b - p_a, p_d - p_a)
        n3 = np.cross(p_c - p_a, p_d - p_a)
        n4 = np.cross(p_c - p_b, p_d - p_b)
        n1_norm = float(np.linalg.norm(n1)) + 1e-30
        n2_norm = float(np.linalg.norm(n2)) + 1e-30
        n3_norm = float(np.linalg.norm(n3)) + 1e-30
        n4_norm = float(np.linalg.norm(n4)) + 1e-30
        cos_d1 = float(np.dot(n1, n2)) / (n1_norm * n2_norm)
        cos_d2 = float(np.dot(n1, n3)) / (n1_norm * n3_norm)
        cos_d3 = float(np.dot(n2, n3)) / (n2_norm * n3_norm)
        cos_d4 = float(np.dot(n1, n4)) / (n1_norm * n4_norm)
        dihedrals = np.array([cos_d1, cos_d2, cos_d3, cos_d4])

        context_8 = np.array([
            float(n_incident_a),
            float(n_incident_b),
            float(n_incident_c),
            float(n_incident_d),
            float(face_areas.mean()),
            float(face_areas.std()),
            float(dihedrals.min()),
            float(dihedrals.max()),
        ], dtype=np.float64)
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


def extract_tet_features_v2(
    pts: np.ndarray,
    tets: np.ndarray,
    tet_idx: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """H5 / beta2614 — V2 feature extractor with curvature 4-dim.

    Returns (coords_12, context_8, curvature_4, quality).
        curvature_4 = [
            mean_radius_of_curvature_per_edge,
            edge_length_ratio (max/min),
            volume_to_inscribed_sphere_ratio,
            dihedral_variance,
        ]

    이전 V1 (extract_tet_features) 와 backward-compatible — V1 호출 그대로
    동작. V2 는 학습 시 24-dim 입력 (= 12+8+4) 의 새 model 용.
    """
    coords_12, context_8, quality = extract_tet_features(pts, tets, tet_idx)
    a, b, c, d = tets[tet_idx]
    p_a, p_b, p_c, p_d = pts[a], pts[b], pts[c], pts[d]

    # edge 길이.
    e01 = float(np.linalg.norm(p_b - p_a))
    e02 = float(np.linalg.norm(p_c - p_a))
    e03 = float(np.linalg.norm(p_d - p_a))
    e12 = float(np.linalg.norm(p_c - p_b))
    e13 = float(np.linalg.norm(p_d - p_b))
    e23 = float(np.linalg.norm(p_d - p_c))
    edges = np.array([e01, e02, e03, e12, e13, e23])
    edge_min = float(edges.min()) + 1e-30
    edge_max = float(edges.max())
    edge_ratio = edge_max / edge_min

    # tet volume.
    vol6 = float(np.cross(p_b - p_a, p_c - p_a) @ (p_d - p_a))
    vol = abs(vol6) / 6.0

    # 4 face areas (재계산 — context_8 의 평균과 다른 raw 값 필요).
    f1 = 0.5 * float(np.linalg.norm(np.cross(p_b - p_a, p_c - p_a)))
    f2 = 0.5 * float(np.linalg.norm(np.cross(p_b - p_a, p_d - p_a)))
    f3 = 0.5 * float(np.linalg.norm(np.cross(p_c - p_a, p_d - p_a)))
    f4 = 0.5 * float(np.linalg.norm(np.cross(p_c - p_b, p_d - p_b)))
    surf_total = f1 + f2 + f3 + f4

    # inscribed sphere radius r = 3V / S_total.
    r_in = 3.0 * vol / max(surf_total, 1e-30)
    # volume-to-inscribed-sphere ratio (정사면체 = 3√3 ≈ 5.196).
    sphere_vol = (4.0 / 3.0) * np.pi * (r_in ** 3)
    vol_ratio = float(vol / max(sphere_vol, 1e-30))

    # mean curvature 추정: surface area 의 sum / mean edge length.
    # 정사면체 면 4개 → curvature ~ 1/r_in.
    mean_curv = 1.0 / max(r_in, 1e-30) * float(np.mean(edges))

    # dihedral variance (context_8 has min/max — variance 추가).
    n1 = np.cross(p_b - p_a, p_c - p_a)
    n2 = np.cross(p_b - p_a, p_d - p_a)
    n3 = np.cross(p_c - p_a, p_d - p_a)
    n4 = np.cross(p_c - p_b, p_d - p_b)
    n1_n = float(np.linalg.norm(n1)) + 1e-30
    n2_n = float(np.linalg.norm(n2)) + 1e-30
    n3_n = float(np.linalg.norm(n3)) + 1e-30
    n4_n = float(np.linalg.norm(n4)) + 1e-30
    dihedrals = np.array([
        float(np.dot(n1, n2)) / (n1_n * n2_n),
        float(np.dot(n1, n3)) / (n1_n * n3_n),
        float(np.dot(n2, n3)) / (n2_n * n3_n),
        float(np.dot(n1, n4)) / (n1_n * n4_n),
    ])
    dihedral_var = float(dihedrals.var())

    curvature_4 = np.array([
        mean_curv, edge_ratio, vol_ratio, dihedral_var,
    ], dtype=np.float64)

    return coords_12, context_8, curvature_4, quality


def augment_features_with_rotations(
    coords_12: np.ndarray,
    context_8: np.ndarray,
    quality: np.ndarray,
    *,
    n_rotations: int = 4,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """K3 / beta2635 — random rotation augmentation (rotation-invariance).

    coords_12 = 4 vertex × 3 coord (centroid-centered). 임의 rotation 후 quality 보존.
    각 sample 을 n_rotations 배로 증강. context_8 / quality 는 rotation-invariant
    (incident counts / face areas / dihedral cosines) → 그대로 복제.

    Args:
        coords_12: (K, 12).
        context_8: (K, 8).
        quality: (K,).
        n_rotations: 1 sample 당 추가 random rotation 수 (1=원본 유지, 4=4× 증강).
        seed: RNG seed.

    Returns:
        (coords_aug, context_aug, quality_aug) — shapes (K*n_rot, 12 / 8 / 1).
    """
    K = int(coords_12.shape[0])
    if K == 0 or n_rotations < 1:
        return coords_12.copy(), context_8.copy(), quality.copy()

    rng = np.random.default_rng(seed)

    coords_list = [coords_12.copy()]
    context_list = [context_8.copy()]
    quality_list = [quality.copy()]

    for r in range(n_rotations - 1):
        # 임의 rotation matrix via QR decomposition (uniform on SO(3)).
        rand = rng.standard_normal((3, 3))
        q, _ = np.linalg.qr(rand)
        if np.linalg.det(q) < 0:
            q[:, 0] = -q[:, 0]  # 반사 방지 (proper rotation).

        # coords_12 의 4 vertex × 3 → reshape, rotate, reshape back.
        cv = coords_12.reshape(K, 4, 3)  # (K, 4, 3).
        rotated = cv @ q.T  # (K, 4, 3) @ (3, 3).T → (K, 4, 3).
        rot_flat = rotated.reshape(K, 12)
        coords_list.append(rot_flat)
        # context / quality 는 rotation-invariant.
        context_list.append(context_8.copy())
        quality_list.append(quality.copy())

    return (
        np.concatenate(coords_list, axis=0),
        np.concatenate(context_list, axis=0),
        np.concatenate(quality_list, axis=0),
    )


def generate_dataset_from_meshes(
    output_path: str,
    mesh_pts_list: list[np.ndarray],
    mesh_tets_list: list[np.ndarray],
    *,
    samples_per_mesh: int = 100,
    seed: int = 42,
    augment_rotations: int = 1,
) -> DatasetGenResult:
    """ML training dataset 실제 생성 (AI-V1.1.2).

    각 mesh 에서 random tet samples_per_mesh 개 추출 → features + quality.
    .npz 로 저장: arrays coords (K, 12), context (K, 8), quality (K,).

    Args:
        output_path: .npz 경로.
        mesh_pts_list: list of (N_i, 3) vertex arrays.
        mesh_tets_list: list of (T_i, 4) tet arrays.
        samples_per_mesh: per-mesh random sample count.
        seed: random seed.

    Returns:
        DatasetGenResult.
    """
    import time
    from pathlib import Path
    t0 = time.perf_counter()

    if len(mesh_pts_list) != len(mesh_tets_list):
        return DatasetGenResult(
            success=False,
            output_path=output_path,
            elapsed=time.perf_counter() - t0,
            message="mesh_pts_list / mesh_tets_list length mismatch",
        )

    rng = np.random.default_rng(seed)
    coords_all: list[np.ndarray] = []
    contexts_all: list[np.ndarray] = []
    quals_all: list[np.ndarray] = []
    n_used = 0

    for mi, (pts, tets) in enumerate(zip(mesh_pts_list, mesh_tets_list)):
        T = int(tets.shape[0])
        if T == 0:
            continue
        # Random select samples_per_mesh tet (with replacement OK for small T).
        n_take = min(samples_per_mesh, T)
        idx = rng.choice(T, size=n_take, replace=False)
        try:
            c12, c8, q = extract_features_batch(pts, tets, idx)
            coords_all.append(c12)
            contexts_all.append(c8)
            quals_all.append(q)
            n_used += int(n_take)
        except Exception as exc:
            # skip problematic mesh
            continue

    if not coords_all:
        return DatasetGenResult(
            success=False,
            output_path=output_path,
            elapsed=time.perf_counter() - t0,
            message="0 samples extracted (all meshes failed)",
        )

    coords_arr = np.concatenate(coords_all, axis=0)
    contexts_arr = np.concatenate(contexts_all, axis=0)
    quals_arr = np.concatenate(quals_all, axis=0)

    # K3 / beta2635 — optional rotation augmentation.
    if augment_rotations > 1:
        coords_arr, contexts_arr, quals_arr = augment_features_with_rotations(
            coords_arr, contexts_arr, quals_arr,
            n_rotations=augment_rotations, seed=seed,
        )
        n_used = int(coords_arr.shape[0])

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        str(out),
        coords=coords_arr,
        context=contexts_arr,
        quality=quals_arr,
    )
    return DatasetGenResult(
        success=True,
        n_samples=n_used,
        output_path=str(out),
        elapsed=time.perf_counter() - t0,
        message=f"saved {n_used} samples to {out}",
    )


def generate_dataset_skeleton(
    output_path: str,
    *,
    n_samples: int = 10000,
    seed: int = 42,
) -> DatasetGenResult:
    """Legacy skeleton API. 실제 구현은 generate_dataset_from_meshes 사용."""
    import time
    t0 = time.perf_counter()
    return DatasetGenResult(
        success=False,
        n_samples=0,
        output_path=output_path,
        elapsed=time.perf_counter() - t0,
        message=(
            f"AI-V1.1 dataset generator not yet implemented. "
            f"Target: n_samples={n_samples} (placeholder). "
            f"Use generate_dataset_from_meshes() for real generation."
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
