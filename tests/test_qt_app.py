"""Qt GUI scaffold 테스트.

QApplication 인스턴스 없이 클래스 정의만 검증한다.
헤드리스 환경(CI/CD, WSL 등)에서도 안전하게 실행된다.
"""
from __future__ import annotations

import pytest

# PySide6 없는 환경에서는 스킵
PySide6 = pytest.importorskip("PySide6")


# ---------------------------------------------------------------------------
# 테스트 1: AutoTessellWindow 클래스 존재 검증
# ---------------------------------------------------------------------------


def test_auto_tessell_window_class_exists() -> None:
    """AutoTessellWindow 클래스가 import 가능하고 기본 속성을 갖는다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    assert callable(AutoTessellWindow), "AutoTessellWindow 는 호출 가능해야 한다"
    assert hasattr(AutoTessellWindow, "SUPPORTED_EXTENSIONS"), (
        "SUPPORTED_EXTENSIONS 클래스 속성이 필요하다"
    )
    assert ".stl" in AutoTessellWindow.SUPPORTED_EXTENSIONS
    assert ".step" in AutoTessellWindow.SUPPORTED_EXTENSIONS


# ---------------------------------------------------------------------------
# 테스트 2: PipelineWorker 클래스 존재 및 시그널 검증
# ---------------------------------------------------------------------------


def test_pipeline_worker_class_exists() -> None:
    """PipelineWorker 클래스가 import 가능하다."""
    from desktop.qt_app import pipeline_worker as pw

    assert hasattr(pw, "PipelineWorker"), "PipelineWorker 가 모듈에 존재해야 한다"
    assert callable(pw.PipelineWorker)


# ---------------------------------------------------------------------------
# 테스트 3: set_input_path / get_input_path 메서드 존재 검증
# ---------------------------------------------------------------------------


def test_main_window_file_path_methods() -> None:
    """AutoTessellWindow 가 파일 경로 설정/조회 메서드를 갖는다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    assert hasattr(AutoTessellWindow, "set_input_path"), (
        "set_input_path 메서드가 필요하다"
    )
    assert hasattr(AutoTessellWindow, "get_input_path"), (
        "get_input_path 메서드가 필요하다"
    )
    assert callable(AutoTessellWindow.set_input_path)
    assert callable(AutoTessellWindow.get_input_path)

    # QApplication 없이 인스턴스 생성 후 경로 API 검증
    win = AutoTessellWindow()
    assert win.get_input_path() is None

    # 유효한 확장자 설정
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
        tmp_path = Path(f.name)

    try:
        win.set_input_path(tmp_path)
        assert win.get_input_path() == tmp_path.resolve()
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 테스트 4: QualityLevel enum 값 검증
# ---------------------------------------------------------------------------


def test_quality_level_enum_values() -> None:
    """QualityLevel enum 이 draft / standard / fine 세 값을 갖는다."""
    from desktop.qt_app.main_window import QualityLevel

    values = {lvl.value for lvl in QualityLevel}
    assert values == {"draft", "standard", "fine"}, (
        f"예상 값 집합과 다름: {values}"
    )

    # str 서브클래스여야 QComboBox currentText() 와 바로 비교 가능
    assert issubclass(QualityLevel, str)


# ---------------------------------------------------------------------------
# 테스트 5: PipelineWorker progress / finished 시그널 타입 검증
# ---------------------------------------------------------------------------


def test_pipeline_worker_signals() -> None:
    """_qt_class 에 progress(str) 와 finished(object) 시그널이 존재한다."""
    from desktop.qt_app import pipeline_worker as pw

    # _qt_class 는 최초 인스턴스 생성 시 만들어지므로 PySide6.QtCore.Signal 확인
    # 클래스 레벨에서 Signal 어노테이션 또는 속성 존재 여부만 확인한다
    # (QApplication 없이 QThread 서브클래스 인스턴스를 만들 수 없음)
    worker_cls = pw.PipelineWorker

    # __new__ 를 통해 동적으로 생성되므로 _qt_class 가 캐시되지 않을 수 있다.
    # 대신 모듈 수준에서 클래스가 올바르게 구성되는지 확인한다.
    assert hasattr(worker_cls, "__new__"), "PipelineWorker 는 __new__ 를 가져야 한다"

    # _qt_class 를 사전에 생성해 시그널 확인
    from PySide6.QtCore import QCoreApplication, QThread

    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])

    from pathlib import Path
    from desktop.qt_app.main_window import QualityLevel

    # 더미 경로(실제 파일 불필요 — 인스턴스만 생성)
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".stl") as f:
        tmp = Path(f.name)
        instance = worker_cls(tmp, QualityLevel.DRAFT)

    qt_cls = type(instance)
    assert issubclass(qt_cls, QThread), "PipelineWorker 인스턴스는 QThread 여야 한다"
    assert hasattr(qt_cls, "progress"), "progress 시그널이 필요하다"
    assert hasattr(qt_cls, "finished"), "finished 시그널이 필요하다"


def test_pipeline_worker_accepts_advanced_options() -> None:
    """PipelineWorker 가 고급 실행 옵션을 받아 내부 필드로 유지한다."""
    from pathlib import Path
    import tempfile

    from PySide6.QtCore import QCoreApplication
    from desktop.qt_app.main_window import QualityLevel
    from desktop.qt_app.pipeline_worker import PipelineWorker

    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])

    with tempfile.NamedTemporaryFile(suffix=".stl") as f:
        worker = PipelineWorker(
            Path(f.name),
            QualityLevel.DRAFT,
            no_repair=True,
            surface_remesh=True,
            remesh_engine="mmg",
            allow_ai_fallback=True,
        )

    assert getattr(worker, "_no_repair") is True
    assert getattr(worker, "_surface_remesh") is True
    assert getattr(worker, "_remesh_engine") == "mmg"
    assert getattr(worker, "_allow_ai_fallback") is True


# ---------------------------------------------------------------------------
# 테스트: 다크 테마 + 신규 UI 컴포넌트 (헤드리스 CI 호환)
# ---------------------------------------------------------------------------


def test_quality_seg_btns_attribute_exists() -> None:
    """AutoTessellWindow 가 _quality_seg_btns dict 속성을 갖는다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert hasattr(win, "_quality_seg_btns"), "_quality_seg_btns 속성이 필요하다"
    assert isinstance(win._quality_seg_btns, dict)


def test_quality_level_set_via_internal_state() -> None:
    """set_quality_level이 _quality_level을 올바르게 업데이트한다."""
    from desktop.qt_app.main_window import AutoTessellWindow, QualityLevel

    win = AutoTessellWindow()
    assert win.get_quality_level() == QualityLevel.DRAFT

    win.set_quality_level("standard")
    assert win.get_quality_level() == QualityLevel.STANDARD

    win.set_quality_level(QualityLevel.FINE)
    assert win.get_quality_level() == QualityLevel.FINE


def test_pipeline_step_labels_attribute_exists() -> None:
    """AutoTessellWindow 가 _pipeline_step_labels list 속성을 갖는다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert hasattr(win, "_pipeline_step_labels"), "_pipeline_step_labels 속성이 필요하다"
    assert isinstance(win._pipeline_step_labels, list)


def test_kpi_labels_attribute_exists() -> None:
    """AutoTessellWindow 가 _kpi_labels dict 속성을 갖는다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert hasattr(win, "_kpi_labels"), "_kpi_labels 속성이 필요하다"
    assert isinstance(win._kpi_labels, dict)


def test_mesh_type_cards_attribute_exists() -> None:
    """AutoTessellWindow 가 _mesh_type_cards dict 속성을 갖는다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert hasattr(win, "_mesh_type_cards"), "_mesh_type_cards 속성이 필요하다"
    assert isinstance(win._mesh_type_cards, dict)


def test_update_kpi_method_exists() -> None:
    """update_kpi 메서드가 존재하고 호출 가능하다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert hasattr(win, "update_kpi"), "update_kpi 메서드가 필요하다"
    assert callable(win.update_kpi)


def test_update_pipeline_step_method_exists() -> None:
    """update_pipeline_step 메서드가 존재하고 호출 가능하다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert hasattr(win, "update_pipeline_step"), "update_pipeline_step 메서드가 필요하다"
    assert callable(win.update_pipeline_step)


def test_quality_fine_warns_without_openfoam(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenFOAM 없을 때 Fine 선택 시 경고 로직이 트리거되는 경로 확인.

    _refresh_quality_seg_btns 호출 시 예외 없이 완료되고,
    _quality_level 이 FINE 으로 바뀌어야 한다.
    (실제 QMessageBox 팝업은 헤드리스 환경에서 테스트 불가 — 로직만 검증)
    """
    from desktop.qt_app.main_window import AutoTessellWindow, QualityLevel

    win = AutoTessellWindow()
    # _quality_seg_btns 가 비어있으므로 _refresh_quality_seg_btns 는 no-op
    win.set_quality_level(QualityLevel.FINE)
    assert win.get_quality_level() == QualityLevel.FINE


def test_tier_combo_text_default() -> None:
    """_tier_combo 가 None 일 때 _tier_combo_text 는 'auto' 를 반환한다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    # _build() 호출 전이므로 _engine_combo 는 None
    assert win._tier_combo_text() == "auto"


def test_param_scope_by_tier_and_remesh_engine() -> None:
    """엔진별 파라미터 적용 범위가 GUI 규칙과 일치한다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()

    assert win._param_is_applicable("snappy_snap_tolerance", "snappy", "auto")
    assert not win._param_is_applicable("snappy_snap_tolerance", "netgen", "auto")
    assert win._param_is_applicable("tetwild_stop_energy", "tetwild", "auto")
    assert not win._param_is_applicable("tetwild_stop_energy", "core", "auto")
    assert win._param_is_applicable("core_quality", "core", "auto")
    assert not win._param_is_applicable("core_quality", "snappy", "auto")

    assert win._param_is_applicable("mmg_hmin", "auto", "mmg")
    assert not win._param_is_applicable("mmg_hmin", "auto", "quadwild")

    # auto는 후보 엔진을 확정하지 않았으므로 관련 파라미터를 노출한다.
    assert win._param_is_applicable("snappy_snap_tolerance", "auto", "auto")
    assert win._param_is_applicable("mmg_hgrad", "auto", "auto")
