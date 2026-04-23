"""y⁺ 패널 (beta98) 테스트 — headless / unit.

Qt 없이 순수 로직만 검증하는 테스트가 기본.
Qt 가 필요한 테스트는 pytest-qt 가 있을 때만 실행 (pytest-qt 없으면 skip).
"""
from __future__ import annotations

import math
import pytest


# ---------------------------------------------------------------------------
# 순수 로직 테스트 (Qt 불필요)
# ---------------------------------------------------------------------------

def test_estimate_first_layer_thickness_import_no_error() -> None:
    """core.utils.yplus import 에러 없음."""
    from core.utils.yplus import estimate_first_layer_thickness  # noqa: F401
    assert callable(estimate_first_layer_thickness)


def test_estimate_air_10ms_yplus1_result() -> None:
    """공기 10 m/s, L=1 m, y+=1 → y_first 정합 값 확인."""
    from core.utils.yplus import estimate_first_layer_thickness
    r = estimate_first_layer_thickness(10.0, 1.0, fluid="air", y_plus_target=1.0)
    assert r.y_first > 0
    assert 1e-7 < r.y_first < 1e-3, f"y_first={r.y_first} 범위 초과"
    assert r.re_l == pytest.approx(10.0 * 1.0 / 1.516e-5, rel=0.01)
    assert r.cf > 0
    assert r.u_tau > 0


def test_estimate_yplus30_is_30x_yplus1() -> None:
    """y+=30 은 y+=1 의 30배."""
    from core.utils.yplus import estimate_first_layer_thickness
    r1 = estimate_first_layer_thickness(10.0, 1.0, y_plus_target=1.0)
    r30 = estimate_first_layer_thickness(10.0, 1.0, y_plus_target=30.0)
    assert r30.y_first == pytest.approx(r1.y_first * 30.0, rel=0.01)


def test_estimate_invalid_velocity_raises() -> None:
    from core.utils.yplus import estimate_first_layer_thickness
    with pytest.raises(ValueError, match="flow_velocity"):
        estimate_first_layer_thickness(0.0, 1.0)


def test_estimate_invalid_length_raises() -> None:
    from core.utils.yplus import estimate_first_layer_thickness
    with pytest.raises(ValueError, match="characteristic_length"):
        estimate_first_layer_thickness(10.0, -1.0)


def test_yplus_panel_module_importable_without_qt() -> None:
    """yplus_panel 모듈은 PySide6 없어도 import 할 때 즉시 crash 하지 않아야.
    (PySide6 가 설치된 환경에서는 정상 import, 없으면 ImportError 가 최대 허용.)
    """
    try:
        import desktop.qt_app.widgets.yplus_panel as _mod  # noqa: F401
        # PySide6 설치 환경: 클래스가 정의돼 있어야
        assert hasattr(_mod, "YPlusPanel")
    except ImportError:
        # PySide6 가 없는 순수 headless 환경 — ImportError 는 허용
        pytest.skip("PySide6 unavailable — skip Qt import test")


# ---------------------------------------------------------------------------
# Qt 통합 테스트 (pytest-qt 필요)
# ---------------------------------------------------------------------------

def _qt_available() -> bool:
    try:
        import PySide6  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _qt_available(), reason="PySide6 not installed")
def test_yplus_panel_instantiates(qtbot) -> None:
    """YPlusPanel 이 QApplication 없이 crash 하지 않고 인스턴스화."""
    from desktop.qt_app.widgets.yplus_panel import YPlusPanel
    panel = YPlusPanel()
    qtbot.addWidget(panel)
    assert panel is not None


@pytest.mark.skipif(not _qt_available(), reason="PySide6 not installed")
def test_yplus_panel_calculate_emits_signal(qtbot) -> None:
    """계산하기 버튼 클릭 시 bl_thickness_computed 시그널 발행."""
    from desktop.qt_app.widgets.yplus_panel import YPlusPanel
    panel = YPlusPanel()
    qtbot.addWidget(panel)

    received: list[float] = []
    panel.bl_thickness_computed.connect(received.append)

    # 기본값으로 계산 실행
    panel._on_calculate()

    assert len(received) == 1
    assert received[0] > 0
    assert math.isfinite(received[0])


@pytest.mark.skipif(not _qt_available(), reason="PySide6 not installed")
def test_yplus_panel_set_characteristic_length(qtbot) -> None:
    """set_characteristic_length 가 스핀박스를 업데이트."""
    from desktop.qt_app.widgets.yplus_panel import YPlusPanel
    panel = YPlusPanel()
    qtbot.addWidget(panel)

    panel.set_characteristic_length(2.5)
    assert panel._length_spin.value() == pytest.approx(2.5)


@pytest.mark.skipif(not _qt_available(), reason="PySide6 not installed")
def test_yplus_panel_result_label_updates(qtbot) -> None:
    """계산 후 결과 라벨이 '첫 층 두께' 텍스트 포함."""
    from desktop.qt_app.widgets.yplus_panel import YPlusPanel
    panel = YPlusPanel()
    qtbot.addWidget(panel)

    panel._on_calculate()
    assert "첫 층 두께" in panel._result_label.text()


@pytest.mark.skipif(not _qt_available(), reason="PySide6 not installed")
def test_yplus_panel_invalid_fluid_shows_error(qtbot, monkeypatch) -> None:
    """알 수 없는 유체 선택 시 결과 라벨에 [error] 표시."""
    from desktop.qt_app.widgets.yplus_panel import YPlusPanel
    panel = YPlusPanel()
    qtbot.addWidget(panel)

    # fluid combo 를 존재하지 않는 값으로 강제 지정
    panel._fluid_combo.addItem("helium")
    panel._fluid_combo.setCurrentText("helium")
    panel._on_calculate()

    assert "[error]" in panel._result_label.text()
