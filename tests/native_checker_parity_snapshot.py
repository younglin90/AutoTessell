"""Test-only immutable snapshot helper for Native/OpenFOAM parity."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class ParitySnapshot:
    case_dir: Path
    native: Any
    external: Any
    native_engine: str
    external_engine: str
    timings: dict[str, float]


def build_parity_snapshot(
    case_dir: Path,
    *,
    native_runner: Callable[[Path], Any],
    external_runner: Any,
    clock: Callable[[], float],
) -> ParitySnapshot:
    """Run each engine exactly once and reject a Native fallback as parity."""
    start = clock()
    native = native_runner(case_dir)
    native_seconds = clock() - start

    start = clock()
    external = external_runner.run(case_dir)
    external_seconds = clock() - start
    if getattr(external_runner, "last_engine_used", None) != "openfoam":
        raise RuntimeError("parity requires a verified external OpenFOAM result")

    return ParitySnapshot(
        case_dir=case_dir,
        native=native,
        external=external,
        native_engine="native",
        external_engine="openfoam",
        timings={"native_seconds": native_seconds, "external_seconds": external_seconds},
    )
