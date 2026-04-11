"""Backend-facing app version bridge."""

from __future__ import annotations

try:
    from core.version import APP_VERSION
except ModuleNotFoundError:
    APP_VERSION = "1.0.0"

