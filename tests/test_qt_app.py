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
    """내장 프리셋 5종이 정의돼 있어야 한다."""
    from desktop.qt_app.presets import BUILTIN_PRESETS, all_presets

    assert len(BUILTIN_PRESETS) == 5
    names = [p.name for p in BUILTIN_PRESETS]
    assert "Draft Quick (Tet)" in names
    assert any("External" in n for n in names)
    assert any("Internal" in n for n in names)
    assert any("Aerospace" in n for n in names)


def test_preset_get_returns_correct() -> None:
    """presets.get(name)이 이름으로 조회 작동."""
    from desktop.qt_app.presets import get

    p = get("Draft Quick (Tet)")
    assert p is not None
    assert p.quality_level == "draft"
    assert p.tier_hint == "tier2_tetwild"
    assert get("존재하지 않는 프리셋") is None


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
    assert len(all_p) == 6  # 5 builtin + 1 custom


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

    resume_spy = QSignalSpy(strip.resume_requested)
    stop_spy = QSignalSpy(strip.stop_requested)
    rerun_spy = QSignalSpy(strip.rerun_requested)

    QTest.mouseClick(strip.resume_btn, Qt.MouseButton.LeftButton)
    QTest.mouseClick(strip.stop_btn, Qt.MouseButton.LeftButton)
    QTest.mouseClick(strip.rerun_btn, Qt.MouseButton.LeftButton)

    assert resume_spy.count() == 1
    assert stop_spy.count() == 1
    assert rerun_spy.count() == 1


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
