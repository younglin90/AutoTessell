"""엔진 정책 — 어떤 메쉬 엔진을 노출·허용할지 런타임 결정.

현재 상황:
- AutoTessell은 19+ 엔진을 지원하지만 상당수는 실험적·연구용 상태
- 도메인/라이선스 특화로 제한하고 싶은 경우가 있음 (예: "WildMesh만")

이 모듈은 정책을 한 곳에 모아:
- 활성 엔진 목록
- 기본 엔진
- GUI 표시 그룹
- Strategist auto 선택 시 폴백 허용 여부
를 런타임에서 전환 가능하게 한다.

영속화: ~/.autotessell/engine_policy.json
환경변수 override: AUTOTESSELL_ENGINE_POLICY (모드 키)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

_POLICY_DIR = Path.home() / ".autotessell"
_POLICY_FILE = _POLICY_DIR / "engine_policy.json"
_ENV_VAR = "AUTOTESSELL_ENGINE_POLICY"


@dataclass
class EnginePolicy:
    """활성 엔진 + 기본값 + 폴백 정책."""

    mode: str = "all"                  # "all" | "wildmesh_only" | "custom"
    allowed_tiers: list[str] = field(default_factory=list)
    default_tier: str = "auto"         # Strategist 무시할 때 기본값
    allow_strategist_fallback: bool = True  # 실패 시 다른 엔진으로 폴백 허용?

    def is_allowed(self, tier: str) -> bool:
        """이 정책에서 `tier`가 사용 가능한지."""
        if self.mode == "all":
            return True
        if tier == "auto":
            return True  # auto는 Strategist 경유 → 선택 시점에 다시 제한
        return tier in self.allowed_tiers

    def resolve_effective_tier(self, requested: str) -> str:
        """요청된 tier를 정책에 맞게 정규화. 허용 안되면 기본값으로 대체."""
        if self.is_allowed(requested):
            return requested
        return self.default_tier

    def fallback_order(self, selected: str, full_order: list[str]) -> list[str]:
        """정책이 허용하는 fallback 순서만 반환.

        wildmesh_only 모드: fallback 완전 차단 (빈 리스트) — 실패시 파이프라인 중단.
        """
        if not self.allow_strategist_fallback:
            return []
        if self.mode == "all":
            return [t for t in full_order if t != selected]
        return [t for t in full_order if t != selected and t in self.allowed_tiers]


# ── 프리셋 정책 ─────────────────────────────────────────────────────────

_WILDMESH_TIERS = ["tier_wildmesh"]  # 단일 엔진

_PRESETS: dict[str, EnginePolicy] = {
    "all": EnginePolicy(
        mode="all",
        allowed_tiers=[],
        default_tier="auto",
        allow_strategist_fallback=True,
    ),
    "wildmesh_only": EnginePolicy(
        mode="wildmesh_only",
        allowed_tiers=list(_WILDMESH_TIERS),
        default_tier="tier_wildmesh",
        allow_strategist_fallback=False,  # 실패를 감춰서는 안됨 — 가시성 최우선
    ),
}


def load() -> EnginePolicy:
    """현재 정책 로드. 우선순위: ENV > 파일 > 기본 'all'."""
    # 1) 환경변수
    env = os.environ.get(_ENV_VAR)
    if env and env in _PRESETS:
        return _PRESETS[env]

    # 2) 영속 파일
    if _POLICY_FILE.exists():
        try:
            data = json.loads(_POLICY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                mode = data.get("mode", "all")
                if mode in _PRESETS:
                    return _PRESETS[mode]
                # custom 모드: 파일에 저장된 allowed_tiers 사용
                if mode == "custom":
                    return EnginePolicy(
                        mode="custom",
                        allowed_tiers=list(data.get("allowed_tiers", [])),
                        default_tier=str(data.get("default_tier", "auto")),
                        allow_strategist_fallback=bool(
                            data.get("allow_strategist_fallback", True)
                        ),
                    )
        except Exception:
            pass

    # 3) 기본
    return _PRESETS["all"]


def save(policy: EnginePolicy) -> None:
    """정책 영속화."""
    try:
        _POLICY_DIR.mkdir(parents=True, exist_ok=True)
        _POLICY_FILE.write_text(
            json.dumps(
                {
                    "mode": policy.mode,
                    "allowed_tiers": policy.allowed_tiers,
                    "default_tier": policy.default_tier,
                    "allow_strategist_fallback": policy.allow_strategist_fallback,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def set_mode(mode: str) -> EnginePolicy:
    """프리셋 모드로 전환하고 저장."""
    if mode not in _PRESETS:
        raise ValueError(f"알 수 없는 모드: {mode}")
    policy = _PRESETS[mode]
    save(policy)
    return policy


def available_modes() -> list[str]:
    return list(_PRESETS.keys())
