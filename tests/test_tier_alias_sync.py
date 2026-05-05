"""`_TIER_ALIASES` (pipeline.py) 와 `_HINT_MAP` (tier_selector.py) 동기화 검증.

두 곳에 거의 동일한 매핑이 있어 한 쪽 추가 시 다른 쪽에서 누락되기 쉽다.
이 테스트는 drift 방지용 — 새 tier 추가 시 두 map 동시에 업데이트해야 통과.
"""
from __future__ import annotations


def test_tier_aliases_match_hint_map() -> None:
    """pipeline._TIER_ALIASES 와 strategist._HINT_MAP 이 동일한 alias → canonical 매핑을 가져야 한다."""
    from core.generator.pipeline import _TIER_ALIASES
    from core.strategist.tier_selector import _HINT_MAP

    # 'auto' 는 HINT_MAP 에만 있음 (orchestrator 경로용) — 허용 예외.
    allowed_only_in_hint = {"auto"}
    # 'robust_hex_mesh' 는 pipeline 에만 있는 legacy alias — 허용
    allowed_only_in_alias = {"robust_hex_mesh"}

    pipeline_keys = set(_TIER_ALIASES.keys()) - allowed_only_in_alias
    hint_keys = set(_HINT_MAP.keys()) - allowed_only_in_hint

    missing_in_hint = pipeline_keys - hint_keys
    missing_in_alias = hint_keys - pipeline_keys

    assert not missing_in_hint, (
        f"_TIER_ALIASES 에만 있고 _HINT_MAP 에 없는 key: {sorted(missing_in_hint)}\n"
        "→ core/strategist/tier_selector.py 의 _HINT_MAP 에 추가하세요."
    )
    assert not missing_in_alias, (
        f"_HINT_MAP 에만 있고 _TIER_ALIASES 에 없는 key: {sorted(missing_in_alias)}\n"
        "→ core/generator/pipeline.py 의 _TIER_ALIASES 에 추가하세요."
    )

    # 공통 key 의 target 이 일치하는지
    for k in pipeline_keys & hint_keys:
        assert _TIER_ALIASES[k] == _HINT_MAP[k], (
            f"alias '{k}' 매핑 불일치: "
            f"pipeline → '{_TIER_ALIASES[k]}', selector → '{_HINT_MAP[k]}'"
        )


def test_all_aliases_resolve_to_registered_tier() -> None:
    """모든 alias 의 target 이 _TIER_REGISTRY 에 실제로 등록되어 있어야 한다."""
    from core.generator.pipeline import _TIER_ALIASES, _TIER_REGISTRY

    for alias, target in _TIER_ALIASES.items():
        if target == "auto":
            continue
        assert target in _TIER_REGISTRY, (
            f"alias '{alias}' → '{target}' 가 _TIER_REGISTRY 에 없음."
        )


def test_canonical_tier_helper() -> None:
    """canonical_tier() 헬퍼가 alias 와 canonical 모두 올바르게 resolve 해야 한다."""
    from core.strategist.tier_selector import canonical_tier

    cases = [
        ("wildmesh", "tier_wildmesh"),
        ("tier_wildmesh", "tier_wildmesh"),
        ("cfmesh", "tier15_cfmesh"),
        ("hex_classy", "tier_hex_classy_blocks"),
        ("salome", "tier_salome_smesh"),
        ("smesh", "tier_salome_smesh"),
        ("meshkit", "tier_meshkit"),
        ("hexpress", "tier_su2_hexpress"),
        ("polyhedral", "tier_polyhedral"),
        ("auto", "auto"),
    ]
    for alias, expected in cases:
        actual = canonical_tier(alias)
        assert actual == expected, (
            f"canonical_tier('{alias}') → '{actual}', expected '{expected}'"
        )
