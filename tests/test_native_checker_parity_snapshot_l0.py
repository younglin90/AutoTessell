"""L0 tests for the test-only parity snapshot helper."""

from __future__ import annotations

import pytest

from tests.native_checker_parity_snapshot import build_parity_snapshot


class _Runner:
    def __init__(self, value: object, engine: str) -> None:
        self.value = value
        self.last_engine_used = engine
        self.calls = 0

    def run(self, case_dir: object) -> object:
        self.calls += 1
        return self.value


def test_snapshot_runs_each_engine_once_and_reuses_values() -> None:
    native_calls = []
    external = _Runner({"cells": 4}, "openfoam")
    snapshot = build_parity_snapshot(
        object(),
        native_runner=lambda case: native_calls.append(case) or {"cells": 4},
        external_runner=external,
        clock=iter([0.0, 0.2, 0.2, 0.7]).__next__,
    )
    assert len(native_calls) == 1
    assert external.calls == 1
    assert snapshot.native == snapshot.external == {"cells": 4}
    assert snapshot.native_engine == "native"
    assert snapshot.external_engine == "openfoam"
    assert snapshot.timings["native_seconds"] == pytest.approx(0.2)
    assert snapshot.timings["external_seconds"] == pytest.approx(0.5)


def test_snapshot_rejects_native_fallback() -> None:
    with pytest.raises(RuntimeError, match="verified external OpenFOAM"):
        build_parity_snapshot(
            object(),
            native_runner=lambda _case: {"cells": 1},
            external_runner=_Runner({"cells": 1}, "native"),
            clock=iter([0.0, 0.1, 0.1, 0.2]).__next__,
        )
