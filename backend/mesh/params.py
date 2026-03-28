"""
MeshParams — user-configurable mesh generation parameters.

Standard mode: only target_cells + mesh_purpose.
Pro mode: full control over each tier's quality/size knobs.

All fields have sensible defaults so callers can override only what they need.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MeshParams:
    # -----------------------------------------------------------------------
    # pytetwild  (dev pipeline + Tier 2 fallback)
    # -----------------------------------------------------------------------
    # Quality energy threshold. Lower = better quality, longer runtime.
    # pytetwild default is ~10.  Practical range: 1 (high quality) – 50 (fast).
    tet_stop_energy: float = 10.0

    # Edge length factor override. None = auto-calculated from target_cells.
    # Fraction of bbox diagonal per edge: 0.02 (fine) – 0.20 (coarse).
    tet_edge_length_fac: float | None = None

    # -----------------------------------------------------------------------
    # snappyHexMesh  (Tier 1, CFD)
    # -----------------------------------------------------------------------
    # Surface refinement level range. None = auto from STL complexity analysis.
    snappy_refine_min: int | None = None   # 0 – 4
    snappy_refine_max: int | None = None   # 1 – 6

    # Number of boundary-layer (prism) cells grown from the wall. 0 = disabled.
    snappy_n_layers: int | None = None     # None = auto (3 simple / 5 complex)

    # Layer thickness growth ratio (each layer / previous layer).
    snappy_expansion_ratio: float = 1.2   # 1.1 – 1.5

    # Final (outermost) layer thickness relative to neighbouring cell.
    snappy_final_layer_thickness: float = 0.3  # 0.1 – 0.5

    # Mesh quality gate: max non-orthogonality angle.
    snappy_max_non_ortho: float = 70.0    # 60 – 85

    # -----------------------------------------------------------------------
    # Netgen  (Tier 0.5)
    # -----------------------------------------------------------------------
    # maxh = characteristic_length / netgen_maxh_ratio
    # Higher ratio → finer mesh (more cells).
    netgen_maxh_ratio: float = 15.0       # 5 – 40

    # -----------------------------------------------------------------------
    # MMG post-processing  (applied after pytetwild when mmg3d is in PATH)
    # -----------------------------------------------------------------------
    mmg_enabled: bool = True

    # Hausdorff distance (surface approximation): smaller = more faithful surface.
    # 0 = auto (L/50).  Practical: 0.001 – 0.1 (relative to bbox).
    mmg_hausd: float | None = None

    # Size gradation between adjacent elements: 1.0 (uniform) – 3.0 (rapid change).
    mmg_hgrad: float = 1.3

    # -----------------------------------------------------------------------
    # (de)serialisation helpers
    # -----------------------------------------------------------------------

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MeshParams":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_json(cls, s: str) -> "MeshParams":
        return cls.from_dict(json.loads(s))

    @classmethod
    def default(cls) -> "MeshParams":
        return cls()
