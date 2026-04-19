"""GUI 시각 회귀 — 헤드리스 Qt widget.grab() PNG baseline 비교."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.visual

_BASELINE_DIR = Path(__file__).parent / "fixtures" / "screenshots" / "baselines"
_ACTUAL_DIR = Path(__file__).parent / "fixtures" / "screenshots" / "actual"
_PIXEL_TOLERANCE = 0.02


def _compare_or_save(widget, name: str, size: tuple[int, int] = (1400, 900)) -> None:
    """widget을 캡처하고 baseline이 있으면 픽셀 차이를 비교한다."""
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

    _ACTUAL_DIR.mkdir(parents=True, exist_ok=True)
    widget.resize(*size)
    widget.show()
    QApplication.processEvents()

    pix = widget.grab()
    actual = _ACTUAL_DIR / f"{name}.png"
    assert pix.save(str(actual), "PNG"), f"actual screenshot 저장 실패: {actual}"

    baseline = _BASELINE_DIR / f"{name}.png"
    if not baseline.exists():
        _BASELINE_DIR.mkdir(parents=True, exist_ok=True)
        assert pix.save(str(baseline), "PNG"), f"baseline 저장 실패: {baseline}"
        pytest.skip(f"baseline 새로 생성: {baseline}")

    a_img = QImage(str(actual)).convertToFormat(QImage.Format.Format_RGB32)
    b_img = QImage(str(baseline)).convertToFormat(QImage.Format.Format_RGB32)
    if a_img.size() != b_img.size():
        pytest.fail(f"크기 불일치: actual={a_img.size()} baseline={b_img.size()}")

    changed = 0
    total_channels = a_img.width() * a_img.height() * 3
    for y in range(a_img.height()):
        for x in range(a_img.width()):
            a = a_img.pixelColor(x, y)
            b = b_img.pixelColor(x, y)
            changed += int(abs(a.red() - b.red()) > 10)
            changed += int(abs(a.green() - b.green()) > 10)
            changed += int(abs(a.blue() - b.blue()) > 10)

    diff_ratio = changed / total_channels if total_channels else 0.0
    if diff_ratio > _PIXEL_TOLERANCE:
        pytest.fail(
            f"{name}: pixel diff {diff_ratio * 100:.2f}% > "
            f"{_PIXEL_TOLERANCE * 100:.2f}%. actual={actual}, baseline={baseline}"
        )


@pytest.fixture(scope="module")
def qt_app():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_visual_empty_mainwindow(qt_app, monkeypatch) -> None:
    """빈 메인 윈도우 — DropZone 초기 상태."""
    from desktop.qt_app import mesh_viewer
    from desktop.qt_app.main_window import AutoTessellWindow

    monkeypatch.setattr(mesh_viewer, "PYVISTAQT_AVAILABLE", False)
    win = AutoTessellWindow()
    win._build()
    _compare_or_save(win._qmain, "01_empty_mainwindow")


def test_visual_wildmesh_param_panel_draft(qt_app) -> None:
    """WildMesh 슬라이더 패널 draft 프리셋."""
    from desktop.qt_app.widgets.wildmesh_param_panel import WildMeshParamPanel

    panel = WildMeshParamPanel()
    panel.apply_preset("draft")
    _compare_or_save(panel, "02_wildmesh_panel_draft", size=(280, 300))


def test_visual_wildmesh_param_panel_fine(qt_app) -> None:
    """WildMesh 슬라이더 패널 fine 프리셋."""
    from desktop.qt_app.widgets.wildmesh_param_panel import WildMeshParamPanel

    panel = WildMeshParamPanel()
    panel.apply_preset("fine")
    _compare_or_save(panel, "03_wildmesh_panel_fine", size=(280, 300))


def test_visual_batch_dialog_empty(qt_app) -> None:
    """배치 다이얼로그 초기 상태."""
    from desktop.qt_app.batch_dialog import BatchDialog

    d = BatchDialog()
    _compare_or_save(d, "04_batch_dialog_empty", size=(960, 640))


def test_visual_history_dialog_empty(qt_app, tmp_path, monkeypatch) -> None:
    """실행 이력 다이얼로그 empty 상태."""
    from desktop.qt_app import history

    monkeypatch.setattr(history, "_HISTORY_DIR", tmp_path / "x")
    monkeypatch.setattr(history, "_HISTORY_FILE", tmp_path / "x" / "h.json")

    from desktop.qt_app.history_dialog import HistoryDialog

    d = HistoryDialog()
    _compare_or_save(d, "05_history_dialog_empty", size=(960, 640))


def test_visual_error_recovery_watertight(qt_app) -> None:
    """에러 복구 다이얼로그 — watertight 패턴."""
    from desktop.qt_app.error_recovery import ErrorRecoveryDialog, classify_error

    classified = classify_error("WildMesh는 watertight surface를 요구합니다")
    assert classified is not None
    guide, actions = classified
    d = ErrorRecoveryDialog(
        error_message="test trace",
        guide_text=guide,
        actions=actions,
    )
    _compare_or_save(d, "06_error_recovery_watertight", size=(720, 520))


def test_visual_quality_pane_with_histogram(qt_app) -> None:
    """Quality 탭 — 히스토그램 3 subplot 샘플 데이터."""
    from desktop.qt_app.widgets.right_column import QualityPane

    pane = QualityPane()
    pane.histogram.update_histograms(
        aspect_data=[1.0 + 0.05 * i for i in range(200)],
        skew_data=[0.01 * i for i in range(200)],
        non_ortho_data=[10.0 + 0.3 * i for i in range(200)],
    )
    pane.set_metric("aspect", 0.3, "3.5")
    pane.set_metric("skew", 0.2, "0.4")
    pane.set_metric("nonortho", 0.5, "45.0")
    _compare_or_save(pane, "07_quality_pane_with_histogram", size=(360, 760))


def test_visual_keyboard_shortcuts(qt_app, monkeypatch) -> None:
    """키보드 단축키 관련 메인 윈도우 상태."""
    from desktop.qt_app import mesh_viewer
    from desktop.qt_app.main_window import AutoTessellWindow

    monkeypatch.setattr(mesh_viewer, "PYVISTAQT_AVAILABLE", False)
    win = AutoTessellWindow()
    win._build()
    _compare_or_save(win._qmain, "08_mainwindow_after_build", size=(1400, 900))


def test_visual_mainwindow_wildmesh_panel_visible(qt_app) -> None:
    """메인 윈도우 — tier=wildmesh 선택 후 WildMesh 튜닝 패널 표시."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    win._build()
    idx = win._engine_combo.findData("wildmesh")
    assert idx >= 0
    win._engine_combo.setCurrentIndex(idx)
    assert not win._wildmesh_param_frame.isHidden()
    _compare_or_save(win._qmain, "09_mainwindow_wildmesh_panel", size=(1400, 900))


def test_visual_engine_policy_wildmesh_only_dropdown(qt_app, tmp_path, monkeypatch) -> None:
    """엔진 정책 wildmesh_only — 드롭다운 정책 차단 마커."""
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app import engine_policy
    from desktop.qt_app.main_window import AutoTessellWindow

    monkeypatch.setattr(engine_policy, "_POLICY_DIR", tmp_path / "ep")
    monkeypatch.setattr(engine_policy, "_POLICY_FILE", tmp_path / "ep" / "policy.json")
    monkeypatch.delenv("AUTOTESSELL_ENGINE_POLICY", raising=False)
    engine_policy.set_mode("wildmesh_only")

    win = AutoTessellWindow()
    win._build()
    win._engine_combo.showPopup()
    QApplication.processEvents()
    view = win._engine_combo.view()
    view.resize(360, 520)
    view.show()
    _compare_or_save(view, "10_engine_policy_wildmesh_only_dropdown", size=(360, 520))


def test_visual_wildmesh_fine_preset_slider_sync(qt_app) -> None:
    """WildMesh Fine 프리셋 선택 후 슬라이더 패널 상태."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    win._build()
    idx = win._preset_combo.findData("WildMesh Fine (Feature Preserving)")
    assert idx >= 0
    win._preset_combo.setCurrentIndex(idx)
    _compare_or_save(
        win._wildmesh_param_panel,
        "11_wildmesh_fine_preset_slider_sync",
        size=(280, 300),
    )


def test_visual_mainwindow_after_file_load(
    qt_app, sphere_stl, tmp_path, monkeypatch
) -> None:
    """파일 로드 후 DropZone/상태 카드/geometry hint 상태."""
    from desktop.qt_app import recent_files
    from desktop.qt_app.main_window import AutoTessellWindow

    monkeypatch.setattr(recent_files, "_RECENT_DIR", tmp_path / "recent")
    monkeypatch.setattr(recent_files, "_RECENT_FILE", tmp_path / "recent" / "recent.json")

    win = AutoTessellWindow()
    win._build()
    win.set_input_path(sphere_stl)
    _compare_or_save(win._qmain, "12_mainwindow_after_file_load", size=(1400, 900))


def test_visual_compare_dialog_two_cases(qt_app, tmp_path) -> None:
    """Compare Mode — 두 case를 나란히 로드한 상태."""
    from desktop.qt_app.compare_dialog import CompareDialog

    case_a = tmp_path / "case_a"
    case_b = tmp_path / "case_b"
    for idx, case in enumerate((case_a, case_b), start=1):
        poly = case / "constant" / "polyMesh"
        poly.mkdir(parents=True)
        (poly / "points").write_text(f"dummy {idx}")

    dlg = CompareDialog()
    dlg.set_case_path("A", case_a)
    dlg.set_case_path("B", case_b)
    dlg.load_selected()
    _compare_or_save(dlg, "13_compare_dialog_two_cases", size=(960, 720))
