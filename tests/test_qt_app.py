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


def test_mesh_type_default_and_set() -> None:
    """v0.4: mesh_type 기본값은 'auto', set_mesh_type 으로 변경된다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert win._mesh_type == "auto"
    win.set_mesh_type("tet")
    assert win._mesh_type == "tet"
    win.set_mesh_type("hex_dominant")
    assert win._mesh_type == "hex_dominant"
    win.set_mesh_type("poly")
    assert win._mesh_type == "poly"
    # 유효하지 않은 값은 무시되고 이전 값 유지
    win.set_mesh_type("invalid")
    assert win._mesh_type == "poly"


def test_prefer_native_tier_check_attribute_exists() -> None:
    """beta29: AutoTessellWindow 가 _prefer_native_tier_check 속성을 갖는다.

    UI builder 가 실제 실행되기 전까지는 None 이지만 속성 자체는 선언되어야 함
    (기존 _prefer_native_check 와 동일 패턴).
    """
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert hasattr(win, "_prefer_native_tier_check")


def test_pipeline_worker_accepts_prefer_native_tier() -> None:
    """beta29: PipelineWorker 가 prefer_native_tier kwarg 를 수용."""
    from pathlib import Path

    from core.schemas import QualityLevel as _QL
    from desktop.qt_app.pipeline_worker import PipelineWorker

    w = PipelineWorker(
        Path("/tmp/does_not_exist.stl"),
        _QL.FINE,
        tier_hint="auto",
        mesh_type="hex_dominant",
        prefer_native_tier=True,
    )
    assert getattr(w, "_prefer_native_tier", None) is True


def test_pipeline_worker_accepts_mesh_type_and_auto_retry() -> None:
    """PipelineWorker 가 mesh_type / auto_retry kwargs 를 받아들인다."""
    from pathlib import Path

    from core.schemas import QualityLevel as _QL
    from desktop.qt_app.pipeline_worker import PipelineWorker

    # Worker 생성만 검증 (run() 은 호출 안 함 → QThread 시작 금지)
    w = PipelineWorker(
        Path("/tmp/does_not_exist.stl"),
        _QL.DRAFT,
        tier_hint="auto",
        mesh_type="hex_dominant",
        auto_retry="once",
    )
    assert getattr(w, "_mesh_type", None) == "hex_dominant"
    assert getattr(w, "_auto_retry", None) == "once"


def test_qt_pipeline_native_tet_e2e(monkeypatch, tmp_path) -> None:
    """v0.4 e2e: AutoTessellWindow(mesh_type=tet) + PipelineWorker(tier=native_tet)
    가 PipelineOrchestrator.run() 을 올바른 tier/mesh_type 으로 호출한다.

    실제 메시 생성은 하지 않고 orchestrator 를 monkeypatch 로 교체. QThread.run
    을 직접 호출해 finished 시그널 payload 를 캡처한다 (headless 안전).
    """
    from pathlib import Path
    from types import SimpleNamespace

    from PySide6.QtCore import QCoreApplication, QObject, Slot
    from core.schemas import QualityLevel as _QL
    from desktop.qt_app.main_window import AutoTessellWindow
    from desktop.qt_app.pipeline_worker import PipelineWorker

    app = QCoreApplication.instance() or QCoreApplication([])

    win = AutoTessellWindow()
    win.set_mesh_type("tet")
    assert win._mesh_type == "tet"

    # 더미 STL 경로 (파일 존재 여부는 orchestrator 가 처리 — 여기서는 mock)
    stub_stl = tmp_path / "dummy.stl"
    stub_stl.write_text("solid empty\nendsolid\n")

    captured: dict = {}

    class _StubOrchestrator:
        def run(self, **kwargs):  # noqa: ANN003
            captured.update(kwargs)
            return SimpleNamespace(
                success=True,
                iterations=1,
                total_time_seconds=0.0,
                error=None,
                final_case_dir=str(tmp_path),
                quality_report=None,
            )

    import core.pipeline.orchestrator as orch_mod  # noqa: PLC0415

    monkeypatch.setattr(orch_mod, "PipelineOrchestrator", _StubOrchestrator)

    # Worker 인스턴스 생성 (tier=native_tet, mesh_type=tet)
    worker = PipelineWorker(
        stub_stl,
        _QL.DRAFT,
        output_dir=tmp_path / "case",
        tier_hint="native_tet",
        mesh_type="tet",
        auto_retry="off",
        prefer_native=True,
    )
    assert worker._tier_hint == "native_tet"
    assert worker._mesh_type == "tet"
    assert worker._prefer_native is True

    # finished payload 캡처
    class _Sink(QObject):
        def __init__(self) -> None:
            super().__init__()
            self.received = None

        @Slot(object)
        def on_finished(self, result) -> None:  # noqa: ANN001
            self.received = result

    sink = _Sink()
    worker.finished.connect(sink.on_finished)

    # QThread.start() 대신 run() 을 synchronously 호출 — orchestrator 가 stub 이라
    # 즉시 반환.
    worker.run()
    app.processEvents()

    assert captured, "orchestrator.run() 이 호출되지 않음"
    assert captured.get("tier_hint") == "native_tet"
    assert captured.get("mesh_type") == "tet"
    assert captured.get("quality_level") == _QL.DRAFT.value
    assert captured.get("prefer_native") is True
    assert sink.received is not None
    assert sink.received.success is True


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


# ---------------------------------------------------------------------------
# 신규 테스트: DropZone QLabel 서브클래스
# ---------------------------------------------------------------------------


def test_drop_zone_is_qlabel_subclass() -> None:
    """DropZone이 QLabel 서브클래스인지 확인."""
    from PySide6.QtWidgets import QLabel
    from desktop.qt_app.drop_zone import DropZone

    assert issubclass(DropZone, QLabel), "DropZone must be a QLabel subclass"


def test_drop_zone_has_file_dropped_signal() -> None:
    """DropZone이 file_dropped Signal을 갖는지 확인."""
    from desktop.qt_app.drop_zone import DropZone

    assert hasattr(DropZone, "file_dropped"), "DropZone must have file_dropped signal"


@pytest.mark.requires_display
def test_drop_zone_accepts_drops_flag() -> None:
    """DropZone 인스턴스가 acceptDrops=True인지 확인 (QApplication 필요)."""
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.drop_zone import DropZone

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    zone = DropZone()
    assert zone.acceptDrops(), "DropZone must accept drops"


# ---------------------------------------------------------------------------
# 신규 테스트: 신규 UI 필드 존재 확인
# ---------------------------------------------------------------------------


def test_new_ui_fields_exist() -> None:
    """v0.4 신규 UI 필드들이 __init__ 후 존재하는지 확인."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert hasattr(win, "_output_path_edit"), "_output_path_edit 속성 필요"
    assert hasattr(win, "_surface_element_size_edit"), "_surface_element_size_edit 속성 필요"
    assert hasattr(win, "_surface_min_size_edit"), "_surface_min_size_edit 속성 필요"
    assert hasattr(win, "_surface_feature_angle_edit"), "_surface_feature_angle_edit 속성 필요"
    assert hasattr(win, "_quality_desc_label"), "_quality_desc_label 속성 필요"
    assert hasattr(win, "_output_path_label"), "_output_path_label 속성 필요"


def test_quality_desc_label_initialized_none() -> None:
    """_quality_desc_label은 _build() 전에는 None이다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert win._quality_desc_label is None


def test_quality_desc_constant_has_three_entries() -> None:
    """_QUALITY_DESC 딕셔너리에 draft/standard/fine 세 항목이 있다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    assert hasattr(AutoTessellWindow, "_QUALITY_DESC")
    desc = AutoTessellWindow._QUALITY_DESC
    assert set(desc.keys()) == {"draft", "standard", "fine"}


# ---------------------------------------------------------------------------
# 신규 테스트: TIER_PARAM_SPECS 신규 항목 확인
# ---------------------------------------------------------------------------


def test_new_tier_param_specs_present() -> None:
    """TIER_PARAM_SPECS에 신규 파라미터들이 존재한다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    keys = {spec[0] for spec in AutoTessellWindow.TIER_PARAM_SPECS}
    new_params = [
        "algohex_pipeline", "algohex_tet_size",
        "robust_hex_n_cells", "robust_hex_hausdorff",
        "mmg3d_hmax", "mmg3d_hmin", "mmg3d_hausd", "mmg3d_ar", "mmg3d_optim",
        "wildmesh_edge_length_r",
        "classy_cell_size", "hex_classy_use_snappy",
        "cinolib_hex_scale",
        "voro_relax_iters",
        "bl_num_layers", "bl_first_thickness", "bl_growth_ratio", "bl_feature_angle",
        "domain_min_x", "domain_min_y", "domain_min_z",
        "domain_max_x", "domain_max_y", "domain_max_z",
        "domain_base_cell_size",
    ]
    for param in new_params:
        assert param in keys, f"TIER_PARAM_SPECS에 '{param}' 항목이 없습니다"


def test_new_tier_param_scope_present() -> None:
    """_TIER_PARAM_SCOPE에 신규 파라미터 스코프가 등록되어 있다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    scope = win._TIER_PARAM_SCOPE

    assert "wildmesh_edge_length_r" in scope
    assert "classy_cell_size" in scope
    assert "hex_classy_use_snappy" in scope
    assert "cinolib_hex_scale" in scope
    assert "voro_relax_iters" in scope

    # 스코프 값 확인
    assert scope["wildmesh_edge_length_r"] == {"wildmesh"}
    assert scope["voro_relax_iters"] == {"voro_poly"}
    assert "classy_blocks" in scope["classy_cell_size"]
    assert "hex_classy" in scope["classy_cell_size"]


def test_param_scope_new_engines() -> None:
    """신규 엔진 파라미터 적용 범위 확인."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()

    assert win._param_is_applicable("algohex_pipeline", "algohex", "auto")
    assert not win._param_is_applicable("algohex_pipeline", "netgen", "auto")
    assert win._param_is_applicable("wildmesh_edge_length_r", "wildmesh", "auto")
    assert not win._param_is_applicable("wildmesh_edge_length_r", "tetwild", "auto")
    assert win._param_is_applicable("cinolib_hex_scale", "cinolib_hex", "auto")
    assert not win._param_is_applicable("cinolib_hex_scale", "snappy", "auto")
    assert win._param_is_applicable("voro_relax_iters", "voro_poly", "auto")
    assert not win._param_is_applicable("voro_relax_iters", "core", "auto")


def test_output_dir_updates_path_label() -> None:
    """set_output_dir 호출 시 _output_path_label이 없어도 예외가 나지 않는다."""
    from desktop.qt_app.main_window import AutoTessellWindow
    from pathlib import Path

    win = AutoTessellWindow()
    # _output_path_label is None before _build()
    win.set_output_dir(Path("/tmp/test_case"))
    assert win.get_output_dir() == Path("/tmp/test_case")


@pytest.mark.requires_display
def test_success_loads_mesh_to_plotter() -> None:
    """파이프라인 성공 후 PyVista plotter에 메쉬 로드 확인."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    win._build()
    # plotter 존재 여부만 확인 (headless 환경에서는 None)
    # 실제 메쉬 로드는 pyvistaqt가 필요하므로 구조 확인만 수행
    assert hasattr(win, "_mesh_viewer")


# ---------------------------------------------------------------------------
# 신규 테스트: Export 기능
# ---------------------------------------------------------------------------


def test_export_pane_get_export_options_method_exists() -> None:
    """ExportPane 클래스에 get_export_options 메서드가 존재한다."""
    from desktop.qt_app.widgets.right_column import ExportPane

    assert hasattr(ExportPane, "get_export_options"), "get_export_options 메서드 필요"
    assert callable(ExportPane.get_export_options)


def test_export_pane_on_fmt_method_exists() -> None:
    """ExportPane 클래스에 _on_fmt 메서드가 존재한다."""
    from desktop.qt_app.widgets.right_column import ExportPane

    assert hasattr(ExportPane, "_on_fmt"), "_on_fmt 메서드 필요"
    assert callable(ExportPane._on_fmt)


@pytest.mark.requires_display
def test_export_pane_get_export_options() -> None:
    """ExportPane.get_export_options()가 올바른 구조를 반환한다."""
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.widgets.right_column import ExportPane

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    pane = ExportPane()
    opts = pane.get_export_options()

    assert "format" in opts, "format 키가 필요하다"
    assert "output_dir" in opts, "output_dir 키가 필요하다"
    assert "report_json" in opts, "report_json 키가 필요하다"
    assert "quality_hist" in opts, "quality_hist 키가 필요하다"
    assert "paraview_state" in opts, "paraview_state 키가 필요하다"
    assert "zip_output" in opts, "zip_output 키가 필요하다"
    assert opts["format"] == "openfoam", "기본 포맷은 openfoam이어야 한다"
    assert isinstance(opts["report_json"], bool)
    assert isinstance(opts["zip_output"], bool)


@pytest.mark.requires_display
def test_export_pane_format_selection() -> None:
    """ExportPane 포맷 선택 시 get_export_options 결과가 바뀐다."""
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.widgets.right_column import ExportPane

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    pane = ExportPane()
    assert pane.get_export_options()["format"] == "openfoam"
    # 직접 _on_fmt 호출
    pane._on_fmt("vtu")
    assert pane.get_export_options()["format"] == "vtu"
    pane._on_fmt("cgns")
    assert pane.get_export_options()["format"] == "cgns"


# ---------------------------------------------------------------------------
# 신규 테스트: 프로젝트 저장/복원
# ---------------------------------------------------------------------------


def test_on_save_project_method_exists() -> None:
    """_on_save_project 메서드가 존재한다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert hasattr(win, "_on_save_project"), "_on_save_project 메서드 필요"
    assert callable(win._on_save_project)


def test_on_open_project_method_exists() -> None:
    """_on_open_project 메서드가 존재한다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert hasattr(win, "_on_open_project"), "_on_open_project 메서드 필요"
    assert callable(win._on_open_project)


# ---------------------------------------------------------------------------
# 신규 테스트: quality_update Signal
# ---------------------------------------------------------------------------


def test_pipeline_worker_quality_update_signal() -> None:
    """PipelineWorker._qt_class에 quality_update Signal이 존재한다."""
    from PySide6.QtCore import QCoreApplication
    from desktop.qt_app.main_window import QualityLevel
    from desktop.qt_app.pipeline_worker import PipelineWorker
    import tempfile
    from pathlib import Path

    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])

    with tempfile.NamedTemporaryFile(suffix=".stl") as f:
        instance = PipelineWorker(Path(f.name), QualityLevel.DRAFT)

    qt_cls = type(instance)
    assert hasattr(qt_cls, "quality_update"), "quality_update Signal이 필요하다"


# ---------------------------------------------------------------------------
# 신규 테스트: _on_quality_update 핸들러
# ---------------------------------------------------------------------------


def test_on_quality_update_method_exists() -> None:
    """AutoTessellWindow._on_quality_update 메서드가 존재한다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert hasattr(win, "_on_quality_update"), "_on_quality_update 메서드 필요"
    assert callable(win._on_quality_update)
    # _build 없이 호출해도 예외 없이 처리
    win._on_quality_update({"max_non_ortho": 45.0})


def test_on_quality_update_with_empty_metrics() -> None:
    """빈 metrics dict로 _on_quality_update 호출 시 예외 없이 처리."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    win._on_quality_update({})  # 예외 없이 통과해야 함


# ---------------------------------------------------------------------------
# 신규 테스트: 로그 컨텍스트 메뉴
# ---------------------------------------------------------------------------


def test_job_pane_log_context_menu_method_exists() -> None:
    """JobPane 클래스에 _on_log_context_menu 메서드가 존재한다."""
    from desktop.qt_app.widgets.right_column import JobPane

    assert hasattr(JobPane, "_on_log_context_menu"), "_on_log_context_menu 메서드 필요"
    assert callable(JobPane._on_log_context_menu)


# ---------------------------------------------------------------------------
# 신규 테스트: _on_mesh_stats_computed 핸들러
# ---------------------------------------------------------------------------


def test_on_mesh_stats_computed_method_exists() -> None:
    """AutoTessellWindow._on_mesh_stats_computed 메서드가 존재한다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert hasattr(win, "_on_mesh_stats_computed"), "_on_mesh_stats_computed 필요"
    assert callable(win._on_mesh_stats_computed)
    # _build 없이 호출해도 예외 없이 처리
    win._on_mesh_stats_computed({
        "n_cells": 50000,
        "n_points": 10000,
        "hex_ratio": 0.6,
        "is_volume": True,
    })


# ---------------------------------------------------------------------------
# 신규 테스트: _on_tier_node_clicked
# ---------------------------------------------------------------------------


def test_on_tier_node_clicked_method_exists() -> None:
    """AutoTessellWindow._on_tier_node_clicked 메서드가 존재한다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert hasattr(win, "_on_tier_node_clicked"), "_on_tier_node_clicked 필요"
    assert callable(win._on_tier_node_clicked)


# ---------------------------------------------------------------------------
# 신규 테스트: Export 헬퍼 메서드 존재
# ---------------------------------------------------------------------------


def test_export_helper_methods_exist() -> None:
    """Export 관련 헬퍼 메서드들이 AutoTessellWindow에 존재한다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    for method in (
        "_export_mesh_format",
        "_export_via_meshio",
        "_export_report_json",
        "_export_quality_histogram",
        "_export_paraview_state",
        "_export_zip",
    ):
        assert hasattr(win, method), f"{method} 메서드 필요"
        assert callable(getattr(win, method))


# ---------------------------------------------------------------------------
# 신규 테스트: _try_emit_quality / _emit_quality_from_result
# ---------------------------------------------------------------------------


def test_quality_emit_helpers_exist() -> None:
    """pipeline_worker 모듈에 품질 emit 헬퍼 함수가 존재한다."""
    from desktop.qt_app import pipeline_worker as pw

    assert hasattr(pw, "_try_emit_quality"), "_try_emit_quality 함수 필요"
    assert hasattr(pw, "_emit_quality_from_result"), "_emit_quality_from_result 함수 필요"
    assert callable(pw._try_emit_quality)
    assert callable(pw._emit_quality_from_result)


# ---------------------------------------------------------------------------
# 실질 동작 테스트: _try_emit_quality regex
# ---------------------------------------------------------------------------


def test_try_emit_quality_parses_non_ortho() -> None:
    """_try_emit_quality가 non-ortho 수치를 메시지에서 파싱한다."""
    from desktop.qt_app import pipeline_worker as pw

    emitted: list[dict] = []

    class _FakeWorker:
        class quality_update:
            @staticmethod
            def emit(d: dict) -> None:
                emitted.append(d)

    pw._try_emit_quality(_FakeWorker(), "Max non-ortho: 45.3 degrees")
    assert emitted, "non-ortho 파싱 후 emit 되어야 한다"
    assert "max_non_ortho" in emitted[0]
    assert abs(emitted[0]["max_non_ortho"] - 45.3) < 0.01


def test_try_emit_quality_parses_skewness_and_aspect() -> None:
    """_try_emit_quality가 skewness와 aspect ratio를 동시에 파싱한다."""
    from desktop.qt_app import pipeline_worker as pw

    emitted: list[dict] = []

    class _FakeWorker:
        class quality_update:
            @staticmethod
            def emit(d: dict) -> None:
                emitted.append(d)

    pw._try_emit_quality(_FakeWorker(), "Skewness 2.1 Aspect 8.5")
    assert emitted
    merged = {}
    for d in emitted:
        merged.update(d)
    assert "max_skewness" in merged or "max_aspect_ratio" in merged


def test_try_emit_quality_no_emit_on_unrelated_message() -> None:
    """관련 없는 메시지에는 quality_update emit이 발생하지 않는다."""
    from desktop.qt_app import pipeline_worker as pw

    emitted: list[dict] = []

    class _FakeWorker:
        class quality_update:
            @staticmethod
            def emit(d: dict) -> None:
                emitted.append(d)

    pw._try_emit_quality(_FakeWorker(), "파이프라인 시작: tetwild")
    assert not emitted, "관련 없는 메시지에는 emit이 없어야 한다"


def test_emit_quality_from_result_empty_quality_report() -> None:
    """quality_report가 없는 result에는 emit이 발생하지 않는다."""
    from desktop.qt_app import pipeline_worker as pw

    emitted: list[dict] = []

    class _FakeWorker:
        class quality_update:
            @staticmethod
            def emit(d: dict) -> None:
                emitted.append(d)

    class _FakeResult:
        quality_report = None

    pw._emit_quality_from_result(_FakeWorker(), _FakeResult())
    assert not emitted, "quality_report=None이면 emit 없어야 한다"


def test_export_paraview_state_uses_openfoam_reader_for_polymesh(tmp_path: "Path") -> None:
    """_export_paraview_state가 polyMesh 디렉토리 존재 시 OpenFOAMReader를 사용한다."""
    import importlib, sys

    # main_window를 headless import
    from desktop.qt_app.main_window import AutoTessellWindow, QualityLevel

    win = object.__new__(AutoTessellWindow)
    win._quality_level = QualityLevel.DRAFT  # type: ignore[attr-defined]

    # 가짜 output_dir with polyMesh
    polymesh_dir = tmp_path / "constant" / "polyMesh"
    polymesh_dir.mkdir(parents=True)
    win._output_dir = tmp_path  # type: ignore[attr-defined]
    win._log = lambda msg: None  # type: ignore[attr-defined]

    export_dir = tmp_path / "export"
    export_dir.mkdir()
    win._export_paraview_state(export_dir)  # type: ignore[attr-defined]

    pvsm = (export_dir / "autotessell_view.pvsm").read_text()
    assert "OpenFOAMReader" in pvsm, "polyMesh 있으면 OpenFOAMReader 사용해야 함"
    assert "XMLUnstructuredGridReader" not in pvsm


# ── Design Review Fix Tests ─────────────────────────────────────────────────


def test_pipeline_result_none_on_init() -> None:
    """초기화 시 _pipeline_result는 None (미완료 상태)."""
    from desktop.qt_app.main_window import AutoTessellWindow, QualityLevel

    win = object.__new__(AutoTessellWindow)
    AutoTessellWindow.__init__(win)
    assert win._pipeline_result is None  # type: ignore[attr-defined]


def test_quality_last_updated_none_on_init() -> None:
    """초기화 시 _quality_last_updated는 None."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = object.__new__(AutoTessellWindow)
    AutoTessellWindow.__init__(win)
    assert win._quality_last_updated is None  # type: ignore[attr-defined]


def test_tier_popup_title_has_readonly(tmp_path: "Path") -> None:
    """Tier 파라미터 팝업 제목에 '읽기 전용'이 포함되어야 한다 (코드 분석)."""
    import inspect
    from desktop.qt_app.main_window import AutoTessellWindow

    src = inspect.getsource(AutoTessellWindow._on_tier_node_clicked)  # type: ignore[attr-defined]
    assert "읽기 전용" in src, "Tier 팝업 제목에 읽기 전용 표시가 필요"


def test_on_export_save_precheck_openfoam_without_polymesh(tmp_path: "Path") -> None:
    """polyMesh 없이 OpenFOAM 포맷 Export 시도하면 경고 후 조기 종료해야 한다."""
    import inspect
    from desktop.qt_app.main_window import AutoTessellWindow

    src = inspect.getsource(AutoTessellWindow._on_export_save)  # type: ignore[attr-defined]
    assert "polyMesh" in src, "_on_export_save에 polyMesh 사전 검증이 없음"
    assert "poly_dir.exists()" in src


def test_on_open_project_warns_missing_output_dir(tmp_path: "Path") -> None:
    """프로젝트 열기 시 출력 경로 없으면 경고 로직이 있어야 한다."""
    import inspect
    from desktop.qt_app.main_window import AutoTessellWindow

    src = inspect.getsource(AutoTessellWindow._on_open_project)  # type: ignore[attr-defined]
    assert "output_dir_path.exists()" in src, "missing output_dir path check not found"
    assert "경로 없음" in src


def test_screenshot_qt_grab_is_primary() -> None:
    """_on_screenshot에서 Qt grab()이 1차 시도(WYSIWYG)여야 한다."""
    import inspect
    from desktop.qt_app.main_window import AutoTessellWindow

    src = inspect.getsource(AutoTessellWindow._on_screenshot)  # type: ignore[attr-defined]
    grab_pos = src.find("grab()")
    pyvista_pos = src.find("pv.Plotter")
    assert grab_pos != -1 and pyvista_pos != -1, "grab() 또는 pv.Plotter를 찾을 수 없음"
    assert grab_pos < pyvista_pos, "Qt grab()이 PyVista보다 먼저 와야 함 (WYSIWYG 우선)"


def test_histogram_data_cached_from_mesh_stats(tmp_path: "Path") -> None:
    """mesh_stats_computed에 hist_ 배열이 있으면 _histogram_data에 캐시된다."""
    from desktop.qt_app.main_window import AutoTessellWindow, QualityLevel

    win = object.__new__(AutoTessellWindow)
    AutoTessellWindow.__init__(win)
    win._right_column = None

    stats = {
        "n_cells": 100,
        "hist_aspect_ratio": [1.1, 1.5, 2.0, 3.0],
        "hist_skewness": [0.1, 0.3, 0.5],
    }
    win._on_mesh_stats_computed(stats)  # type: ignore[attr-defined]
    assert win._histogram_data is not None  # type: ignore[attr-defined]
    assert "aspect_ratio" in win._histogram_data  # type: ignore[attr-defined]
    assert "skewness" in win._histogram_data  # type: ignore[attr-defined]


def test_quality_histogram_uses_real_arrays(tmp_path: "Path") -> None:
    """_histogram_data가 있으면 ax.hist() 기반 PNG를 생성한다."""
    from desktop.qt_app.main_window import AutoTessellWindow, QualityLevel

    win = object.__new__(AutoTessellWindow)
    AutoTessellWindow.__init__(win)
    win._right_column = None
    win._log = lambda msg: None  # type: ignore[attr-defined]
    win._histogram_data = {
        "aspect_ratio": [1.0, 1.5, 2.0, 3.0, 5.0, 8.0],
        "skewness": [0.1, 0.2, 0.4, 0.6, 0.8],
    }

    export_dir = tmp_path / "export"
    export_dir.mkdir()
    win._export_quality_histogram(export_dir)  # type: ignore[attr-defined]

    out = export_dir / "quality_histogram.png"
    assert out.exists(), "히스토그램 PNG가 생성되어야 함"
    assert out.stat().st_size > 5000, "PNG 파일이 너무 작음 (히스토그램 아닐 수 있음)"


def test_quality_histogram_fallback_without_data(tmp_path: "Path") -> None:
    """_histogram_data가 None이면 게이지 fallback으로 PNG를 생성한다."""
    from desktop.qt_app.main_window import AutoTessellWindow, QualityLevel

    win = object.__new__(AutoTessellWindow)
    AutoTessellWindow.__init__(win)
    win._right_column = None
    win._log = lambda msg: None  # type: ignore[attr-defined]
    win._histogram_data = None  # type: ignore[attr-defined]

    export_dir = tmp_path / "export"
    export_dir.mkdir()
    # _right_column=None이면 게이지 fallback은 early return
    # 예외 없이 조용히 종료되어야 함
    win._export_quality_histogram(export_dir)  # type: ignore[attr-defined]


def test_viewport_quality_button_exists_in_toolbar() -> None:
    """InteractiveMeshViewer 툴바에 품질 색상화 버튼이 있어야 한다."""
    import inspect
    from desktop.qt_app.mesh_viewer import InteractiveMeshViewer

    src = inspect.getsource(InteractiveMeshViewer._build_toolbar)
    assert "품질 표시" in src or "_quality_btn" in src, "품질 표시 버튼이 툴바에 없음"


def test_log_box_has_tooltip_in_source() -> None:
    """JobPane log_box에 우클릭 힌트 툴팁이 있어야 한다."""
    import inspect
    from desktop.qt_app.widgets.right_column import JobPane

    src = inspect.getsource(JobPane)
    assert "우클릭" in src or "setToolTip" in src.lower() or "toolTip" in src, \
        "JobPane log_box에 우클릭 힌트가 없음"


def test_tier_node_has_node_clicked_signal() -> None:
    """_TierNode 클래스가 node_clicked Signal을 갖고 있어야 한다 (monkey-patch 버그 수정 확인)."""
    import inspect
    from desktop.qt_app.widgets.tier_pipeline import _TierNode

    src = inspect.getsource(_TierNode)
    assert "node_clicked" in src, "_TierNode에 node_clicked Signal이 없음"
    assert "mousePressEvent" in src, "_TierNode.mousePressEvent 오버라이드 없음"


def test_tier_node_click_connects_via_signal() -> None:
    """_NodesContainer.set_tiers()가 signal 연결로 tier_clicked를 wire-up해야 한다."""
    import inspect
    from desktop.qt_app.widgets.tier_pipeline import _NodesContainer

    src = inspect.getsource(_NodesContainer.set_tiers)
    assert "node_clicked.connect" in src, "monkey-patch 방식으로 tier 클릭을 연결하고 있음"


def test_drop_zone_has_clicked_signal() -> None:
    """DropZone이 clicked Signal을 갖고 있어야 한다 (click-to-browse 기능)."""
    from desktop.qt_app.drop_zone import DropZone

    assert hasattr(DropZone, "clicked"), "DropZone.clicked Signal 없음"


def test_drop_zone_has_mousePressEvent_override() -> None:
    """DropZone이 mousePressEvent를 오버라이드해야 한다."""
    import inspect
    from desktop.qt_app.drop_zone import DropZone

    src = inspect.getsource(DropZone)
    assert "mousePressEvent" in src, "DropZone.mousePressEvent 오버라이드 없음"


def test_mesh_viewer_has_mesh_ready_signal() -> None:
    """InteractiveMeshViewer에 mesh_ready Signal이 있어야 한다."""
    import inspect
    from desktop.qt_app.mesh_viewer import InteractiveMeshViewer

    src = inspect.getsource(InteractiveMeshViewer)
    assert "mesh_ready" in src, "InteractiveMeshViewer.mesh_ready Signal 없음"


def test_quality_pane_has_histogram_widget() -> None:
    """QualityPane에 _HistogramCanvas histogram 속성이 있어야 한다."""
    import inspect
    from desktop.qt_app.widgets.right_column import QualityPane

    src = inspect.getsource(QualityPane.__init__)
    assert "histogram" in src, "QualityPane에 histogram 위젯이 없음"


def test_histogram_canvas_update_histograms_method() -> None:
    """_HistogramCanvas에 update_histograms 메서드가 있어야 한다."""
    from desktop.qt_app.widgets.right_column import _HistogramCanvas

    assert hasattr(_HistogramCanvas, "update_histograms"), "_HistogramCanvas.update_histograms 없음"


def test_quality_metric_dropdown_defined() -> None:
    """InteractiveMeshViewer에 _QUALITY_METRICS 딕셔너리가 정의돼야 한다."""
    from desktop.qt_app.mesh_viewer import InteractiveMeshViewer

    assert hasattr(InteractiveMeshViewer, "_QUALITY_METRICS"), "_QUALITY_METRICS 없음"
    metrics = InteractiveMeshViewer._QUALITY_METRICS
    assert "aspect_ratio" in metrics, "aspect_ratio 메트릭 없음"
    assert "skew" in metrics, "skew 메트릭 없음"
    assert "max_angle" in metrics, "max_angle (non-ortho) 메트릭 없음"


def test_on_quality_metric_selected_method_exists() -> None:
    """InteractiveMeshViewer에 _on_quality_metric_selected 메서드가 있어야 한다."""
    from desktop.qt_app.mesh_viewer import InteractiveMeshViewer

    assert hasattr(InteractiveMeshViewer, "_on_quality_metric_selected"), \
        "_on_quality_metric_selected 없음"


def test_pipeline_interrupted_emits_finished() -> None:
    """InterruptedError 발생 시 pipeline_worker가 finished Signal을 emit해야 한다."""
    import inspect
    from desktop.qt_app import pipeline_worker

    src = inspect.getsource(pipeline_worker)
    # InterruptedError 핸들러에서 finished.emit이 있어야 함
    assert "InterruptedError" in src, "InterruptedError 핸들러 없음"
    assert "finished.emit" in src, "finished Signal emit 없음"


def test_quality_bar_stores_fill_ratio() -> None:
    """_QualityBar.set_value가 _fill_ratio를 저장해야 한다 (resizeEvent 수정 확인)."""
    import inspect
    from desktop.qt_app.widgets.right_column import _QualityBar

    src = inspect.getsource(_QualityBar.set_value)
    assert "_fill_ratio" in src, "_QualityBar.set_value에서 _fill_ratio 저장 없음"


def test_tier_pipeline_strip_public_apis_exist() -> None:
    """TierPipelineStrip 공개 API (get_status/node_count/reset_active_to/get_node_info)가 있어야 한다."""
    from desktop.qt_app.widgets.tier_pipeline import TierPipelineStrip

    for method in ("get_status", "node_count", "reset_active_to", "get_node_info"):
        assert hasattr(TierPipelineStrip, method), f"TierPipelineStrip.{method} 없음"


def test_tier_pipeline_strip_get_node_info_shape() -> None:
    """get_node_info가 name/engine/status를 가진 dict 또는 None을 반환해야 한다."""
    import inspect
    from desktop.qt_app.widgets.tier_pipeline import TierPipelineStrip

    src = inspect.getsource(TierPipelineStrip.get_node_info)
    for field in ("name", "engine", "status"):
        assert field in src, f"get_node_info 리턴 dict에 {field} 없음"


def test_cancellation_resets_active_tier_nodes() -> None:
    """_on_pipeline_finished 중단 경로가 reset_active_to('skipped')를 호출해야 한다."""
    import inspect
    from desktop.qt_app.main_window import AutoTessellWindow

    src = inspect.getsource(AutoTessellWindow._on_pipeline_finished)
    assert "reset_active_to" in src, "중단 후 active tier 노드 정리 없음"
    assert "Cancelled" in src, "JobPane에 Cancelled 배지 표시 없음"


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1 — Behavioral Signal Tests (QTest + QSignalSpy 기반)
# 소스 문자열 검증이 아닌 실제 이벤트→시그널→동작 체인을 검증
# ═══════════════════════════════════════════════════════════════════════════


def test_dropzone_mouse_press_emits_clicked() -> None:
    """DropZone에 실제 마우스 클릭 → clicked Signal emit 검증."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QSignalSpy, QTest
    from desktop.qt_app.drop_zone import DropZone

    dz = DropZone()
    dz.resize(200, 100)
    spy = QSignalSpy(dz.clicked)
    QTest.mouseClick(dz, Qt.MouseButton.LeftButton)
    assert spy.count() == 1, f"clicked signal 미발생 (count={spy.count()})"


def test_tier_node_click_emits_node_clicked_with_zero_based_index() -> None:
    """_TierNode 클릭 시 node_clicked Signal이 0-based index로 emit되어야 한다."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QSignalSpy, QTest
    from desktop.qt_app.widgets.tier_pipeline import _TierNode

    # 1-based index=3으로 생성 → emit 시 2 (0-based)
    node = _TierNode(index=3, name="Tier 3", engine="Netgen")
    node.resize(120, 80)
    spy = QSignalSpy(node.node_clicked)
    QTest.mouseClick(node, Qt.MouseButton.LeftButton)
    assert spy.count() == 1
    emitted = spy.at(0)[0]
    assert emitted == 2, f"0-based index 기대 2, 실제 {emitted}"


def test_tier_pipeline_strip_propagates_tier_clicked() -> None:
    """TierPipelineStrip.set_tiers 후 자식 노드 클릭 → strip.tier_clicked emit 검증."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QSignalSpy, QTest
    from desktop.qt_app.widgets.tier_pipeline import TierPipelineStrip

    strip = TierPipelineStrip()
    strip.set_tiers([("Tier A", "a"), ("Tier B", "b"), ("Tier C", "c")])
    strip.resize(500, 140)
    spy = QSignalSpy(strip.tier_clicked)

    # 두 번째 노드 클릭 → tier_clicked(1) 기대
    # strip._nodes 직접 접근은 테스트 한정 (공개 API는 get_node_info)
    nodes = [strip._nodes[i] for i in range(strip.node_count())]
    QTest.mouseClick(nodes[1], Qt.MouseButton.LeftButton)
    assert spy.count() == 1
    assert spy.at(0)[0] == 1


def test_tier_pipeline_reset_active_to_skipped() -> None:
    """reset_active_to('skipped')가 active 노드만 skipped로 전환해야 한다."""
    from desktop.qt_app.widgets.tier_pipeline import TierPipelineStrip

    strip = TierPipelineStrip()
    strip.set_tiers([("A", "a"), ("B", "b"), ("C", "c")])
    strip.set_status(0, "done")
    strip.set_status(1, "active")
    strip.set_status(2, "pending")

    changed = strip.reset_active_to("skipped")
    assert changed == 1
    assert strip.get_status(0) == "done"
    assert strip.get_status(1) == "skipped"
    assert strip.get_status(2) == "pending"


def test_tier_pipeline_get_node_info_returns_correct_dict() -> None:
    """get_node_info가 name/engine/status dict를 반환하고, 범위 밖은 None."""
    from desktop.qt_app.widgets.tier_pipeline import TierPipelineStrip

    strip = TierPipelineStrip()
    strip.set_tiers([("Alpha", "eng1"), ("Beta", "eng2")])
    strip.set_status(0, "done")

    info = strip.get_node_info(0)
    assert info == {"name": "Alpha", "engine": "eng1", "status": "done"}
    assert strip.get_node_info(99) is None


@pytest.mark.requires_display
def test_quality_metric_selected_updates_metric() -> None:
    """_on_quality_metric_selected가 action.data() 값으로 _quality_metric 업데이트."""
    from desktop.qt_app.mesh_viewer import (
        InteractiveMeshViewer,
        PYVISTAQT_AVAILABLE,
    )

    if not PYVISTAQT_AVAILABLE:
        pytest.skip("pyvistaqt unavailable")

    from PySide6.QtGui import QAction

    viewer = InteractiveMeshViewer()
    assert viewer._quality_metric == "aspect_ratio"  # 기본값

    # skew action 시뮬레이션
    action = QAction("Skewness")
    action.setData("skew")
    viewer._on_quality_metric_selected(action)
    assert viewer._quality_metric == "skew"
    assert "Skew" in viewer._quality_btn.text()

    # max_angle action 시뮬레이션
    action2 = QAction("Non-ortho")
    action2.setData("max_angle")
    viewer._on_quality_metric_selected(action2)
    assert viewer._quality_metric == "max_angle"
    assert "Non-ortho" in viewer._quality_btn.text()


@pytest.mark.requires_display
def test_mesh_viewer_widget_connects_mesh_ready_to_stats() -> None:
    """MeshViewerWidget이 mesh_ready Signal을 _compute_and_emit_stats에 연결한다."""
    from desktop.qt_app.mesh_viewer import (
        MeshViewerWidget,
        PYVISTAQT_AVAILABLE,
    )

    if not PYVISTAQT_AVAILABLE:
        pytest.skip("pyvistaqt unavailable")

    widget = MeshViewerWidget()
    if not hasattr(widget._viewer, "mesh_ready"):
        pytest.skip("viewer는 StaticMeshViewer (mesh_ready 없음)")

    # _compute_and_emit_stats를 가로채서 호출 여부 확인
    calls = []
    original = widget._compute_and_emit_stats
    widget._compute_and_emit_stats = lambda mesh: calls.append(mesh)  # type: ignore[assignment]

    # 하지만 signal 연결은 이미 __init__ 시점에 original 메서드를 가리킴.
    # 대신 connect receivers 개수로 wiring 검증
    try:
        receivers = widget._viewer.receivers(widget._viewer.mesh_ready)
        assert receivers >= 1, f"mesh_ready에 연결된 receiver 없음 (count={receivers})"
    finally:
        widget._compute_and_emit_stats = original  # type: ignore[assignment]


@pytest.mark.requires_display
def test_mesh_ready_emit_triggers_stats_when_patched_before_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """클래스 레벨에서 _compute_and_emit_stats를 patch 후 구성 → mesh_ready emit이 호출해야 한다."""
    from desktop.qt_app.mesh_viewer import (
        MeshViewerWidget,
        PYVISTAQT_AVAILABLE,
    )

    if not PYVISTAQT_AVAILABLE:
        pytest.skip("pyvistaqt unavailable")

    calls: list = []
    monkeypatch.setattr(
        MeshViewerWidget,
        "_compute_and_emit_stats",
        lambda self, mesh: calls.append(mesh),
    )
    widget = MeshViewerWidget()
    if not hasattr(widget._viewer, "mesh_ready"):
        pytest.skip("StaticMeshViewer fallback")

    fake_mesh = object()
    widget._viewer.mesh_ready.emit(fake_mesh)
    assert calls == [fake_mesh], f"_compute_and_emit_stats 미호출 (calls={calls!r})"


@pytest.mark.requires_display
def test_drop_zone_clicked_wires_pick_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """DropZone.clicked → main window의 _on_pick_input 호출 검증."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from desktop.qt_app.main_window import AutoTessellWindow

    called: list[bool] = []
    # 클래스 레벨 패치 — 시그널 연결 시점에 이 메서드가 바인딩됨
    monkeypatch.setattr(
        AutoTessellWindow, "_on_pick_input", lambda self: called.append(True)
    )

    win = AutoTessellWindow()
    win._build()
    assert win._drop_label is not None

    # 패치된 _on_pick_input이 바인딩됐는지 확인
    win._drop_label.resize(200, 100)
    QTest.mouseClick(win._drop_label, Qt.MouseButton.LeftButton)
    assert called == [True], f"_on_pick_input 미호출 (called={called})"


def test_quality_histogram_canvas_has_update_method() -> None:
    """_HistogramCanvas.update_histograms가 데이터 없이 호출돼도 에러 없이 동작."""
    from desktop.qt_app.widgets.right_column import _HistogramCanvas

    canvas = _HistogramCanvas()
    # None 인자 → matplotlib 미설치면 no-op, 설치면 "데이터 없음" 표시
    canvas.update_histograms(aspect_data=None, skew_data=None)
    # 실제 데이터
    canvas.update_histograms(
        aspect_data=[1.0, 1.2, 1.5, 2.0, 1.1, 1.3],
        skew_data=[0.1, 0.2, 0.3, 0.15, 0.25],
    )
    # 에러 없이 도달하면 통과


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3 — Real Pipeline Smoke Tests
# PipelineWorker를 sphere.stl 실제 실행 → finished signal 수신까지 검증
# ═══════════════════════════════════════════════════════════════════════════


def _wait_for_signal(
    signal_flag: list, worker, timeout_s: float = 60.0
) -> bool:
    """QSignalSpy.wait()가 크로스스레드 이벤트를 제대로 spin하지 않으므로
    수동 processEvents 루프로 신호 대기. signal_flag[0]=True면 반환."""
    import time

    from PySide6.QtCore import QCoreApplication

    t0 = time.time()
    while not signal_flag[0] and time.time() - t0 < timeout_s:
        QCoreApplication.processEvents()
        time.sleep(0.05)
    return bool(signal_flag[0])


@pytest.mark.slow
def test_pipeline_worker_runs_sphere_draft_end_to_end(tmp_path) -> None:
    """PipelineWorker.start() → finished Signal이 success=True로 emit된다 (sphere.stl draft, ~3s)."""
    from pathlib import Path

    from desktop.qt_app.main_window import QualityLevel
    from desktop.qt_app.pipeline_worker import PipelineWorker

    sphere = Path(__file__).parent / "benchmarks" / "sphere.stl"
    assert sphere.exists(), f"벤치마크 누락: {sphere}"

    out_dir = tmp_path / "case"
    worker = PipelineWorker(
        input_path=sphere,
        quality_level=QualityLevel.DRAFT,
        output_dir=out_dir,
    )

    finished_flag: list = [False]
    finished_result: list = [None]
    progress_count: list = [0]

    def _on_fin(r: object) -> None:
        finished_result[0] = r
        finished_flag[0] = True

    worker.finished.connect(_on_fin)  # type: ignore[attr-defined]
    worker.progress.connect(lambda _m: progress_count.__setitem__(0, progress_count[0] + 1))  # type: ignore[attr-defined]

    worker.start()  # type: ignore[attr-defined]
    try:
        assert _wait_for_signal(finished_flag, worker, timeout_s=60.0), \
            "finished Signal 미수신 (60s timeout)"
        worker.wait(5_000)  # type: ignore[attr-defined]

        # 검증
        result = finished_result[0]
        assert result is not None, "finished에 result=None emit됨"
        success = getattr(result, "success", None)
        assert success is True, (
            f"파이프라인 실패: success={success}, "
            f"error={getattr(result, 'error', None)!r}"
        )

        # polyMesh 출력 확인
        polymesh = out_dir / "constant" / "polyMesh"
        assert polymesh.exists(), f"polyMesh 미생성: {polymesh}"
        assert (polymesh / "points").exists(), "polyMesh/points 없음"
        assert (polymesh / "faces").exists(), "polyMesh/faces 없음"
        assert (polymesh / "owner").exists(), "polyMesh/owner 없음"

        # progress Signal 실제로 발화했는지
        assert progress_count[0] >= 5, \
            f"progress Signal 횟수 부족 (실제={progress_count[0]}, 기대>=5)"
    finally:
        if worker.isRunning():  # type: ignore[attr-defined]
            worker.requestInterruption()  # type: ignore[attr-defined]
            worker.wait(5_000)  # type: ignore[attr-defined]


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2 — UI State Transition Tests (위젯 단위 동작 검증, MeshViewer 없이)
# ═══════════════════════════════════════════════════════════════════════════


def test_export_pane_get_export_options_returns_dict() -> None:
    """ExportPane.get_export_options()가 format/compress 키를 가진 dict 반환."""
    from desktop.qt_app.widgets.right_column import ExportPane

    pane = ExportPane()
    opts = pane.get_export_options()
    assert isinstance(opts, dict), f"dict 기대, 실제 {type(opts)}"
    # 최소한 format 키가 있어야 — 구체 값은 UI 초기 상태에 따름
    assert "format" in opts or len(opts) > 0, \
        f"ExportPane 옵션 dict 비어 있음: {opts}"


def test_quality_pane_set_metric_updates_bar_value() -> None:
    """QualityPane.set_metric이 지정된 바의 값 텍스트를 갱신한다."""
    from desktop.qt_app.widgets.right_column import QualityPane

    pane = QualityPane()
    pane.set_metric("aspect", 0.3, "3.5", warn=False)
    assert pane.q_aspect._val_lbl.text() == "3.5"
    pane.set_metric("skew", 0.8, "7.2", warn=True)
    assert pane.q_skew._val_lbl.text() == "7.2"


def test_viewport_kpi_overlay_has_all_rows() -> None:
    """KPIStatsOverlay가 Cells/Tier/Time/Hex%/Aspect/Skew/Non-ortho 7개 행 제공."""
    from desktop.qt_app.widgets.viewport_overlays import KPIStatsOverlay

    kpi = KPIStatsOverlay()
    expected = ["Cells", "Tier", "Time", "Hex %", "Aspect", "Skew", "Non-ortho"]
    for key in expected:
        assert key in kpi._rows, f"KPIStatsOverlay에 '{key}' 행 없음"


def test_viewport_kpi_overlay_set_value_and_warn() -> None:
    """set_value가 텍스트 갱신 + warn=True시 주황색 스타일 적용."""
    from desktop.qt_app.widgets.viewport_overlays import KPIStatsOverlay

    kpi = KPIStatsOverlay()
    kpi.set_value("Cells", "8,572")
    assert kpi._rows["Cells"].text() == "8,572"

    kpi.set_value("Non-ortho", "72.5°", warn=True)
    assert kpi._rows["Non-ortho"].text() == "72.5°"
    # 경고 색상이 스타일시트에 반영됐는지
    assert "#ff7b54" in kpi._rows["Non-ortho"].styleSheet()


def test_recent_files_add_load_clear(tmp_path, monkeypatch) -> None:
    """recent_files.add/load/clear가 JSON 영속화 + 중복 제거 + 최대 5개."""
    from pathlib import Path
    from desktop.qt_app import recent_files

    # ~/.autotessell 경로를 tmp로 바꿔치기
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(recent_files, "_RECENT_DIR", fake_home)
    monkeypatch.setattr(recent_files, "_RECENT_FILE", fake_home / "recent.json")

    # 실제로 존재하는 파일이어야 load가 필터링 안함
    files = []
    for i in range(7):
        f = tmp_path / f"f{i}.stl"
        f.write_text("x")
        files.append(f)

    for f in files:
        recent_files.add(f)

    entries = recent_files.load()
    # 최대 5개 + 역순 (최근이 앞)
    assert len(entries) == 5
    assert Path(entries[0]).name == "f6.stl"  # 가장 최근
    assert Path(entries[-1]).name == "f2.stl"  # 5번째로 최근

    # 중복 추가 → 중복 제거
    recent_files.add(files[3])
    entries2 = recent_files.load()
    assert len(entries2) == 5
    assert Path(entries2[0]).name == "f3.stl"  # 재추가된 게 맨 앞

    # clear
    recent_files.clear()
    assert recent_files.load() == []


def test_recent_files_skip_nonexistent(tmp_path, monkeypatch) -> None:
    """load 시 존재하지 않는 경로는 자동 제거."""
    from desktop.qt_app import recent_files

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(recent_files, "_RECENT_DIR", fake_home)
    monkeypatch.setattr(recent_files, "_RECENT_FILE", fake_home / "recent.json")

    f = tmp_path / "exists.stl"
    f.write_text("x")
    recent_files.add(f)
    recent_files.add(tmp_path / "deleted.stl")  # 존재 안함 — 추가만

    entries = recent_files.load()
    # 존재하는 것만 나와야 함
    assert len(entries) == 1
    assert "exists" in entries[0]


def test_presets_builtin_list() -> None:
    """내장 프리셋 8종 (기본 5 + WildMesh 3)이 정의돼 있어야 한다."""
    from desktop.qt_app.presets import BUILTIN_PRESETS, all_presets

    assert len(BUILTIN_PRESETS) == 8
    names = [p.name for p in BUILTIN_PRESETS]
    assert "Draft Quick (Tet)" in names
    assert any("External" in n for n in names)
    assert any("Internal" in n for n in names)
    assert any("Aerospace" in n for n in names)
    # WildMesh 프리셋도 확인
    assert any("WildMesh" in n for n in names)


def test_preset_get_returns_correct() -> None:
    """presets.get(name)이 이름으로 조회 작동."""
    from desktop.qt_app.presets import get

    p = get("Draft Quick (Tet)")
    assert p is not None
    assert p.quality_level == "draft"
    assert p.tier_hint == "tier2_tetwild"
    assert get("존재하지 않는 프리셋") is None


# ═══════════════════════════════════════════════════════════════════════════
# Phase N — WildMesh-only 정책 검증 (단일 엔진 모드)
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
# Phase O — WildMesh 안정화 + GUI 렌더 수정 + 백로그 Tier A
# ═══════════════════════════════════════════════════════════════════════════


def test_wildmesh_param_clamp_out_of_range() -> None:
    """WM1: epsilon/edge_length_r/stop_quality/max_its 범위 밖 → clamp."""
    from core.generator.tier_wildmesh import _PARAM_RANGES, _clamp_param, _get_quality_params

    # 너무 작은 값 → lo로 clamp
    assert _clamp_param("epsilon", 1e-8) == _PARAM_RANGES["epsilon"][0]
    assert _clamp_param("edge_length_r", 0.001) == _PARAM_RANGES["edge_length_r"][0]
    # 너무 큰 값 → hi로 clamp
    assert _clamp_param("epsilon", 0.5) == _PARAM_RANGES["epsilon"][1]
    # 정상 범위 통과
    assert _clamp_param("epsilon", 0.002) == 0.002

    # _get_quality_params 통합 테스트
    p = _get_quality_params("draft", {"wildmesh_epsilon": 1e-10})
    assert p["epsilon"] >= _PARAM_RANGES["epsilon"][0]
    p = _get_quality_params("draft", {"wildmesh_epsilon": 10.0})
    assert p["epsilon"] <= _PARAM_RANGES["epsilon"][1]


def test_wildmesh_timeout_scales_with_mesh_size() -> None:
    """WM3: 메쉬 크기에 따라 동적 timeout, 상한 30분."""
    from core.generator.tier_wildmesh import _TIMEOUT_MAX_SEC, _compute_timeout

    # 작은 메쉬
    t_small = _compute_timeout("draft", 1000, {})
    # 큰 메쉬
    t_large = _compute_timeout("draft", 100_000, {})
    assert t_large > t_small, "큰 메쉬가 더 긴 timeout 필요"

    # 매우 큰 메쉬 → 상한
    t_huge = _compute_timeout("fine", 10_000_000, {})
    assert t_huge == _TIMEOUT_MAX_SEC

    # 사용자 override
    t_user = _compute_timeout("draft", 100_000, {"wildmesh_timeout": 90})
    assert t_user == 90

    # override도 상한 적용
    t_override_huge = _compute_timeout("draft", 100, {"wildmesh_timeout": 999999})
    assert t_override_huge == _TIMEOUT_MAX_SEC


def test_wildmesh_preflight_watertight_warning(tmp_path) -> None:
    """WM4: non-watertight 메쉬 → WARN 경고 포함."""
    import trimesh

    from desktop.qt_app.wildmesh_preflight import WarningLevel, analyze

    # 구멍 있는 메쉬 생성
    path = tmp_path / "open.stl"
    mesh = trimesh.creation.box(extents=[1, 1, 1])
    # 한 face 제거해서 open shell 만들기
    mesh.faces = mesh.faces[:-2]
    mesh.export(str(path))

    report = analyze(path)
    # watertight 경고 또는 다른 위험 경고가 있어야 함
    titles = " ".join(w.title for w in report.warnings)
    assert "watertight" in titles.lower() or "non-watertight" in titles.lower()


def test_wildmesh_preflight_thin_wall_danger(tmp_path) -> None:
    """WM4: 극도 thin-wall (aspect > 100) → DANGER."""
    import numpy as _np
    import trimesh

    from desktop.qt_app.wildmesh_preflight import WarningLevel, analyze

    # 1000 x 1 x 0.005 극얇은 판 → aspect ~200k
    path = tmp_path / "thin.stl"
    mesh = trimesh.creation.box(extents=[1000.0, 1.0, 0.005])
    mesh.export(str(path))

    report = analyze(path)
    danger_titles = [w.title for w in report.warnings if w.level == WarningLevel.DANGER]
    assert any("thin" in t.lower() or "planar" in t.lower() for t in danger_titles), \
        f"thin-wall DANGER 감지 실패: {danger_titles}"
    assert report.is_safe is False


def test_wildmesh_preflight_empty_missing_file(tmp_path) -> None:
    """WM4: 없는 파일 → DANGER."""
    from desktop.qt_app.wildmesh_preflight import WarningLevel, analyze

    report = analyze(tmp_path / "nothing.stl")
    assert report.is_safe is False
    assert any(w.level == WarningLevel.DANGER for w in report.warnings)


def test_param_history_push_and_revert(tmp_path, monkeypatch) -> None:
    """A3: push/pop_previous/peek 왕복."""
    from desktop.qt_app import param_history

    monkeypatch.setattr(param_history, "_HISTORY_DIR", tmp_path / "x")
    monkeypatch.setattr(param_history, "_HISTORY_FILE", tmp_path / "x" / "ph.json")

    param_history.push({"wildmesh_epsilon": 0.001})
    param_history.push({"wildmesh_epsilon": 0.002})
    param_history.push({"wildmesh_epsilon": 0.0005})

    # peek은 최신
    latest = param_history.peek()
    assert latest == {"wildmesh_epsilon": 0.0005}

    # pop_previous: [0] 제거하고 [1] 반환 (이전 값)
    prev = param_history.pop_previous()
    assert prev == {"wildmesh_epsilon": 0.002}

    # 스냅샷 하나만 있으면 pop_previous → None
    param_history.clear()
    param_history.push({"only_one": 1})
    assert param_history.pop_previous() is None


def test_param_history_max_5() -> None:
    """A3: 최대 5개 제한."""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from desktop.qt_app import param_history

    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        with patch.object(param_history, "_HISTORY_DIR", tmp_p), \
             patch.object(param_history, "_HISTORY_FILE", tmp_p / "ph.json"):
            for i in range(10):
                param_history.push({"v": i})
            entries = param_history.load()
            assert len(entries) == 5
            # 최신이 맨 앞
            assert entries[0]["v"] == 9
            assert entries[-1]["v"] == 5


def test_param_history_deduplicates() -> None:
    """A3: 동일 스냅샷 중복 제거."""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from desktop.qt_app import param_history

    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        with patch.object(param_history, "_HISTORY_DIR", tmp_p), \
             patch.object(param_history, "_HISTORY_FILE", tmp_p / "ph.json"):
            param_history.push({"a": 1})
            param_history.push({"a": 1})  # 같은 값
            entries = param_history.load()
            assert len(entries) == 1


def test_param_validator_numeric_ok() -> None:
    """A2: numeric_validator 정상 값 → ok."""
    from desktop.qt_app.widgets.param_validator import numeric_validator

    v = numeric_validator("float", min_val=0.0, max_val=1.0,
                          recommended_min=0.1, recommended_max=0.9)
    result = v("0.5")
    assert result.level == "ok"
    assert result.parsed_value == 0.5

    # 빈 문자열은 ok
    result = v("")
    assert result.level == "ok"


def test_param_validator_numeric_warn_and_err() -> None:
    """A2: 권장 범위 밖 → warn, hard 범위 밖 → err, 파싱 실패 → err."""
    from desktop.qt_app.widgets.param_validator import numeric_validator

    v = numeric_validator("float", min_val=0.0, max_val=1.0,
                          recommended_min=0.1, recommended_max=0.9)
    # warn (권장 밖)
    assert v("0.05").level == "warn"
    assert v("0.95").level == "warn"
    # err (hard 밖)
    assert v("-0.1").level == "err"
    assert v("1.5").level == "err"
    # err (파싱)
    assert v("abc").level == "err"


def test_wildmesh_param_panel_presets() -> None:
    """A1: WildMeshParamPanel 프리셋 적용 → current_params 반환."""
    from desktop.qt_app.widgets.wildmesh_param_panel import PRESETS, WildMeshParamPanel

    panel = WildMeshParamPanel()
    # 기본은 draft
    params = panel.current_params()
    assert abs(params["wildmesh_epsilon"] - PRESETS["draft"]["epsilon"]) < 1e-4

    # standard로 전환
    panel.apply_preset("standard")
    params = panel.current_params()
    assert abs(params["wildmesh_epsilon"] - PRESETS["standard"]["epsilon"]) < 1e-4

    # 외부에서 set_params
    panel.set_params({"wildmesh_epsilon": 0.005, "wildmesh_stop_quality": 7})
    params = panel.current_params()
    assert 0.003 < params["wildmesh_epsilon"] < 0.008


def test_wildmesh_param_panel_emits_signal() -> None:
    """A1: 프리셋 변경시 params_changed Signal emit."""
    from PySide6.QtTest import QSignalSpy
    from desktop.qt_app.widgets.wildmesh_param_panel import WildMeshParamPanel

    panel = WildMeshParamPanel()
    spy = QSignalSpy(panel.params_changed)
    panel.apply_preset("fine")
    assert spy.count() >= 1


def test_gu1_matplotlib_korean_fonts_configured() -> None:
    """GU1: matplotlib rcParams에 한국어 폰트가 앞쪽에 있어야 한다."""
    # __init__.py 가 import 시 _configure_matplotlib_fonts() 호출됨
    import desktop.qt_app  # noqa: F401

    import matplotlib

    sans = list(matplotlib.rcParams.get("font.sans-serif", []))
    # Pretendard가 DejaVu보다 앞에
    assert "Pretendard" in sans
    assert "DejaVu Sans" in sans
    pret_idx = sans.index("Pretendard")
    dejavu_idx = sans.index("DejaVu Sans")
    assert pret_idx < dejavu_idx


def test_gu2_palette_has_new_semantic_keys() -> None:
    """GU2: PALETTE에 accent_fg/err_fg/code_bg/dialog_bg 추가."""
    from desktop.qt_app.main_window import PALETTE

    for key in ("accent_fg", "err_fg", "code_bg", "dialog_bg"):
        assert key in PALETTE, f"PALETTE['{key}'] 없음"
        assert PALETTE[key].startswith("#")


def test_gu4_dialog_size_constants_defined() -> None:
    """GU4: DIALOG_SMALL/MEDIUM/LARGE 상수 정의."""
    from desktop.qt_app.main_window import DIALOG_LARGE, DIALOG_MEDIUM, DIALOG_SMALL

    assert isinstance(DIALOG_SMALL, tuple) and len(DIALOG_SMALL) == 2
    assert isinstance(DIALOG_MEDIUM, tuple) and len(DIALOG_MEDIUM) == 2
    assert isinstance(DIALOG_LARGE, tuple) and len(DIALOG_LARGE) == 2
    # 순서대로 커지는지
    assert DIALOG_SMALL[0] < DIALOG_MEDIUM[0] < DIALOG_LARGE[0]


def test_engine_policy_default_is_all(tmp_path, monkeypatch) -> None:
    """정책 파일 없음 + env 없음 → 'all' 기본."""
    from desktop.qt_app import engine_policy

    monkeypatch.delenv("AUTOTESSELL_ENGINE_POLICY", raising=False)
    monkeypatch.setattr(engine_policy, "_POLICY_DIR", tmp_path / "x")
    monkeypatch.setattr(engine_policy, "_POLICY_FILE", tmp_path / "x" / "engine_policy.json")

    policy = engine_policy.load()
    assert policy.mode == "all"
    assert policy.allow_strategist_fallback is True
    assert policy.is_allowed("tier_wildmesh") is True
    assert policy.is_allowed("tier2_tetwild") is True


def test_engine_policy_wildmesh_only_blocks_other_engines(tmp_path, monkeypatch) -> None:
    """wildmesh_only 모드 — 타 엔진 차단, fallback 없음."""
    from desktop.qt_app import engine_policy

    monkeypatch.setenv("AUTOTESSELL_ENGINE_POLICY", "wildmesh_only")
    policy = engine_policy.load()

    assert policy.mode == "wildmesh_only"
    assert policy.default_tier == "tier_wildmesh"
    assert policy.allow_strategist_fallback is False
    assert policy.is_allowed("tier_wildmesh") is True
    assert policy.is_allowed("tier2_tetwild") is False
    assert policy.is_allowed("tier1_snappy") is False
    # auto는 Strategist 경유이므로 정책 적용 전까진 허용
    assert policy.is_allowed("auto") is True

    # fallback 필터
    fb = policy.fallback_order("tier_wildmesh", ["tier2_tetwild", "tier1_snappy"])
    assert fb == []


def test_engine_policy_save_and_load_roundtrip(tmp_path, monkeypatch) -> None:
    """set_mode → 파일 저장 → load 재조회 일치."""
    from desktop.qt_app import engine_policy

    monkeypatch.delenv("AUTOTESSELL_ENGINE_POLICY", raising=False)
    monkeypatch.setattr(engine_policy, "_POLICY_DIR", tmp_path / "home")
    monkeypatch.setattr(engine_policy, "_POLICY_FILE", tmp_path / "home" / "engine_policy.json")

    engine_policy.set_mode("wildmesh_only")
    reloaded = engine_policy.load()
    assert reloaded.mode == "wildmesh_only"
    assert reloaded.allow_strategist_fallback is False


def test_tier_selector_policy_filter_forces_wildmesh(monkeypatch) -> None:
    """_policy_filter_tier: wildmesh_only 하에서 다른 tier 요청시 wildmesh로 교체."""
    monkeypatch.setenv("AUTOTESSELL_ENGINE_POLICY", "wildmesh_only")
    from core.strategist.tier_selector import _policy_filter_tier

    sel, fb = _policy_filter_tier("tier2_tetwild", ["tier05_netgen", "tier1_snappy"])
    assert sel == "tier_wildmesh"
    assert fb == []


def test_tier_selector_policy_filter_all_mode_passthrough(monkeypatch) -> None:
    """'all' 정책 → 필터 통과, 원본 그대로."""
    monkeypatch.setenv("AUTOTESSELL_ENGINE_POLICY", "all")
    from core.strategist.tier_selector import _policy_filter_tier

    sel, fb = _policy_filter_tier("tier2_tetwild", ["tier05_netgen", "tier1_snappy"])
    assert sel == "tier2_tetwild"
    assert fb == ["tier05_netgen", "tier1_snappy"]


def test_resolve_engine_canonical_mapping() -> None:
    """GUI 짧은 키 → canonical tier 변환."""
    from desktop.qt_app.main_window import _resolve_engine_canonical

    assert _resolve_engine_canonical("wildmesh") == "tier_wildmesh"
    assert _resolve_engine_canonical("tetwild") == "tier2_tetwild"
    assert _resolve_engine_canonical("snappy") == "tier1_snappy"
    assert _resolve_engine_canonical("auto") == "auto"
    # 모르는 키는 그대로 반환
    assert _resolve_engine_canonical("unknown_xyz") == "unknown_xyz"


def test_wildmesh_presets_exist() -> None:
    """WildMesh 전용 프리셋 3종 내장 확인."""
    from desktop.qt_app.presets import BUILTIN_PRESETS

    wildmesh_presets = [p for p in BUILTIN_PRESETS if p.tier_hint == "wildmesh"]
    assert len(wildmesh_presets) == 3
    names = [p.name for p in wildmesh_presets]
    assert "WildMesh Draft" in names
    assert "WildMesh Standard" in names
    assert "WildMesh Fine (Feature Preserving)" in names

    # 파라미터 검증 — 모든 wildmesh 프리셋이 wildmesh_epsilon 포함
    for p in wildmesh_presets:
        assert "wildmesh_epsilon" in p.params
        assert "wildmesh_edge_length_r" in p.params
        assert "wildmesh_stop_quality" in p.params


def test_cli_tier_choice_includes_wildmesh() -> None:
    """CLI --tier choice 목록에 wildmesh + 신규 엔진 포함."""
    import inspect
    import cli.main as cli_main

    src = inspect.getsource(cli_main)
    # --tier Choice 리스트에 wildmesh 등 최신 엔진들이 있어야
    assert '"wildmesh"' in src, "CLI --tier choice에 wildmesh 없음"
    for engine in ["mmg3d", "algohex", "robust_hex", "jigsaw"]:
        assert f'"{engine}"' in src, f"CLI --tier choice에 {engine} 누락"


@pytest.mark.slow
def test_pipeline_worker_runs_sphere_wildmesh_end_to_end(tmp_path) -> None:
    """PipelineWorker.start() with tier_hint='wildmesh' → success + polyMesh."""
    from pathlib import Path

    from desktop.qt_app.main_window import QualityLevel
    from desktop.qt_app.pipeline_worker import PipelineWorker

    sphere = Path(__file__).parent / "benchmarks" / "sphere.stl"
    assert sphere.exists()

    out_dir = tmp_path / "case"
    worker = PipelineWorker(
        input_path=sphere,
        quality_level=QualityLevel.DRAFT,
        output_dir=out_dir,
        tier_hint="wildmesh",
    )

    finished_flag: list = [False]
    finished_result: list = [None]
    progress_count: list = [0]
    worker.finished.connect(  # type: ignore[attr-defined]
        lambda r: (finished_result.__setitem__(0, r), finished_flag.__setitem__(0, True))
    )
    worker.progress.connect(lambda _m: progress_count.__setitem__(0, progress_count[0] + 1))  # type: ignore[attr-defined]

    worker.start()  # type: ignore[attr-defined]
    try:
        assert _wait_for_signal(finished_flag, worker, timeout_s=60.0), \
            "wildmesh 파이프라인 finished 미수신"
        worker.wait(5_000)  # type: ignore[attr-defined]

        result = finished_result[0]
        assert result is not None
        assert getattr(result, "success", False) is True, \
            f"wildmesh 실패: error={getattr(result, 'error', None)!r}"

        polymesh = out_dir / "constant" / "polyMesh"
        assert polymesh.exists()
        assert (polymesh / "points").exists()

        # 실제 wildmesh가 사용됐는지 확인
        gen_log = getattr(result, "generator_log", None)
        summary = getattr(gen_log, "execution_summary", None) if gen_log else None
        selected_tier = getattr(summary, "selected_tier", "") if summary else ""
        assert selected_tier == "tier_wildmesh", \
            f"wildmesh이 아닌 엔진 사용됨: {selected_tier}"

        assert progress_count[0] >= 5
    finally:
        if worker.isRunning():  # type: ignore[attr-defined]
            worker.requestInterruption()  # type: ignore[attr-defined]
            worker.wait(5_000)  # type: ignore[attr-defined]


@pytest.mark.slow
def test_wildmesh_only_policy_rewrites_tier_hint(tmp_path, monkeypatch) -> None:
    """wildmesh_only 정책 하에서 tier_hint='snappy' 요청 → 실제로 tier_wildmesh 사용."""
    from pathlib import Path

    from desktop.qt_app.main_window import QualityLevel
    from desktop.qt_app.pipeline_worker import PipelineWorker

    # 정책을 env로 설정
    monkeypatch.setenv("AUTOTESSELL_ENGINE_POLICY", "wildmesh_only")

    sphere = Path(__file__).parent / "benchmarks" / "sphere.stl"
    out_dir = tmp_path / "case"
    worker = PipelineWorker(
        input_path=sphere,
        quality_level=QualityLevel.DRAFT,
        output_dir=out_dir,
        tier_hint="snappy",  # 정책이 wildmesh로 덮어씀
    )

    finished_flag: list = [False]
    finished_result: list = [None]
    worker.finished.connect(  # type: ignore[attr-defined]
        lambda r: (finished_result.__setitem__(0, r), finished_flag.__setitem__(0, True))
    )

    worker.start()  # type: ignore[attr-defined]
    try:
        assert _wait_for_signal(finished_flag, worker, timeout_s=60.0)
        worker.wait(5_000)  # type: ignore[attr-defined]

        result = finished_result[0]
        assert result is not None
        assert getattr(result, "success", False) is True

        # tier_wildmesh가 실제로 사용됐는지
        gen_log = getattr(result, "generator_log", None)
        summary = getattr(gen_log, "execution_summary", None) if gen_log else None
        selected_tier = getattr(summary, "selected_tier", "") if summary else ""
        assert selected_tier == "tier_wildmesh", \
            f"정책이 snappy를 wildmesh로 바꾸지 못함: {selected_tier}"
    finally:
        if worker.isRunning():  # type: ignore[attr-defined]
            worker.requestInterruption()  # type: ignore[attr-defined]
            worker.wait(5_000)  # type: ignore[attr-defined]


def test_geometry_hint_analyze_sphere() -> None:
    """sphere.stl 실제 파일로 지오메트리 분석."""
    from pathlib import Path

    from desktop.qt_app.geometry_hint import analyze

    sphere = Path("tests/benchmarks/sphere.stl")
    if not sphere.exists():
        pytest.skip("sphere.stl 없음")

    hint = analyze(sphere)
    assert hint.error is None
    assert hint.n_triangles > 0
    assert hint.n_vertices > 0
    assert hint.bbox_diag > 0
    assert hint.file_size_mb > 0
    # sphere는 watertight
    assert hint.is_watertight is True


def test_geometry_hint_recommend_quality_by_triangles() -> None:
    """삼각형 수에 따른 품질 추천."""
    from desktop.qt_app.geometry_hint import GeometryHint, _recommend_quality

    # 작은 메쉬 → draft
    h1 = GeometryHint(n_triangles=1000, is_watertight=True)
    _recommend_quality(h1)
    assert h1.recommended_quality == "draft"

    # 중간 크기 → standard
    h2 = GeometryHint(n_triangles=50_000, is_watertight=True)
    _recommend_quality(h2)
    assert h2.recommended_quality == "standard"

    # 큰 메쉬 → fine
    h3 = GeometryHint(n_triangles=500_000, is_watertight=True)
    _recommend_quality(h3)
    assert h3.recommended_quality == "fine"

    # Watertight 아님 → 수리 힌트 포함
    h4 = GeometryHint(n_triangles=1000, is_watertight=False)
    _recommend_quality(h4)
    assert "L1" in h4.recommended_reason or "수리" in h4.recommended_reason


def test_geometry_hint_format_complete() -> None:
    """format_hint 모든 필드 포함."""
    from desktop.qt_app.geometry_hint import GeometryHint, format_hint

    h = GeometryHint(
        n_triangles=12000,
        n_vertices=6000,
        bbox_diag=1.732,
        is_watertight=True,
        is_winding_consistent=True,
        file_size_mb=0.5,
        recommended_quality="standard",
        recommended_reason="12,000 삼각형",
        eta_seconds_draft=5.0,
        eta_seconds_standard=120.0,
        eta_confidence="medium",
    )
    text = format_hint(h)
    assert "12,000" in text or "12000" in text
    assert "✓ Watertight" in text
    assert "추천" in text
    assert "ETA" in text


def test_geometry_hint_cad_file_unsupported() -> None:
    """STEP 파일은 trimesh로 직접 분석 불가 — 적절한 에러."""
    from pathlib import Path

    from desktop.qt_app.geometry_hint import analyze

    # 가짜 STEP 파일 (trimesh는 로드 못함)
    p = Path("/tmp/fake_cad.step")
    p.write_text("ISO-10303-21;\nHEADER;")
    try:
        hint = analyze(p)
        # CAD 파일은 ext 검사에서 걸러짐
        assert hint.error is not None
        assert "tessellation" in hint.error.lower() or ".step" in hint.error.lower()
    finally:
        p.unlink(missing_ok=True)


def test_geometry_hint_eta_from_history(tmp_path, monkeypatch) -> None:
    """history에 기록된 유사 실행 시간 → ETA 예측."""
    from desktop.qt_app import geometry_hint, history

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(history, "_HISTORY_DIR", fake_home)
    monkeypatch.setattr(history, "_HISTORY_FILE", fake_home / "history.jsonl")

    # 10,000 셀 정도의 draft 성공 이력 3개
    for elapsed, cells in [(2.8, 8500), (3.2, 11000), (2.5, 9200)]:
        history.record(history.HistoryEntry(
            timestamp="2026-04-18T10:00:00",
            input_file="/x.stl", output_dir="/o",
            quality_level="draft", tier_used="tier2_tetwild",
            success=True, elapsed_seconds=elapsed, n_cells=cells,
        ))

    # 새 메쉬: 1000 삼각형 (→ 약 10000 셀 예상 — 유사)
    h = geometry_hint.GeometryHint(n_triangles=1000, is_watertight=True)
    geometry_hint._predict_eta(h)

    assert h.eta_seconds_draft is not None
    # 중앙값 2.8 근처
    assert 2.0 < h.eta_seconds_draft < 4.0
    assert h.eta_confidence in ("low", "medium", "high")


def test_history_record_and_load(tmp_path, monkeypatch) -> None:
    """history.record → load_all 왕복 + 최신순 정렬."""
    from desktop.qt_app import history

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(history, "_HISTORY_DIR", fake_home)
    monkeypatch.setattr(history, "_HISTORY_FILE", fake_home / "history.jsonl")

    e1 = history.HistoryEntry(
        timestamp="2026-04-18T10:00:00",
        input_file="/tmp/a.stl", output_dir="/tmp/a_case",
        quality_level="draft", tier_used="tier2_tetwild",
        success=True, elapsed_seconds=3.2, n_cells=5000,
    )
    e2 = history.HistoryEntry(
        timestamp="2026-04-18T10:05:00",
        input_file="/tmp/b.stl", output_dir="/tmp/b_case",
        quality_level="standard", tier_used="tier05_netgen",
        success=False, elapsed_seconds=1.8, error="FOAM FATAL",
    )
    history.record(e1)
    history.record(e2)

    entries = history.load_all()
    assert len(entries) == 2
    # 최신이 먼저 (e2)
    assert entries[0].input_file == "/tmp/b.stl"
    assert entries[0].success is False
    assert entries[1].input_file == "/tmp/a.stl"


def test_history_clear(tmp_path, monkeypatch) -> None:
    """history.clear 후 load_all 빈 리스트."""
    from desktop.qt_app import history

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(history, "_HISTORY_DIR", fake_home)
    monkeypatch.setattr(history, "_HISTORY_FILE", fake_home / "history.jsonl")

    history.record(history.HistoryEntry(
        timestamp="2026-04-18T10:00:00",
        input_file="/a.stl", output_dir="/o", quality_level="draft",
        tier_used="x", success=True, elapsed_seconds=1.0,
    ))
    assert len(history.load_all()) == 1
    history.clear()
    assert history.load_all() == []


def test_history_make_entry_from_result() -> None:
    """make_entry_from_result: 목 객체 → HistoryEntry 필드."""
    from types import SimpleNamespace

    from desktop.qt_app.history import make_entry_from_result

    check_mesh = SimpleNamespace(
        cells=8572,
        max_aspect_ratio=4.1,
        max_skewness=0.46,
        max_non_orthogonality=44.3,
    )
    quality_report = SimpleNamespace(check_mesh=check_mesh)
    execution_summary = SimpleNamespace(selected_tier="tier2_tetwild")
    generator_log = SimpleNamespace(execution_summary=execution_summary)
    result = SimpleNamespace(
        success=True, total_time_seconds=2.74, error=None,
        quality_report=quality_report, generator_log=generator_log,
    )

    e = make_entry_from_result(
        input_file="/tmp/sphere.stl",
        output_dir="/tmp/case",
        quality_level="draft",
        result=result,
    )
    assert e.success is True
    assert e.n_cells == 8572
    assert e.tier_used == "tier2_tetwild"
    assert e.max_non_orthogonality == 44.3
    assert e.elapsed_seconds == 2.74


def test_history_dialog_filter_success_only(tmp_path, monkeypatch) -> None:
    """HistoryDialog 필터 '성공만' → 실패 항목 제외."""
    from desktop.qt_app import history
    from desktop.qt_app.history_dialog import HistoryDialog

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(history, "_HISTORY_DIR", fake_home)
    monkeypatch.setattr(history, "_HISTORY_FILE", fake_home / "history.jsonl")

    history.record(history.HistoryEntry(
        timestamp="2026-04-18T10:00:00",
        input_file="/a.stl", output_dir="/o", quality_level="draft",
        tier_used="x", success=True, elapsed_seconds=1.0,
    ))
    history.record(history.HistoryEntry(
        timestamp="2026-04-18T10:05:00",
        input_file="/b.stl", output_dir="/o", quality_level="draft",
        tier_used="y", success=False, elapsed_seconds=2.0, error="boom",
    ))

    dlg = HistoryDialog()
    assert dlg.table.rowCount() == 2  # 기본 '전체'

    # 성공만
    idx = dlg.status_combo.findData("success")
    dlg.status_combo.setCurrentIndex(idx)
    dlg._refresh()
    assert dlg.table.rowCount() == 1

    # 실패만
    idx = dlg.status_combo.findData("failure")
    dlg.status_combo.setCurrentIndex(idx)
    dlg._refresh()
    assert dlg.table.rowCount() == 1


def test_history_dialog_search_filter(tmp_path, monkeypatch) -> None:
    """HistoryDialog 검색어 → 파일명 매칭만 남김."""
    from desktop.qt_app import history
    from desktop.qt_app.history_dialog import HistoryDialog

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(history, "_HISTORY_DIR", fake_home)
    monkeypatch.setattr(history, "_HISTORY_FILE", fake_home / "history.jsonl")

    history.record(history.HistoryEntry(
        timestamp="2026-04-18T10:00:00",
        input_file="/proj/sphere.stl", output_dir="/o",
        quality_level="draft", tier_used="x", success=True, elapsed_seconds=1.0,
    ))
    history.record(history.HistoryEntry(
        timestamp="2026-04-18T10:05:00",
        input_file="/proj/cube.stl", output_dir="/o",
        quality_level="draft", tier_used="x", success=True, elapsed_seconds=2.0,
    ))

    dlg = HistoryDialog()
    dlg.search_edit.setText("sphere")
    dlg._refresh()
    assert dlg.table.rowCount() == 1


def test_batch_make_parameter_sweep(tmp_path) -> None:
    """make_parameter_sweep: 1 파일 × N 값 → N개 job 생성."""
    from pathlib import Path
    from desktop.qt_app.batch import make_parameter_sweep, JobStatus

    jobs = make_parameter_sweep(
        base_input=Path("/tmp/sphere.stl"),
        output_root=tmp_path,
        quality_level="draft",
        tier_hint="tier2_tetwild",
        sweep_key="epsilon",
        sweep_values=[0.001, 0.002, 0.005],
        preset_name="Draft Quick",
    )
    assert len(jobs) == 3
    assert all(j.status == JobStatus.PENDING for j in jobs)
    # params는 sweep_key만 포함
    assert jobs[0].params == {"epsilon": 0.001}
    assert jobs[2].params == {"epsilon": 0.005}
    # output_dir 고유
    dirs = [j.output_dir for j in jobs]
    assert len(set(dirs)) == 3
    assert "0p001" in str(jobs[0].output_dir)


def test_batch_make_file_batch(tmp_path) -> None:
    """make_file_batch: N 파일 × 동일 설정 → N개 job."""
    from pathlib import Path
    from desktop.qt_app.batch import make_file_batch

    files = [Path("/tmp/a.stl"), Path("/tmp/b.stl"), Path("/tmp/c.stl")]
    jobs = make_file_batch(
        input_paths=files,
        output_root=tmp_path,
        quality_level="standard",
        tier_hint="tier05_netgen",
        params={"element_size": 0.1},
    )
    assert len(jobs) == 3
    assert jobs[0].input_path.stem == "a"
    assert jobs[0].output_dir == tmp_path / "a_case"
    assert jobs[2].output_dir == tmp_path / "c_case"
    # 모두 동일 설정
    assert all(j.quality_level == "standard" for j in jobs)
    assert all(j.params == {"element_size": 0.1} for j in jobs)


def test_batch_summary_aggregation() -> None:
    """BatchSummary.from_jobs: 상태별 집계 + 성공률."""
    from pathlib import Path
    from desktop.qt_app.batch import BatchJob, BatchSummary, JobStatus

    jobs = [
        BatchJob(Path("/x"), Path("/y"), status=JobStatus.SUCCESS, elapsed_seconds=2.5),
        BatchJob(Path("/x"), Path("/y"), status=JobStatus.SUCCESS, elapsed_seconds=3.0),
        BatchJob(Path("/x"), Path("/y"), status=JobStatus.FAILED, elapsed_seconds=1.0),
        BatchJob(Path("/x"), Path("/y"), status=JobStatus.CANCELLED, elapsed_seconds=0.5),
    ]
    s = BatchSummary.from_jobs(jobs)
    assert s.total == 4
    assert s.succeeded == 2
    assert s.failed == 1
    assert s.cancelled == 1
    assert abs(s.total_elapsed_seconds - 7.0) < 1e-9
    assert abs(s.pass_rate() - 0.5) < 1e-9


def test_batch_summary_empty() -> None:
    """빈 job 리스트는 pass_rate=0."""
    from desktop.qt_app.batch import BatchSummary

    s = BatchSummary.from_jobs([])
    assert s.total == 0
    assert s.pass_rate() == 0.0


def test_batch_job_display_name() -> None:
    """display_name: stem + 파라미터 일부."""
    from pathlib import Path
    from desktop.qt_app.batch import BatchJob

    j1 = BatchJob(Path("/a/sphere.stl"), Path("/o"))
    assert j1.display_name() == "sphere"

    j2 = BatchJob(Path("/a/cube.stl"), Path("/o"), params={"epsilon": 0.001})
    assert j2.display_name() == "cube (epsilon=0.001)"


def test_batch_dialog_add_jobs(tmp_path) -> None:
    """BatchDialog.add_jobs: 프로그래매틱 주입 + 테이블 행 수 일치."""
    from pathlib import Path
    from desktop.qt_app.batch import BatchJob
    from desktop.qt_app.batch_dialog import BatchDialog

    dlg = BatchDialog()
    f = tmp_path / "x.stl"
    f.write_text("solid")

    jobs = [
        BatchJob(f, tmp_path / "case1"),
        BatchJob(f, tmp_path / "case2"),
    ]
    dlg.add_jobs(jobs)

    assert dlg.table.rowCount() == 2
    # 상태 컬럼 표시
    assert "대기" in dlg.table.item(0, 3).text()


def test_report_pdf_generation(tmp_path) -> None:
    """ReportData → PDF 파일 생성 + 최소 크기 검증."""
    from desktop.qt_app.report_pdf import ReportData, write_pdf, _MPL_AVAILABLE

    if not _MPL_AVAILABLE:
        pytest.skip("matplotlib 미설치")

    data = ReportData(
        input_file="/path/to/sphere.stl",
        output_dir="/tmp/case",
        tier_used="tier2_tetwild",
        quality_level="draft",
        total_time_seconds=2.74,
        n_cells=8572,
        n_points=1824,
        max_aspect_ratio=4.1,
        max_skewness=0.46,
        max_non_orthogonality=44.3,
        negative_volumes=0,
        hist_aspect=[1.0 + 0.1 * i for i in range(100)],
        hist_skew=[0.01 * i for i in range(100)],
        hist_non_ortho=[10.0 + 0.5 * i for i in range(100)],
    )
    out = tmp_path / "report.pdf"
    ok = write_pdf(data, out)
    assert ok is True
    assert out.exists()
    assert out.stat().st_size > 5000  # 최소 5KB (matplotlib PDF는 보통 20KB+)


def test_report_pdf_no_glyph_missing_warning(tmp_path) -> None:
    """PDF 리포트 생성 중 glyph missing 경고가 없어야 한다."""
    import warnings

    from desktop.qt_app.report_pdf import ReportData, write_pdf, _MPL_AVAILABLE

    if not _MPL_AVAILABLE:
        pytest.skip("matplotlib 미설치")

    data = ReportData(
        input_file="/path/to/sphere.stl",
        output_dir="/tmp/case",
        tier_used="tier_wildmesh",
        quality_level="draft",
        total_time_seconds=1.5,
        n_cells=1000,
        n_points=500,
        max_aspect_ratio=2.0,
        max_skewness=0.4,
        max_non_orthogonality=20.0,
        negative_volumes=0,
    )
    out = tmp_path / "report.pdf"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ok = write_pdf(data, out)

    assert ok is True
    glyph_warnings = [w for w in caught if "Glyph" in str(w.message)]
    assert glyph_warnings == []


def test_report_pdf_verdict_logic() -> None:
    """_compute_verdict: 임계값 기반 PASS/WARN/FAIL."""
    from desktop.qt_app.report_pdf import ReportData, _compute_verdict

    # 전부 통과
    d1 = ReportData(
        max_aspect_ratio=10.0, max_skewness=1.0,
        max_non_orthogonality=30.0, negative_volumes=0,
    )
    assert _compute_verdict(d1) == "PASS"

    # 경고 (임계값의 80% 초과)
    d2 = ReportData(
        max_aspect_ratio=10.0, max_skewness=1.0,
        max_non_orthogonality=54.0,  # > 65 * 0.8 = 52
        negative_volumes=0,
    )
    assert _compute_verdict(d2) == "WARN"

    # 실패
    d3 = ReportData(
        max_aspect_ratio=10.0, max_skewness=1.0,
        max_non_orthogonality=70.0,  # > 65
        negative_volumes=0,
    )
    assert _compute_verdict(d3) == "FAIL"

    # Negative volumes
    d4 = ReportData(negative_volumes=5)
    assert _compute_verdict(d4) == "FAIL"


def test_export_pane_has_report_pdf_checkbox() -> None:
    """ExportPane에 report_pdf 체크박스."""
    from desktop.qt_app.widgets.right_column import ExportPane

    pane = ExportPane()
    assert hasattr(pane, "chk_report_pdf")
    opts = pane.get_export_options()
    assert "report_pdf" in opts


def test_foam_template_writes_required_files(tmp_path) -> None:
    """write_case_template이 controlDict/fvSchemes/fvSolution + 0.orig 생성."""
    from desktop.qt_app.foam_templates import write_case_template

    case = tmp_path / "mycase"
    case.mkdir()
    written = write_case_template(case)

    assert (case / "system" / "controlDict").exists()
    assert (case / "system" / "fvSchemes").exists()
    assert (case / "system" / "fvSolution").exists()
    assert (case / "0.orig").is_dir()
    assert len(written) >= 3

    # 내용 검증 — simpleFoam 기본
    cd = (case / "system" / "controlDict").read_text()
    assert "simpleFoam" in cd
    assert "endTime" in cd

    schemes = (case / "system" / "fvSchemes").read_text()
    assert "div(phi,U)" in schemes

    sol = (case / "system" / "fvSolution").read_text()
    assert "SIMPLE" in sol
    assert "GAMG" in sol  # pressure solver


def test_foam_template_preserves_existing_files(tmp_path) -> None:
    """write_case_template은 기존 파일 덮어쓰지 않는다 (사용자 편집 보호)."""
    from pathlib import Path as _Path

    from desktop.qt_app.foam_templates import write_case_template

    case = tmp_path / "mycase"
    (case / "system").mkdir(parents=True)
    custom = case / "system" / "controlDict"
    custom.write_text("// MY CUSTOM CONFIG\napplication pimpleFoam;\n")

    written = write_case_template(case)
    # controlDict가 written 목록에 없어야 함
    names = [_Path(p).name for p in written]
    assert "controlDict" not in names
    # 원본 내용 유지
    assert "MY CUSTOM CONFIG" in custom.read_text()


def test_export_pane_has_foam_template_checkbox() -> None:
    """ExportPane에 foam_template 체크박스 + get_export_options에 포함."""
    from desktop.qt_app.widgets.right_column import ExportPane

    pane = ExportPane()
    assert hasattr(pane, "chk_foam_template")
    opts = pane.get_export_options()
    assert "foam_template" in opts


def test_log_level_classification_variants() -> None:
    """_classify_log_level이 한·영문 변형을 정확히 분류."""
    from desktop.qt_app.main_window import AutoTessellWindow

    c = AutoTessellWindow._classify_log_level
    # ERR variants
    assert c("[ERR] 뭔가 실패") == "ERR"
    assert c("[ERROR] something") == "ERR"
    assert c("  [오류] 시간 초과") == "ERR"
    # WARN variants
    assert c("[WARN] 메시 품질 낮음") == "WARN"
    assert c("[WARNING] deprecated") == "WARN"
    assert c("[경고] 파일 크기 큼") == "WARN"
    # DBG variants
    assert c("[DBG] debug message") == "DBG"
    assert c("[DEBUG] verbose info") == "DBG"
    # INFO / OK / 진행 / 태그 없음 — 전부 INFO
    assert c("[INFO] 시작") == "INFO"
    assert c("[OK] 파이프라인 완료") == "INFO"
    assert c("[진행 42%] Generate 1/3") == "INFO"
    assert c("태그 없는 일반 메시지") == "INFO"


def test_pipeline_worker_has_intermediate_ready_signal() -> None:
    """PipelineWorker에 intermediate_ready Signal이 정의돼야 한다."""
    from pathlib import Path

    from desktop.qt_app.main_window import QualityLevel
    from desktop.qt_app.pipeline_worker import PipelineWorker

    worker = PipelineWorker(
        input_path=Path("/nonexistent/x.stl"),
        quality_level=QualityLevel.DRAFT,
        output_dir=Path("/tmp/_x"),
    )
    assert hasattr(worker, "intermediate_ready"), "intermediate_ready Signal 없음"


def test_try_emit_intermediate_preprocessed_stl(tmp_path) -> None:
    """_try_emit_intermediate — 'Preprocess 완료' 메시지 + preprocessed.stl 존재시 emit."""
    from pathlib import Path

    from PySide6.QtTest import QSignalSpy
    from desktop.qt_app.main_window import QualityLevel
    from desktop.qt_app.pipeline_worker import PipelineWorker, _try_emit_intermediate

    # 가짜 artifact 생성
    work = tmp_path / "_work"
    work.mkdir()
    pre_stl = work / "preprocessed.stl"
    pre_stl.write_text("solid stl\n" * 10)  # 더미 non-empty

    worker = PipelineWorker(
        input_path=Path("/nonexistent/x.stl"),
        quality_level=QualityLevel.DRAFT,
        output_dir=tmp_path,
    )
    spy = QSignalSpy(worker.intermediate_ready)  # type: ignore[attr-defined]
    _try_emit_intermediate(worker, "Preprocess 완료", tmp_path)

    assert spy.count() == 1
    emitted_path = spy.at(0)[0]
    emitted_label = spy.at(0)[1]
    assert "preprocessed.stl" in emitted_path
    assert "표면" in emitted_label or "Surface" in emitted_label


def test_try_emit_intermediate_iteration_polymesh(tmp_path) -> None:
    """'Generate 완료 1/3' + polyMesh 존재시 intermediate_ready emit."""
    from pathlib import Path

    from PySide6.QtTest import QSignalSpy
    from desktop.qt_app.main_window import QualityLevel
    from desktop.qt_app.pipeline_worker import PipelineWorker, _try_emit_intermediate

    poly = tmp_path / "constant" / "polyMesh"
    poly.mkdir(parents=True)
    (poly / "points").write_text("dummy")

    worker = PipelineWorker(
        input_path=Path("/nonexistent/x.stl"),
        quality_level=QualityLevel.DRAFT,
        output_dir=tmp_path,
    )
    spy = QSignalSpy(worker.intermediate_ready)  # type: ignore[attr-defined]
    _try_emit_intermediate(worker, "Generate 완료 1/3", tmp_path)

    assert spy.count() == 1


def test_try_emit_intermediate_final_iteration_skipped(tmp_path) -> None:
    """마지막 iteration (1/1 또는 3/3)은 최종이므로 emit 안 함."""
    from pathlib import Path

    from PySide6.QtTest import QSignalSpy
    from desktop.qt_app.main_window import QualityLevel
    from desktop.qt_app.pipeline_worker import PipelineWorker, _try_emit_intermediate

    poly = tmp_path / "constant" / "polyMesh"
    poly.mkdir(parents=True)
    (poly / "points").write_text("dummy")

    worker = PipelineWorker(
        input_path=Path("/nonexistent/x.stl"),
        quality_level=QualityLevel.DRAFT,
        output_dir=tmp_path,
    )
    spy = QSignalSpy(worker.intermediate_ready)  # type: ignore[attr-defined]
    _try_emit_intermediate(worker, "Generate 완료 3/3", tmp_path)  # 마지막

    assert spy.count() == 0, "최종 iteration은 emit되면 안 됨 (finished가 처리)"


def test_error_recovery_classify_openfoam_missing() -> None:
    """OpenFOAM 미설치 에러 메시지를 분류한다."""
    from desktop.qt_app.error_recovery import classify_error

    result = classify_error("FOAM FATAL ERROR: cannot find controlDict")
    assert result is not None
    guide, actions = result
    assert "OpenFOAM" in guide
    keys = [a.handler_key for a in actions]
    assert "install_openfoam" in keys
    assert "lower_quality" in keys


def test_error_recovery_classify_hausdorff() -> None:
    """Hausdorff 실패 에러를 분류한다."""
    from desktop.qt_app.error_recovery import classify_error

    result = classify_error("hausdorff ratio exceeded threshold 10%")
    assert result is not None
    guide, actions = result
    assert "Hausdorff" in guide or "지오메트리" in guide
    keys = [a.handler_key for a in actions]
    assert "repair_surface" in keys


def test_error_recovery_classify_watertight() -> None:
    """Watertight/manifold 실패 에러를 분류한다."""
    from desktop.qt_app.error_recovery import classify_error

    result = classify_error("mesh is not watertight, non-manifold edges detected")
    assert result is not None
    _, actions = result
    keys = [a.handler_key for a in actions]
    assert "enable_ai_fallback" in keys


def test_error_recovery_classify_all_tiers_failed() -> None:
    """모든 Tier 실패 → GitHub issue 액션."""
    from desktop.qt_app.error_recovery import classify_error

    result = classify_error("Failed after 3 iterations")
    assert result is not None
    _, actions = result
    keys = [a.handler_key for a in actions]
    assert "issue_url" in keys


def test_error_recovery_no_match_returns_none() -> None:
    """패턴 미매치면 None."""
    from desktop.qt_app.error_recovery import classify_error

    assert classify_error("") is None
    assert classify_error("some random unclassified error") is None


def test_preset_save_user_preset_and_load(tmp_path, monkeypatch) -> None:
    """save_user_preset + all_presets 재조회 시 새 프리셋 포함."""
    from desktop.qt_app import presets

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(presets, "_PRESETS_DIR", fake_home)
    monkeypatch.setattr(presets, "_USER_PRESETS_FILE", fake_home / "presets.json")

    custom = presets.Preset(
        name="My Custom",
        description="test",
        quality_level="standard",
        tier_hint="tier05_netgen",
    )
    presets.save_user_preset(custom)

    all_p = presets.all_presets()
    names = [p.name for p in all_p]
    assert "My Custom" in names
    assert len(all_p) == 9  # 8 builtin (5 기본 + 3 WildMesh) + 1 custom


def test_viewport_kpi_overlay_reset_clears_all() -> None:
    """reset()이 모든 행을 '—'로 초기화."""
    from desktop.qt_app.widgets.viewport_overlays import KPIStatsOverlay

    kpi = KPIStatsOverlay()
    kpi.set_value("Cells", "1000")
    kpi.set_value("Tier", "tier2_tetwild")
    kpi.reset()
    assert kpi._rows["Cells"].text() == "—"
    assert kpi._rows["Tier"].text() == "—"


def test_quality_pane_histogram_updates_with_arrays() -> None:
    """QualityPane.histogram.update_histograms가 실제 데이터로 matplotlib 렌더 (3 메트릭)."""
    from desktop.qt_app.widgets.right_column import QualityPane, _MPL_AVAILABLE

    pane = QualityPane()
    assert hasattr(pane, "histogram"), "QualityPane.histogram 속성 없음"
    # 데이터 없이도 예외 없음
    pane.histogram.update_histograms()
    pane.histogram.update_histograms(
        aspect_data=[1.1, 1.2, 1.5, 2.0, 1.8],
        skew_data=[0.1, 0.2, 0.05, 0.3],
        non_ortho_data=[30.0, 45.0, 55.0, 62.0, 40.0],
    )
    if _MPL_AVAILABLE:
        assert pane.histogram._canvas is not None, "matplotlib 사용 가능인데 canvas None"
        # 3개 서브플롯 확인
        axes = pane.histogram._fig.get_axes()
        assert len(axes) == 3, f"3 subplot 기대, 실제 {len(axes)}"
        titles = [ax.get_title() for ax in axes]
        assert any("Aspect" in t for t in titles)
        assert any("Skew" in t for t in titles)
        assert any("Non-ortho" in t or "non-ortho" in t.lower() for t in titles)


def test_job_pane_log_box_receives_appended_text() -> None:
    """JobPane.log_box.appendPlainText이 실제로 로그 누적."""
    from desktop.qt_app.widgets.right_column import JobPane

    pane = JobPane()
    pane.log_box.appendPlainText("[INFO] first line")
    pane.log_box.appendPlainText("[ERR] second line")
    content = pane.log_box.toPlainText()
    assert "first line" in content
    assert "second line" in content


def test_job_pane_log_filter_chips_exist_with_clicked_signal() -> None:
    """JobPane 필터 chip들이 clicked Signal을 emit할 수 있어야 한다."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QSignalSpy, QTest
    from desktop.qt_app.widgets.right_column import JobPane

    pane = JobPane()
    pane.chip_info.resize(50, 24)
    spy = QSignalSpy(pane.chip_info.clicked)
    QTest.mouseClick(pane.chip_info, Qt.MouseButton.LeftButton)
    assert spy.count() >= 1, "chip_info 클릭 → clicked Signal 미발생"


def test_tier_pipeline_strip_resume_stop_rerun_signals() -> None:
    """TierPipelineStrip 버튼 클릭 → resume/stop/rerun_requested Signal emit."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QSignalSpy, QTest
    from desktop.qt_app.widgets.tier_pipeline import TierPipelineStrip

    strip = TierPipelineStrip()
    strip.set_tiers([("A", "a"), ("B", "b")])

    run_spy = QSignalSpy(strip.run_requested)
    stop_spy = QSignalSpy(strip.stop_requested)
    rerun_spy = QSignalSpy(strip.rerun_requested)
    reset_spy = QSignalSpy(strip.reset_requested)

    # idle 상태: run_btn만 visible
    strip.set_state("idle")
    QTest.mouseClick(strip.run_btn, Qt.MouseButton.LeftButton)

    # running 상태: stop_btn만 visible
    strip.set_state("running")
    QTest.mouseClick(strip.stop_btn, Qt.MouseButton.LeftButton)

    # done 상태: rerun + reset visible
    strip.set_state("done")
    QTest.mouseClick(strip.rerun_btn, Qt.MouseButton.LeftButton)
    QTest.mouseClick(strip.reset_btn, Qt.MouseButton.LeftButton)

    assert run_spy.count() == 1
    assert stop_spy.count() == 1
    assert rerun_spy.count() == 1
    assert reset_spy.count() == 1


def test_drop_zone_drag_and_drop_emits_file_dropped() -> None:
    """DropZone에 파일 drop 이벤트 → file_dropped Signal emit 검증."""
    from pathlib import Path

    from PySide6.QtCore import QMimeData, QPoint, QPointF, QUrl, Qt
    from PySide6.QtGui import QDropEvent
    from PySide6.QtTest import QSignalSpy
    from desktop.qt_app.drop_zone import DropZone

    dz = DropZone()
    dz.resize(200, 100)
    spy = QSignalSpy(dz.file_dropped)

    tmp_file = Path("/tmp/test_dz_drop.stl")
    tmp_file.write_text("fake")
    try:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(tmp_file))])
        drop = QDropEvent(
            QPointF(50, 50),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        dz.dropEvent(drop)
        assert spy.count() == 1
        assert spy.at(0)[0] == str(tmp_file)
    finally:
        tmp_file.unlink(missing_ok=True)


def test_try_emit_quality_roundtrip() -> None:
    """_try_emit_quality가 progress 메시지를 파싱해 quality_update Signal emit."""
    from desktop.qt_app.main_window import QualityLevel
    from desktop.qt_app.pipeline_worker import PipelineWorker, _try_emit_quality
    from pathlib import Path

    # PipelineWorker 인스턴스 필요 (QThread + Signal)
    worker = PipelineWorker(
        input_path=Path("/nonexistent/x.stl"),
        quality_level=QualityLevel.DRAFT,
        output_dir=Path("/tmp/_x"),
    )
    # 시작은 하지 않음 — Signal만 직접 테스트

    from PySide6.QtTest import QSignalSpy
    spy = QSignalSpy(worker.quality_update)  # type: ignore[attr-defined]

    _try_emit_quality(worker, "max_non_orthogonality: 62.5 deg")
    _try_emit_quality(worker, "max_skewness: 3.2")
    _try_emit_quality(worker, "아무 관련 없는 메시지")

    assert spy.count() >= 1, \
        f"non_ortho/skew 메시지가 파싱되지 않음 (count={spy.count()})"


@pytest.mark.slow
def test_pipeline_worker_requestInterruption_emits_finished(tmp_path) -> None:
    """requestInterruption() 후 finished Signal이 반드시 emit돼야 한다 (UI stuck 방지)."""
    from pathlib import Path

    from desktop.qt_app.main_window import QualityLevel
    from desktop.qt_app.pipeline_worker import PipelineWorker

    sphere = Path(__file__).parent / "benchmarks" / "sphere.stl"
    out_dir = tmp_path / "case"
    worker = PipelineWorker(
        input_path=sphere,
        quality_level=QualityLevel.DRAFT,
        output_dir=out_dir,
    )

    finished_flag: list = [False]
    worker.finished.connect(lambda _r: finished_flag.__setitem__(0, True))  # type: ignore[attr-defined]

    worker.start()  # type: ignore[attr-defined]
    # 즉시 중단 요청 — _on_progress 첫 호출 시 InterruptedError
    worker.requestInterruption()  # type: ignore[attr-defined]

    try:
        # finished는 반드시 emit돼야 함 (성공/실패 무관) — UI stuck 버그 방지 회귀 테스트
        assert _wait_for_signal(finished_flag, worker, timeout_s=60.0), \
            "중단 후 finished 미수신 — UI stuck 재현됨"
        worker.wait(5_000)  # type: ignore[attr-defined]
    finally:
        if worker.isRunning():  # type: ignore[attr-defined]
            worker.requestInterruption()  # type: ignore[attr-defined]
            worker.wait(5_000)  # type: ignore[attr-defined]


# ═══════════════════════════════════════════════════════════════════════════
# Codex GUI Verification Handoff — interaction, QSS, signal, modal tests
# ═══════════════════════════════════════════════════════════════════════════


def test_engine_policy_switch_rebuilds_dropdown(monkeypatch, tmp_path) -> None:
    """정책 변경시 드롭다운 disabled 아이템 수가 바뀌어야 한다."""
    from desktop.qt_app import engine_policy
    from desktop.qt_app import mesh_viewer
    from desktop.qt_app.main_window import AutoTessellWindow

    monkeypatch.setattr(mesh_viewer, "PYVISTAQT_AVAILABLE", False)
    monkeypatch.setattr(engine_policy, "_POLICY_DIR", tmp_path / "x")
    monkeypatch.setattr(engine_policy, "_POLICY_FILE", tmp_path / "x" / "p.json")
    monkeypatch.delenv("AUTOTESSELL_ENGINE_POLICY", raising=False)

    win = AutoTessellWindow()
    win._build()
    assert win._engine_combo is not None

    def _count_enabled() -> int:
        model = win._engine_combo.model()
        enabled = 0
        for i in range(model.rowCount()):
            item = model.item(i)
            if item and item.isEnabled():
                enabled += 1
        return enabled

    before = _count_enabled()
    engine_policy.set_mode("wildmesh_only")
    win._rebuild_engine_combo_model()
    after = _count_enabled()

    assert after < before
    assert after >= 2


def test_preset_wildmesh_fine_syncs_slider_panel(monkeypatch, tmp_path) -> None:
    """WildMesh Fine 프리셋 선택 → 슬라이더 값이 프리셋 params와 동기화된다."""
    from desktop.qt_app import engine_policy
    from desktop.qt_app import mesh_viewer
    from desktop.qt_app.main_window import AutoTessellWindow
    from desktop.qt_app.presets import get

    monkeypatch.setattr(mesh_viewer, "PYVISTAQT_AVAILABLE", False)
    monkeypatch.setattr(engine_policy, "_POLICY_DIR", tmp_path / "ep")
    monkeypatch.setattr(engine_policy, "_POLICY_FILE", tmp_path / "ep" / "p.json")
    monkeypatch.delenv("AUTOTESSELL_ENGINE_POLICY", raising=False)

    win = AutoTessellWindow()
    win._build()

    preset = get("WildMesh Fine (Feature Preserving)")
    assert preset is not None

    for i in range(win._preset_combo.count()):
        if win._preset_combo.itemData(i) == preset.name:
            win._preset_combo.setCurrentIndex(i)
            break

    cur = win._wildmesh_param_panel.current_params()
    assert abs(cur["wildmesh_epsilon"] - 0.0003) < 1e-4
    assert abs(cur["wildmesh_edge_length_r"] - 0.02) < 1e-3
    assert int(cur["wildmesh_stop_quality"]) == 5


def test_signal_connections_completeness(monkeypatch) -> None:
    """최근 위젯 주요 signal이 실제 receiver를 갖고 있어야 한다."""
    from desktop.qt_app import mesh_viewer
    from desktop.qt_app.main_window import AutoTessellWindow

    monkeypatch.setattr(mesh_viewer, "PYVISTAQT_AVAILABLE", False)
    win = AutoTessellWindow()
    win._build()

    def _receivers(obj, signal) -> int:
        sig = repr(signal).split("SignalInstance ", 1)[1].split(" at ", 1)[0]
        return obj.receivers(f"2{sig}")

    checks = [
        ("_drop_label", "clicked", 1),
        ("_drop_label", "file_dropped", 1),
        ("_tier_pipeline", "tier_clicked", 1),
        ("_tier_pipeline", "run_requested", 1),
        ("_tier_pipeline", "stop_requested", 1),
        ("_tier_pipeline", "rerun_requested", 1),
        ("_tier_pipeline", "reset_requested", 1),
        ("_wildmesh_param_panel", "params_changed", 1),
    ]
    for attr, sig_name, min_r in checks:
        obj = getattr(win, attr, None)
        assert obj is not None, f"{attr} 없음"
        signal = getattr(obj, sig_name, None)
        assert signal is not None, f"{attr}.{sig_name} 없음"
        receivers = _receivers(obj, signal)
        assert receivers >= min_r, (
            f"{attr}.{sig_name} receivers={receivers} < {min_r}"
        )


def test_export_pane_signal_wired(monkeypatch) -> None:
    """ExportPane.save_requested → main_window handler 연결 확인."""
    from desktop.qt_app import mesh_viewer
    from desktop.qt_app.main_window import AutoTessellWindow

    monkeypatch.setattr(mesh_viewer, "PYVISTAQT_AVAILABLE", False)
    win = AutoTessellWindow()
    win._build()
    assert win._right_column is not None
    pane = win._right_column.export_pane
    sig = repr(pane.save_requested).split("SignalInstance ", 1)[1].split(" at ", 1)[0]
    receivers = pane.receivers(f"2{sig}")
    assert receivers >= 1


def test_dialog_qss_uses_palette() -> None:
    """공통 다이얼로그 QSS는 PALETTE 기반으로 생성된다."""
    import inspect

    from desktop.qt_app.main_window import PALETTE, get_dialog_qss, get_table_qss

    qss = get_dialog_qss()
    table_qss = get_table_qss()
    assert PALETTE["dialog_bg"] in qss
    assert PALETTE["text_0"] in qss
    assert PALETTE["line_1"] in table_qss

    src = inspect.getsource(get_dialog_qss) + inspect.getsource(get_table_qss)
    assert "#0f1318" not in src
    assert "#e8ecf2" not in src


def test_esc_dismisses_batch_dialog() -> None:
    """Esc 키 → BatchDialog reject 호출."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from desktop.qt_app.batch_dialog import BatchDialog

    d = BatchDialog()
    rejected = []
    d.rejected.connect(lambda: rejected.append(True))

    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    d.keyPressEvent(event)
    assert rejected == [True]


def test_esc_dismisses_history_and_error_dialogs() -> None:
    """Esc 키 공통 mixin이 이력/에러 복구 다이얼로그에도 적용된다."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from desktop.qt_app.error_recovery import ErrorRecoveryDialog
    from desktop.qt_app.history_dialog import HistoryDialog

    for dialog in (HistoryDialog(), ErrorRecoveryDialog()):
        event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
        rejected = []
        dialog.rejected.connect(lambda: rejected.append(True))
        dialog.keyPressEvent(event)
        assert rejected == [True]


def test_engine_policy_wildmesh_only_marks_blocked_items(monkeypatch, tmp_path) -> None:
    """wildmesh_only 모델에는 wildmesh 외 엔진에 정책 차단 마커가 있어야 한다."""
    from desktop.qt_app import engine_policy
    from desktop.qt_app.main_window import AutoTessellWindow

    monkeypatch.setattr(engine_policy, "_POLICY_DIR", tmp_path / "ep")
    monkeypatch.setattr(engine_policy, "_POLICY_FILE", tmp_path / "ep" / "p.json")
    monkeypatch.delenv("AUTOTESSELL_ENGINE_POLICY", raising=False)
    engine_policy.set_mode("wildmesh_only")

    win = AutoTessellWindow()
    model, _ = win._make_engine_combo_model()
    labels = [
        model.item(i).text()
        for i in range(model.rowCount())
        if model.item(i) is not None
    ]
    assert any("정책 차단" in label for label in labels)
    assert any("WildMesh" in label and "정책 차단" not in label for label in labels)


def test_engine_policy_all_mode_has_no_blocked_items(monkeypatch, tmp_path) -> None:
    """all 모드 모델에는 정책 차단 마커가 없어야 한다."""
    from desktop.qt_app import engine_policy
    from desktop.qt_app.main_window import AutoTessellWindow

    monkeypatch.setattr(engine_policy, "_POLICY_DIR", tmp_path / "ep")
    monkeypatch.setattr(engine_policy, "_POLICY_FILE", tmp_path / "ep" / "p.json")
    monkeypatch.delenv("AUTOTESSELL_ENGINE_POLICY", raising=False)
    engine_policy.set_mode("all")

    win = AutoTessellWindow()
    model, _ = win._make_engine_combo_model()
    labels = [
        model.item(i).text()
        for i in range(model.rowCount())
        if model.item(i) is not None
    ]
    assert all("정책 차단" not in label for label in labels)


def test_wildmesh_draft_preset_syncs_slider_panel(monkeypatch, tmp_path) -> None:
    """WildMesh Draft 프리셋도 슬라이더 패널에 정확히 적용된다."""
    from desktop.qt_app import engine_policy, mesh_viewer
    from desktop.qt_app.main_window import AutoTessellWindow

    monkeypatch.setattr(mesh_viewer, "PYVISTAQT_AVAILABLE", False)
    monkeypatch.setattr(engine_policy, "_POLICY_DIR", tmp_path / "ep")
    monkeypatch.setattr(engine_policy, "_POLICY_FILE", tmp_path / "ep" / "p.json")
    monkeypatch.delenv("AUTOTESSELL_ENGINE_POLICY", raising=False)

    win = AutoTessellWindow()
    win._build()
    idx = win._preset_combo.findData("WildMesh Draft")
    assert idx >= 0
    win._preset_combo.setCurrentIndex(idx)

    cur = win._wildmesh_param_panel.current_params()
    assert abs(cur["wildmesh_epsilon"] - 0.002) < 1e-4
    assert abs(cur["wildmesh_edge_length_r"] - 0.06) < 1e-3
    assert int(cur["wildmesh_stop_quality"]) == 20


def test_wildmesh_standard_preset_syncs_slider_panel(monkeypatch, tmp_path) -> None:
    """WildMesh Standard 프리셋도 슬라이더 패널에 정확히 적용된다."""
    from desktop.qt_app import engine_policy, mesh_viewer
    from desktop.qt_app.main_window import AutoTessellWindow

    monkeypatch.setattr(mesh_viewer, "PYVISTAQT_AVAILABLE", False)
    monkeypatch.setattr(engine_policy, "_POLICY_DIR", tmp_path / "ep")
    monkeypatch.setattr(engine_policy, "_POLICY_FILE", tmp_path / "ep" / "p.json")
    monkeypatch.delenv("AUTOTESSELL_ENGINE_POLICY", raising=False)

    win = AutoTessellWindow()
    win._build()
    idx = win._preset_combo.findData("WildMesh Standard")
    assert idx >= 0
    win._preset_combo.setCurrentIndex(idx)

    cur = win._wildmesh_param_panel.current_params()
    assert abs(cur["wildmesh_epsilon"] - 0.001) < 1e-4
    assert abs(cur["wildmesh_edge_length_r"] - 0.04) < 1e-3
    assert int(cur["wildmesh_stop_quality"]) == 10


def test_dialog_classes_use_esc_mixin() -> None:
    """커스텀 다이얼로그 클래스가 EscDismissMixin을 상속한다."""
    from desktop.qt_app.batch_dialog import BatchDialog
    from desktop.qt_app.error_recovery import ErrorRecoveryDialog
    from desktop.qt_app.history_dialog import HistoryDialog
    from desktop.qt_app.widgets.dialog_mixin import EscDismissMixin

    assert issubclass(BatchDialog, EscDismissMixin)
    assert issubclass(HistoryDialog, EscDismissMixin)
    assert issubclass(ErrorRecoveryDialog, EscDismissMixin)


def test_batch_dialog_uses_common_qss_helpers() -> None:
    """BatchDialog 루트/테이블 스타일은 공통 QSS 헬퍼 결과를 사용한다."""
    from desktop.qt_app.batch_dialog import BatchDialog
    from desktop.qt_app.main_window import get_dialog_qss, get_table_qss

    dlg = BatchDialog()
    assert dlg.styleSheet() == get_dialog_qss()
    assert dlg.table.styleSheet() == get_table_qss()


def test_history_dialog_uses_common_qss_helpers(tmp_path, monkeypatch) -> None:
    """HistoryDialog 루트/테이블 스타일은 공통 QSS 헬퍼 결과를 사용한다."""
    from desktop.qt_app import history
    from desktop.qt_app.history_dialog import HistoryDialog
    from desktop.qt_app.main_window import get_dialog_qss, get_table_qss

    monkeypatch.setattr(history, "_HISTORY_DIR", tmp_path / "x")
    monkeypatch.setattr(history, "_HISTORY_FILE", tmp_path / "x" / "h.json")

    dlg = HistoryDialog()
    assert dlg.styleSheet() == get_dialog_qss()
    assert dlg.table.styleSheet() == get_table_qss()


def test_error_recovery_dialog_uses_common_dialog_qss() -> None:
    """ErrorRecoveryDialog 루트 스타일은 공통 다이얼로그 QSS를 사용한다."""
    from desktop.qt_app.error_recovery import ErrorRecoveryDialog
    from desktop.qt_app.main_window import get_dialog_qss

    dlg = ErrorRecoveryDialog()
    assert dlg.styleSheet() == get_dialog_qss()


def test_sidebar_uses_scroll_area() -> None:
    """사이드바는 작은 viewport에서도 잘리지 않도록 QScrollArea를 사용한다."""
    from PySide6.QtWidgets import QScrollArea
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    sidebar = win._build_sidebar()
    assert isinstance(sidebar, QScrollArea)
    assert sidebar.widgetResizable() is True
    assert sidebar.widget() is not None


def test_pipeline_worker_signals_wired_in_main_window_source() -> None:
    """main window 실행 경로가 PipelineWorker 주요 signal을 연결한다."""
    import inspect
    from desktop.qt_app.main_window import AutoTessellWindow

    src = inspect.getsource(AutoTessellWindow._on_run_clicked)
    for signal_name in (
        "progress.connect",
        "progress_percent.connect",
        "quality_update.connect",
        "intermediate_ready.connect",
        "finished.connect",
    ):
        assert signal_name in src, f"{signal_name} 연결 없음"


def test_history_dialog_filter_signals_wired(tmp_path, monkeypatch) -> None:
    """HistoryDialog 필터 combo/search edit signal이 refresh에 연결돼야 한다."""
    from desktop.qt_app import history
    from desktop.qt_app.history_dialog import HistoryDialog

    monkeypatch.setattr(history, "_HISTORY_DIR", tmp_path / "x")
    monkeypatch.setattr(history, "_HISTORY_FILE", tmp_path / "x" / "h.json")

    dlg = HistoryDialog()

    combo_sig = repr(dlg.status_combo.currentIndexChanged).split(
        "SignalInstance ", 1
    )[1].split(" at ", 1)[0]
    search_sig = repr(dlg.search_edit.textChanged).split(
        "SignalInstance ", 1
    )[1].split(" at ", 1)[0]
    assert dlg.status_combo.receivers(f"2{combo_sig}") >= 1
    assert dlg.search_edit.receivers(f"2{search_sig}") >= 1


def test_batch_dialog_selection_signal_updates_remove_button(tmp_path) -> None:
    """BatchDialog table selection changed → 선택 제거 버튼 상태 갱신."""
    from pathlib import Path
    from desktop.qt_app.batch import BatchJob
    from desktop.qt_app.batch_dialog import BatchDialog

    dlg = BatchDialog()
    f = tmp_path / "x.stl"
    f.write_text("solid")
    dlg.add_jobs([BatchJob(Path(f), tmp_path / "case")])

    assert dlg.remove_btn.isEnabled() is False
    dlg.table.selectRow(0)
    assert dlg.remove_btn.isEnabled() is True

    sig = repr(dlg.table.itemSelectionChanged).split(
        "SignalInstance ", 1
    )[1].split(" at ", 1)[0]
    assert dlg.table.receivers(f"2{sig}") >= 1


def test_compare_dialog_loads_two_cases(tmp_path) -> None:
    """CompareDialog가 두 OpenFOAM case 디렉토리를 로드하고 표를 갱신한다."""
    from desktop.qt_app.compare_dialog import CompareDialog

    case_a = tmp_path / "case_a"
    case_b = tmp_path / "case_b"
    for case in (case_a, case_b):
        poly = case / "constant" / "polyMesh"
        poly.mkdir(parents=True)
        (poly / "points").write_text("dummy")

    dlg = CompareDialog()
    dlg.set_case_path("A", case_a)
    dlg.set_case_path("B", case_b)
    loaded_a, loaded_b = dlg.load_selected()

    assert loaded_a is True
    assert loaded_b is True
    assert dlg.table.rowCount() == 4
    assert dlg.table.item(3, 1).text() != "-"
    assert dlg.table.item(3, 2).text() != "-"


def test_compare_dialog_camera_sync() -> None:
    """A viewer camera state 변경 → B viewer에 동기화된다."""
    from desktop.qt_app.compare_dialog import CompareDialog

    dlg = CompareDialog()
    dlg.sync_camera_check.setChecked(True)
    dlg.viewer_a.emit_camera_state({"view": "front", "position": [1, 2, 3]})

    assert dlg.viewer_b._camera_state["view"] == "front"
    assert dlg.viewer_b._camera_state["position"] == [1, 2, 3]

    dlg.sync_camera_check.setChecked(False)
    dlg.viewer_a.emit_camera_state({"view": "top"})
    assert dlg.viewer_b._camera_state["view"] == "front"


def test_compare_dialog_histogram_overlay() -> None:
    """CompareDialog histogram overlay가 A/B 데이터를 가진 3개 subplot을 만든다."""
    from desktop.qt_app.compare_dialog import CompareDialog

    dlg = CompareDialog()
    dlg._on_stats(
        "A",
        {
            "hist_aspect_ratio": [1.0, 1.2, 1.4],
            "hist_skewness": [0.1, 0.2, 0.3],
            "hist_non_orthogonality": [10.0, 20.0, 30.0],
            "n_cells": 10,
        },
    )
    dlg._on_stats(
        "B",
        {
            "hist_aspect_ratio": [1.1, 1.3, 1.5],
            "hist_skewness": [0.2, 0.3, 0.4],
            "hist_non_orthogonality": [12.0, 22.0, 32.0],
            "n_cells": 12,
        },
    )

    if dlg.histogram._fig is not None:
        axes = dlg.histogram._fig.get_axes()
        assert len(axes) == 3
    assert dlg.table.item(3, 3).text().startswith("+")


def test_main_window_compare_menu_action_wired() -> None:
    """main window에 도구→메시 비교 Ctrl+D 메뉴 액션이 연결돼야 한다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    win._build()
    actions = win._qmain.menuBar().actions()
    tools = [a.menu() for a in actions if a.text() == "도구"]
    assert tools and tools[0] is not None
    compare_actions = [a for a in tools[0].actions() if "메시 비교" in a.text()]
    assert compare_actions
    assert compare_actions[0].shortcut().toString() == "Ctrl+D"


def test_qt_app_module_entrypoint_exists() -> None:
    """QA 명령 `python -m desktop.qt_app`가 실행 가능한 module entrypoint를 가져야 한다."""
    import importlib.util
    import inspect

    spec = importlib.util.find_spec("desktop.qt_app.__main__")
    assert spec is not None

    import desktop.qt_app.__main__ as entry

    src = inspect.getsource(entry)
    assert "desktop.qt_main" in src
    assert "main()" in src


def test_qt_main_pyvista_runtime_respects_display(monkeypatch) -> None:
    """실제 display가 있으면 PyVista offscreen을 강제하지 않아야 한다."""
    import sys
    from types import SimpleNamespace

    from desktop.qt_main import _configure_pyvista_runtime

    calls: list[str] = []
    fake_pyvista = SimpleNamespace(
        OFF_SCREEN=None,
        start_xvfb=lambda: calls.append("xvfb"),
    )
    monkeypatch.setitem(sys.modules, "pyvista", fake_pyvista)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    _configure_pyvista_runtime()

    assert fake_pyvista.OFF_SCREEN is False
    assert calls == []


def test_qt_main_pyvista_runtime_uses_offscreen_when_headless(monkeypatch) -> None:
    """display가 없거나 Qt offscreen이면 PyVista offscreen fallback을 사용한다."""
    import sys
    from types import SimpleNamespace

    from desktop.qt_main import _configure_pyvista_runtime

    calls: list[str] = []
    fake_pyvista = SimpleNamespace(
        OFF_SCREEN=None,
        start_xvfb=lambda: calls.append("xvfb"),
    )
    monkeypatch.setitem(sys.modules, "pyvista", fake_pyvista)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    _configure_pyvista_runtime()

    assert fake_pyvista.OFF_SCREEN is True


def test_mesh_viewer_runtime_detects_headless_and_static_flag(monkeypatch) -> None:
    """mesh_viewer도 Qt runtime 상태와 정적 뷰어 강제 flag를 따라야 한다."""
    from desktop.qt_app import mesh_viewer

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("AUTOTESSELL_STATIC_VIEWER", "1")

    assert mesh_viewer._qt_runtime_is_headless() is True
    assert mesh_viewer._force_static_viewer_requested() is True


def test_main_window_qss_avoids_unsupported_box_shadow() -> None:
    """Qt QSS가 지원하지 않는 box-shadow 속성을 사용하지 않는다."""
    from pathlib import Path

    src = Path("desktop/qt_app/main_window.py").read_text(encoding="utf-8")
    assert "box-shadow" not in src


def test_mesh_viewer_prefers_foam_to_vtk_preview(tmp_path) -> None:
    """polyMesh 직접 reader보다 foamToVTK preview 파일을 우선 사용한다."""
    from desktop.qt_app.mesh_viewer import _find_case_preview_mesh

    poly_dir = tmp_path / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True)
    (poly_dir / "points").write_text("", encoding="utf-8")
    vtk_dir = tmp_path / "VTK" / "case_0"
    vtk_dir.mkdir(parents=True)
    internal_vtu = vtk_dir / "internal.vtu"
    internal_vtu.write_text("<VTKFile />", encoding="utf-8")

    assert _find_case_preview_mesh(tmp_path) == internal_vtu


def test_interactive_polymesh_load_uses_preview_before_openfoam_reader(tmp_path, monkeypatch) -> None:
    """VTK preview가 있으면 OpenFOAMReader 경로를 타지 않는다."""
    from types import SimpleNamespace

    from desktop.qt_app.mesh_viewer import InteractiveMeshViewer

    poly_dir = tmp_path / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True)
    (poly_dir / "points").write_text("", encoding="utf-8")
    vtk_dir = tmp_path / "VTK" / "case_0"
    vtk_dir.mkdir(parents=True)
    internal_vtu = vtk_dir / "internal.vtu"
    internal_vtu.write_text("<VTKFile />", encoding="utf-8")

    calls: list[tuple[str, bool]] = []

    def _load_mesh(path, show_edges=True):
        calls.append((str(path), show_edges))
        return True

    fake = SimpleNamespace(load_mesh=_load_mesh)
    monkeypatch.setattr(
        InteractiveMeshViewer,
        "_read_openfoam",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("OpenFOAMReader called")),
    )

    assert InteractiveMeshViewer.load_polymesh(fake, tmp_path) is True
    assert calls == [(str(internal_vtu), True)]


def test_interactive_polymesh_direct_preview_is_opt_in(tmp_path, monkeypatch) -> None:
    """VTK preview가 없으면 polyMesh 직접 preview를 기본 비활성화한다."""
    from types import SimpleNamespace

    from desktop.qt_app.mesh_viewer import InteractiveMeshViewer

    poly_dir = tmp_path / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True)
    (poly_dir / "points").write_text("", encoding="utf-8")
    messages: list[str] = []
    fake = SimpleNamespace(_info_label=SimpleNamespace(setText=messages.append))
    monkeypatch.delenv("AUTOTESSELL_POLYMESH_DIRECT_PREVIEW", raising=False)
    monkeypatch.setattr(
        InteractiveMeshViewer,
        "_read_openfoam",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("OpenFOAMReader called")),
    )

    assert InteractiveMeshViewer.load_polymesh(fake, tmp_path) is True
    assert messages
    assert "foamToVTK" in messages[-1]


# ═══════════════════════════════════════════════════════════════════════════
# Fix Regression Tests: GUI freeze / progress / sidebar duplicate
# ═══════════════════════════════════════════════════════════════════════════


def test_set_pipeline_running_method_exists() -> None:
    """_set_pipeline_running 헬퍼가 AutoTessellWindow에 있어야 한다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert hasattr(win, "_set_pipeline_running"), "_set_pipeline_running 메서드 필요"
    assert callable(win._set_pipeline_running)
    # _build 없이 호출해도 예외 없이 동작 (위젯 None 상태)
    win._set_pipeline_running(True)
    win._set_pipeline_running(False)


def test_pipeline_start_time_initialized_in_init() -> None:
    """_pipeline_start_time이 __init__에서 0.0으로 초기화되어야 한다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert hasattr(win, "_pipeline_start_time"), "_pipeline_start_time 초기화 필요"
    assert win._pipeline_start_time == 0.0


def test_stage_to_tier_mapping_defined() -> None:
    """_STAGE_TO_TIER 클래스 속성이 정의되어 있어야 한다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    assert hasattr(AutoTessellWindow, "_STAGE_TO_TIER"), "_STAGE_TO_TIER 없음"
    mapping = AutoTessellWindow._STAGE_TO_TIER
    assert isinstance(mapping, list), "_STAGE_TO_TIER는 list여야 한다"
    assert len(mapping) >= 5, "최소 5개 단계 (Analyze/Preprocess/Strateg/Generat/Evaluat)"
    keywords = [kw for kw, _ in mapping]
    assert any("Analyze" in kw for kw in keywords), "Analyze 단계 없음"
    assert any("Evaluat" in kw for kw in keywords), "Evaluate 단계 없음"


def test_on_progress_line_tier_strip_updates_by_keyword() -> None:
    """_on_progress_line이 키워드로 Tier strip 상태를 올바르게 갱신한다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()

    # 가짜 Tier pipeline 스텁
    statuses: dict[int, str] = {i: "pending" for i in range(6)}

    class _FakeTier:
        def set_status(self, idx: int, status: str) -> None:
            statuses[idx] = status

    win._tier_pipeline = _FakeTier()

    # "Analyze" 키워드 → index 0 active
    win._on_progress_line("[진행 10%] Analyze 시작")
    assert statuses[0] == "active", f"Analyze 단계 active 기대, 실제: {statuses[0]}"

    # "Preprocess 완료" → index 0,1 done
    win._on_progress_line("[진행 30%] Preprocess 완료")
    assert statuses[0] == "done", f"Preprocess 완료 후 index 0 done 기대"
    assert statuses[1] == "done", f"Preprocess 완료 후 index 1 done 기대"


def test_surface_mesh_duplicate_refs_initialized() -> None:
    """Surface Mesh 중복 방지용 위젯 ref들이 __init__ 후 존재한다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    assert hasattr(win, "_surface_size_lbl_el"), "_surface_size_lbl_el 초기화 필요"
    assert hasattr(win, "_surface_size_lbl_min"), "_surface_size_lbl_min 초기화 필요"
    assert hasattr(win, "_surface_size_dup_hint"), "_surface_size_dup_hint 초기화 필요"
    # _build 전에는 None
    assert win._surface_size_lbl_el is None
    assert win._surface_size_lbl_min is None
    assert win._surface_size_dup_hint is None


def test_refresh_surface_mesh_section_for_tier_no_error_before_build() -> None:
    """_refresh_surface_mesh_section_for_tier는 _build 전에 호출해도 예외 없이 처리한다."""
    from desktop.qt_app.main_window import AutoTessellWindow

    win = AutoTessellWindow()
    # 위젯이 None인 상태에서도 예외 없이 동작해야 함
    win._refresh_surface_mesh_section_for_tier("wildmesh")
    win._refresh_surface_mesh_section_for_tier("netgen")


def test_on_pipeline_finished_restores_run_button() -> None:
    """_on_pipeline_finished 호출 후 _set_pipeline_running(False)가 호출되어야 한다 (소스 검증)."""
    import inspect
    from desktop.qt_app.main_window import AutoTessellWindow

    src = inspect.getsource(AutoTessellWindow._on_pipeline_finished)
    assert "_set_pipeline_running(False)" in src, \
        "_on_pipeline_finished에 _set_pipeline_running(False) 없음"


def test_on_run_clicked_sets_pipeline_running(monkeypatch) -> None:
    """_on_run_clicked가 _set_pipeline_running(True)를 호출한다 (소스 검증)."""
    import inspect
    from desktop.qt_app.main_window import AutoTessellWindow

    src = inspect.getsource(AutoTessellWindow._on_run_clicked)
    assert "_set_pipeline_running(True)" in src, \
        "_on_run_clicked에 _set_pipeline_running(True) 없음"
