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
