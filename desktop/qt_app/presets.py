"""파이프라인 프리셋 — 자주 쓰는 품질 레벨/엔진/파라미터 조합.

CFD 도메인 전형 (외부 유동/내부 유동/공기역학 등)에 맞춘 5종 기본 제공.
사용자 정의는 ~/.autotessell/presets.json 에 저장.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

_PRESETS_DIR = Path.home() / ".autotessell"
_USER_PRESETS_FILE = _PRESETS_DIR / "presets.json"


@dataclass
class Preset:
    """하나의 프리셋 = 품질 + 엔진 + 파라미터 묶음."""

    name: str
    description: str
    quality_level: str              # "draft" | "standard" | "fine"
    tier_hint: str                  # "auto" | "tier2_tetwild" | "tier05_netgen" | ...
    remesh_engine: str = "auto"     # "auto" | "pyacvd" | "geogram" | "mmg"
    surface_remesh: bool = False
    allow_ai_fallback: bool = False
    params: dict = field(default_factory=dict)


# 내장 프리셋 (CFD 도메인 기준)
BUILTIN_PRESETS: list[Preset] = [
    Preset(
        name="Draft Quick (Tet)",
        description="빠른 점검용 TetWild. 품질보다 속도. ~수초",
        quality_level="draft",
        tier_hint="tier2_tetwild",
        params={"epsilon": 0.002, "edge_length": 0.16, "stop_energy": 10.0},
    ),
    Preset(
        name="Standard External (Tet)",
        description="외부 유동 기본. Netgen tet. 풍동 도메인 자동 생성. ~수분",
        quality_level="standard",
        tier_hint="tier05_netgen",
        surface_remesh=True,
        remesh_engine="auto",
    ),
    Preset(
        name="Standard Internal (Hex-dom)",
        description="내부 유동 (배관/덕트). cfMesh hex-dominant. ~수분",
        quality_level="standard",
        tier_hint="tier15_cfmesh",
    ),
    Preset(
        name="Fine Aerospace (BL)",
        description="항공기/외부 공력. snappyHexMesh + 경계층. 고품질 ~30분+",
        quality_level="fine",
        tier_hint="tier1_snappy",
        surface_remesh=True,
        params={"bl_layers": 5, "bl_expansion_ratio": 1.2},
    ),
    Preset(
        name="Fine Internal (Hex BL)",
        description="펌프/임펠러. cfMesh hex + 얇은 경계층. ~20분+",
        quality_level="fine",
        tier_hint="tier15_cfmesh",
        params={"bl_layers": 3, "bl_expansion_ratio": 1.3},
    ),
]


def all_presets() -> list[Preset]:
    """내장 + 사용자 정의 프리셋 전부 반환."""
    return BUILTIN_PRESETS + _load_user_presets()


def get(name: str) -> Preset | None:
    """이름으로 프리셋 조회. 없으면 None."""
    for p in all_presets():
        if p.name == name:
            return p
    return None


def _load_user_presets() -> list[Preset]:
    if not _USER_PRESETS_FILE.exists():
        return []
    try:
        data = json.loads(_USER_PRESETS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [Preset(**item) for item in data if isinstance(item, dict)]
    except Exception:
        pass
    return []


def save_user_preset(preset: Preset) -> None:
    """사용자 정의 프리셋 저장 (같은 이름이면 덮어쓰기)."""
    existing = _load_user_presets()
    existing = [p for p in existing if p.name != preset.name]
    existing.append(preset)
    try:
        _PRESETS_DIR.mkdir(parents=True, exist_ok=True)
        _USER_PRESETS_FILE.write_text(
            json.dumps([asdict(p) for p in existing], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass
