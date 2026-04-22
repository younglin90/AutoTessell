"""core/utils/visualizer.py smoke 테스트 (v0.4.0-beta21).

MeshVisualizer 는 optional 3rd-party (polyscope, k3d) 를 쓰므로 headless / 미설치
환경을 포괄. 렌더링 자체가 아니라 graceful fallback (None 반환, False 반환, 예외
없음) 을 검증.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.utils.visualizer import MeshVisualizer


def _cube():
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    F = np.array([
        [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
        [0, 4, 5], [0, 5, 1], [2, 6, 7], [2, 7, 3],
        [1, 5, 6], [1, 6, 2], [0, 3, 7], [0, 7, 4],
    ], dtype=np.int64)
    return V, F


def test_visualizer_is_importable_and_instantiable() -> None:
    """MeshVisualizer 가 import + 생성 가능."""
    v = MeshVisualizer()
    assert v is not None
    assert hasattr(v, "show")
    assert hasattr(v, "show_polyscope")
    assert hasattr(v, "show_k3d")
    assert hasattr(v, "save_screenshot")


def test_show_polyscope_graceful_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """polyscope 미설치/헤드리스 환경에서도 raise 없이 None 반환."""
    import core.utils.visualizer as viz  # noqa: PLC0415

    monkeypatch.setattr(viz, "_POLYSCOPE_AVAILABLE", False)
    monkeypatch.setattr(viz, "_ps", None)

    V, F = _cube()
    result = MeshVisualizer().show_polyscope(V, F, name="cube")
    assert result is None


def test_show_k3d_graceful_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """k3d 미설치 환경에서도 raise 없이 None 반환."""
    import core.utils.visualizer as viz  # noqa: PLC0415

    monkeypatch.setattr(viz, "_K3D_AVAILABLE", False)
    monkeypatch.setattr(viz, "_k3d", None)

    V, F = _cube()
    result = MeshVisualizer().show_k3d(V, F, name="cube")
    assert result is None


def test_save_screenshot_graceful_when_polyscope_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """polyscope 없을 때 save_screenshot 이 False 반환, 예외 없음."""
    import core.utils.visualizer as viz  # noqa: PLC0415

    monkeypatch.setattr(viz, "_POLYSCOPE_AVAILABLE", False)
    monkeypatch.setattr(viz, "_ps", None)

    V, F = _cube()
    out = tmp_path / "shot.png"
    result = MeshVisualizer().save_screenshot(V, F, out, name="cube")
    assert result is False
    assert not out.exists()


def test_show_dispatches_to_polyscope_outside_jupyter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """show() 가 Jupyter 아닐 때 show_polyscope 로 dispatch."""
    import core.utils.visualizer as viz  # noqa: PLC0415

    monkeypatch.setattr(viz, "_is_jupyter", lambda: False)

    dispatched: dict = {}

    def _fake_polyscope(self, vertices, faces, name="mesh"):  # noqa: ANN001
        dispatched["polyscope"] = name
        return "ps_ok"

    monkeypatch.setattr(MeshVisualizer, "show_polyscope", _fake_polyscope)
    V, F = _cube()
    result = MeshVisualizer().show(V, F, name="cube_test")
    assert result == "ps_ok"
    assert dispatched.get("polyscope") == "cube_test"


def test_show_dispatches_to_k3d_in_jupyter(monkeypatch: pytest.MonkeyPatch) -> None:
    """show() 가 Jupyter 환경에서 show_k3d 로 dispatch."""
    import core.utils.visualizer as viz  # noqa: PLC0415

    monkeypatch.setattr(viz, "_is_jupyter", lambda: True)

    dispatched: dict = {}

    def _fake_k3d(self, vertices, faces, name="mesh"):  # noqa: ANN001
        dispatched["k3d"] = name
        return "k3d_ok"

    monkeypatch.setattr(MeshVisualizer, "show_k3d", _fake_k3d)
    V, F = _cube()
    result = MeshVisualizer().show(V, F, name="cube_jupyter")
    assert result == "k3d_ok"
    assert dispatched.get("k3d") == "cube_jupyter"
