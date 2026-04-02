## 메쉬 생성 파라미터 설정 패널
## CLI의 모든 옵션을 GUI에서 수정할 수 있게 한다.
extends PanelContainer

# -----------------------------------------------------------------------
# Signals
# -----------------------------------------------------------------------
signal params_changed(params: Dictionary)

# -----------------------------------------------------------------------
# All configurable parameters with defaults
# -----------------------------------------------------------------------
var _params := {
	# Quality / Tier
	"quality": "standard",
	"tier": "auto",

	# Engine selection
	"repair_engine": "auto",
	"remesh_engine": "auto",
	"volume_engine": "auto",
	"checker_engine": "auto",
	"cad_engine": "auto",
	"postprocess_engine": "auto",

	# Cell size
	"element_size": 0.0,        # 0 = auto
	"base_cell_size": 0.0,
	"min_cell_size": 0.0,
	"base_cell_num": 50,

	# Domain
	"domain_upstream": 0.0,     # 0 = auto (quality-dependent)
	"domain_downstream": 0.0,
	"domain_lateral": 0.0,
	"domain_scale": 1.0,

	# Memory limit
	"max_cells": 0,             # 0 = no limit

	# Boundary Layer
	"bl_layers": 0,             # 0 = auto (quality-dependent)
	"bl_first_height": 0.0,
	"bl_growth_ratio": 1.2,

	# Preprocessor
	"no_repair": false,
	"force_remesh": false,
	"remesh_target_faces": 0,   # 0 = auto
	"allow_ai_fallback": false,

	# TetWild
	"tetwild_epsilon": 0.0,     # 0 = auto
	"tetwild_stop_energy": 0.0,

	# snappyHexMesh
	"snappy_castellated_min": 1,
	"snappy_castellated_max": 2,
	"snappy_snap_tolerance": 2.0,
	"snappy_snap_iterations": 5,

	# Output
	"max_iterations": 3,
	"export_vtk": false,
	"parallel": 0,              # 0 = no parallel
}

# UI node references (populated in _ready)
var _controls: Dictionary = {}

# -----------------------------------------------------------------------
# Lifecycle
# -----------------------------------------------------------------------
func _ready() -> void:
	_build_ui()
	_apply_style()


func _apply_style() -> void:
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.12, 0.12, 0.15, 1.0)
	style.content_margin_left = 8
	style.content_margin_right = 8
	style.content_margin_top = 4
	style.content_margin_bottom = 4
	add_theme_stylebox_override("panel", style)


# -----------------------------------------------------------------------
# Dynamic UI construction
# -----------------------------------------------------------------------
func _build_ui() -> void:
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_child(scroll)

	var vbox := VBoxContainer.new()
	vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(vbox)

	# === Quality / Tier ===
	_add_section(vbox, "품질 / 엔진")
	_add_option(vbox, "quality", "품질 레벨", ["draft", "standard", "fine"], 1)
	_add_option(vbox, "tier", "볼륨 엔진", ["auto", "tetwild", "netgen", "snappy", "cfmesh"], 0)
	_add_option(vbox, "repair_engine", "수리 엔진", ["auto", "pymeshfix", "trimesh", "none"], 0)
	_add_option(vbox, "remesh_engine", "리메쉬 엔진", ["auto", "vorpalite", "pyacvd", "pymeshlab", "none"], 0)
	_add_option(vbox, "checker_engine", "검증 엔진", ["auto", "openfoam", "native"], 0)
	_add_option(vbox, "postprocess_engine", "후처리 엔진", ["auto", "mmg", "none"], 0)

	# === Cell Size ===
	_add_section(vbox, "셀 크기")
	_add_float(vbox, "element_size", "표면 셀 크기 [m]", 0.0, 10.0, 0.001, "0 = 자동")
	_add_float(vbox, "base_cell_size", "배경 셀 크기 [m]", 0.0, 10.0, 0.01, "0 = 자동")
	_add_float(vbox, "min_cell_size", "최소 셀 크기 [m]", 0.0, 1.0, 0.0001, "0 = 자동")
	_add_int(vbox, "base_cell_num", "특성길이 분할 수", 5, 500, "작을수록 거친 메쉬")

	# === Domain ===
	_add_section(vbox, "도메인")
	_add_float(vbox, "domain_upstream", "업스트림 배수", 0.0, 50.0, 0.5, "0 = 자동")
	_add_float(vbox, "domain_downstream", "다운스트림 배수", 0.0, 100.0, 1.0, "0 = 자동")
	_add_float(vbox, "domain_lateral", "측면 배수", 0.0, 50.0, 0.5, "0 = 자동")
	_add_float(vbox, "domain_scale", "도메인 스케일", 0.1, 10.0, 0.1, "전체 크기 배율")

	# === Memory ===
	_add_section(vbox, "메모리 제한")
	_add_int(vbox, "max_cells", "최대 셀 수", 0, 1000000000, "0 = 제한 없음")

	# === Boundary Layer ===
	_add_section(vbox, "Boundary Layer")
	_add_int(vbox, "bl_layers", "BL 레이어 수", 0, 20, "0 = 자동 (fine만 활성)")
	_add_float(vbox, "bl_first_height", "첫 레이어 높이 [m]", 0.0, 0.1, 0.0001, "0 = 자동")
	_add_float(vbox, "bl_growth_ratio", "성장비", 1.0, 3.0, 0.05, "")

	# === Preprocessor ===
	_add_section(vbox, "전처리")
	_add_check(vbox, "no_repair", "수리 건너뛰기")
	_add_check(vbox, "force_remesh", "리메쉬 강제 실행")
	_add_int(vbox, "remesh_target_faces", "리메쉬 목표 삼각형 수", 0, 1000000, "0 = 자동")
	_add_check(vbox, "allow_ai_fallback", "AI 표면 재생성 허용 (GPU)")

	# === TetWild ===
	_add_section(vbox, "TetWild 파라미터")
	_add_float(vbox, "tetwild_epsilon", "Epsilon", 0.0, 0.1, 0.001, "0 = 자동 (draft=0.02)")
	_add_float(vbox, "tetwild_stop_energy", "Stop Energy", 0.0, 100.0, 1.0, "0 = 자동 (draft=20)")

	# === snappyHexMesh ===
	_add_section(vbox, "snappyHexMesh 파라미터")
	_add_int(vbox, "snappy_castellated_min", "Castellated Min Level", 0, 10, "")
	_add_int(vbox, "snappy_castellated_max", "Castellated Max Level", 0, 10, "")
	_add_float(vbox, "snappy_snap_tolerance", "Snap Tolerance", 0.1, 10.0, 0.1, "")
	_add_int(vbox, "snappy_snap_iterations", "Snap Iterations", 1, 100, "")

	# === Output ===
	_add_section(vbox, "출력")
	_add_int(vbox, "max_iterations", "최대 재시도 횟수", 1, 10, "")
	_add_check(vbox, "export_vtk", "VTK 내보내기")
	_add_int(vbox, "parallel", "MPI 병렬 프로세서 수", 0, 128, "0 = 비활성")


# -----------------------------------------------------------------------
# UI helpers
# -----------------------------------------------------------------------
func _add_section(parent: VBoxContainer, title: String) -> void:
	var sep := HSeparator.new()
	parent.add_child(sep)
	var label := Label.new()
	label.text = title
	label.add_theme_font_size_override("font_size", 14)
	label.add_theme_color_override("font_color", Color(0.5, 0.8, 1.0))
	parent.add_child(label)


func _add_option(parent: VBoxContainer, key: String, label_text: String, options: Array, default_idx: int) -> void:
	var hbox := HBoxContainer.new()
	parent.add_child(hbox)
	var label := Label.new()
	label.text = label_text
	label.custom_minimum_size.x = 160
	hbox.add_child(label)
	var opt := OptionButton.new()
	opt.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for i in range(options.size()):
		opt.add_item(options[i])
	opt.selected = default_idx
	opt.item_selected.connect(func(idx: int) -> void:
		_params[key] = opt.get_item_text(idx)
		params_changed.emit(_params)
	)
	hbox.add_child(opt)
	_controls[key] = opt


func _add_float(parent: VBoxContainer, key: String, label_text: String, min_val: float, max_val: float, step: float, hint: String) -> void:
	var hbox := HBoxContainer.new()
	parent.add_child(hbox)
	var label := Label.new()
	label.text = label_text
	label.custom_minimum_size.x = 160
	if not hint.is_empty():
		label.tooltip_text = hint
	hbox.add_child(label)
	var spin := SpinBox.new()
	spin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	spin.min_value = min_val
	spin.max_value = max_val
	spin.step = step
	spin.value = _params[key]
	spin.value_changed.connect(func(val: float) -> void:
		_params[key] = val
		params_changed.emit(_params)
	)
	hbox.add_child(spin)
	_controls[key] = spin


func _add_int(parent: VBoxContainer, key: String, label_text: String, min_val: int, max_val: int, hint: String) -> void:
	var hbox := HBoxContainer.new()
	parent.add_child(hbox)
	var label := Label.new()
	label.text = label_text
	label.custom_minimum_size.x = 160
	if not hint.is_empty():
		label.tooltip_text = hint
	hbox.add_child(label)
	var spin := SpinBox.new()
	spin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	spin.min_value = min_val
	spin.max_value = max_val
	spin.step = 1
	spin.value = _params[key]
	spin.rounded = true
	spin.value_changed.connect(func(val: float) -> void:
		_params[key] = int(val)
		params_changed.emit(_params)
	)
	hbox.add_child(spin)
	_controls[key] = spin


func _add_check(parent: VBoxContainer, key: String, label_text: String) -> void:
	var check := CheckBox.new()
	check.text = label_text
	check.button_pressed = _params[key]
	check.toggled.connect(func(pressed: bool) -> void:
		_params[key] = pressed
		params_changed.emit(_params)
	)
	parent.add_child(check)
	_controls[key] = check


# -----------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------
func get_params() -> Dictionary:
	return _params.duplicate()


func get_ws_start_payload() -> Dictionary:
	"""WebSocket start 메시지에 포함할 파라미터를 반환한다."""
	var payload := {
		"action": "start",
		"quality": _params["quality"],
		"tier": _params["tier"],
		"max_iterations": _params["max_iterations"],
	}

	# 0이 아닌 값만 포함 (0 = auto)
	if _params["element_size"] > 0:
		payload["element_size"] = _params["element_size"]
	if _params["base_cell_size"] > 0:
		payload["base_cell_size"] = _params["base_cell_size"]
	if _params["max_cells"] > 0:
		payload["max_cells"] = _params["max_cells"]
	if _params["bl_layers"] > 0:
		payload["bl_layers"] = _params["bl_layers"]
	if _params["tetwild_epsilon"] > 0:
		payload["tetwild_epsilon"] = _params["tetwild_epsilon"]

	# Engine selection
	for key in ["repair_engine", "remesh_engine", "volume_engine", "checker_engine", "postprocess_engine"]:
		if _params[key] != "auto":
			payload[key] = _params[key]

	# Bool flags
	if _params["no_repair"]:
		payload["no_repair"] = true
	if _params["force_remesh"]:
		payload["force_remesh"] = true
	if _params["export_vtk"]:
		payload["export_vtk"] = true
	if _params["allow_ai_fallback"]:
		payload["allow_ai_fallback"] = true

	return payload


func set_quality(quality: String) -> void:
	_params["quality"] = quality
	if _controls.has("quality"):
		var opt: OptionButton = _controls["quality"]
		for i in range(opt.item_count):
			if opt.get_item_text(i) == quality:
				opt.selected = i
				break


func reset_to_defaults() -> void:
	"""모든 파라미터를 기본값으로 초기화."""
	_params = {
		"quality": "standard", "tier": "auto",
		"repair_engine": "auto", "remesh_engine": "auto",
		"volume_engine": "auto", "checker_engine": "auto",
		"cad_engine": "auto", "postprocess_engine": "auto",
		"element_size": 0.0, "base_cell_size": 0.0,
		"min_cell_size": 0.0, "base_cell_num": 50,
		"domain_upstream": 0.0, "domain_downstream": 0.0,
		"domain_lateral": 0.0, "domain_scale": 1.0,
		"max_cells": 0,
		"bl_layers": 0, "bl_first_height": 0.0, "bl_growth_ratio": 1.2,
		"no_repair": false, "force_remesh": false,
		"remesh_target_faces": 0, "allow_ai_fallback": false,
		"tetwild_epsilon": 0.0, "tetwild_stop_energy": 0.0,
		"snappy_castellated_min": 1, "snappy_castellated_max": 2,
		"snappy_snap_tolerance": 2.0, "snappy_snap_iterations": 5,
		"max_iterations": 3, "export_vtk": false, "parallel": 0,
	}
	# Update all UI controls
	for key in _controls:
		var ctrl = _controls[key]
		if ctrl is OptionButton:
			for i in range(ctrl.item_count):
				if ctrl.get_item_text(i) == str(_params[key]):
					ctrl.selected = i
					break
		elif ctrl is SpinBox:
			ctrl.value = _params[key]
		elif ctrl is CheckBox:
			ctrl.button_pressed = _params[key]
	params_changed.emit(_params)
