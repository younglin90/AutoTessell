"""K6 / beta2638 — Tier plugin discovery system.

사용자가 외부 .py 파일로 custom Tier 등록 가능.
plugin 파일 규약:
    1. AUTO_TESSELL_TIER 변수 (str) — tier name.
    2. generate(V, F, work_dir, **kwargs) → result-like object 함수.
    3. (optional) AUTO_TESSELL_FALLBACK_AFTER (list[str]) — 의존하는 selectable tier.

discovery 경로:
    - env AUTO_TESSELL_PLUGINS_DIR (default: ~/.auto-tessell/plugins).
    - 모든 .py 파일 import + 위 규약 검증.
"""
from __future__ import annotations

import importlib.util
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)


@dataclass
class TierPlugin:
    """등록된 plugin 메타."""

    name: str
    path: Path
    generate_fn: Callable
    fallback_after: list[str] = field(default_factory=list)
    description: str = ""


def _default_plugin_dir() -> Path:
    return Path(os.environ.get(
        "AUTO_TESSELL_PLUGINS_DIR",
        str(Path.home() / ".auto-tessell" / "plugins"),
    ))


def discover_plugins(
    plugin_dir: Path | str | None = None,
) -> list[TierPlugin]:
    """plugin_dir 의 .py 파일 → TierPlugin list."""
    pdir = Path(plugin_dir) if plugin_dir else _default_plugin_dir()
    plugins: list[TierPlugin] = []

    if not pdir.exists() or not pdir.is_dir():
        return plugins

    for py_file in sorted(pdir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"autotessell_plugin_{py_file.stem}", str(py_file),
            )
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as exc:
            log.warning(
                "plugin_load_failed", path=str(py_file), error=str(exc)[:120],
            )
            continue

        # 규약 검증.
        tier_name = getattr(mod, "AUTO_TESSELL_TIER", None)
        gen_fn = getattr(mod, "generate", None)
        if not isinstance(tier_name, str) or not callable(gen_fn):
            log.debug(
                "plugin_invalid", path=str(py_file),
                has_name=bool(tier_name), has_generate=callable(gen_fn),
            )
            continue

        plugins.append(TierPlugin(
            name=tier_name,
            path=py_file,
            generate_fn=gen_fn,
            fallback_after=list(getattr(mod, "AUTO_TESSELL_FALLBACK_AFTER", []) or []),
            description=getattr(mod, "__doc__", "") or "",
        ))

    return plugins


def list_plugin_names(plugin_dir: Path | str | None = None) -> list[str]:
    """간편 — plugin tier name list 만."""
    return [p.name for p in discover_plugins(plugin_dir)]


def example_plugin_template() -> str:
    """사용자가 새 plugin 작성 시 참고할 template."""
    return '''"""Custom AutoTessell tier plugin example."""
from __future__ import annotations

# 필수: tier 이름.
AUTO_TESSELL_TIER = "my_custom_tier"

# 선택: 이 tier 가 fallback 으로 적용될 위치 (e.g. "wildmesh" 다음).
AUTO_TESSELL_FALLBACK_AFTER = ["wildmesh"]


def generate(V, F, work_dir, **kwargs):
    """Custom mesh generator.

    Args:
        V: (N, 3) surface vertex coords.
        F: (M, 3) surface face indices.
        work_dir: pathlib.Path output directory.
        **kwargs: generator-specific params (quality, max_cells 등).

    Returns:
        result object with attributes:
          - success: bool
          - n_cells: int
          - elapsed: float
          - message: str
    """
    from dataclasses import dataclass

    @dataclass
    class CustomResult:
        success: bool = False
        n_cells: int = 0
        elapsed: float = 0.0
        message: str = ""

    return CustomResult(
        success=False,
        message="custom plugin not yet implemented",
    )
'''
