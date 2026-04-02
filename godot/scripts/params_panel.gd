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
	# Theme이 PanelContainer 스타일을 자동 적용하므로 추가 override 불필요.
	# 필요 시 미세 조정만:
	pass


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
	_add_option(vbox, "quality", "품질 레벨", ["draft", "standard", "fine"], 1,
		"draft: TetWild로 빠른 검증 (~1초). 품질 기준이 느슨함 (non-ortho < 85°).\nstandard: Netgen/cfMesh로 엔지니어링 해석용 (~수분). non-ortho < 70°.\nfine: snappyHexMesh + BL로 최종 CFD 제출용 (~30분+). non-ortho < 65°.")
	_add_option(vbox, "tier", "볼륨 엔진", ["auto", "tetwild", "netgen", "snappy", "cfmesh"], 0,
		"auto: 품질 레벨에 따라 자동 선택.\ntetwild: 사면체(tet) 메쉬. 불량 표면에도 강건. Draft 기본.\nnetgen: 사면체 메쉬. CAD(STEP) 직접 지원. Standard 기본.\nsnappy: 육면체 우세(hex-dominant) + BL. 외부 유동 최적.\ncfmesh: 육면체 우세. blockMesh 불필요, 대용량 안전.")
	_add_option(vbox, "repair_engine", "수리 엔진", ["auto", "pymeshfix", "trimesh", "none"], 0,
		"auto: pymeshfix 우선, 실패 시 trimesh.\npymeshfix: non-manifold 엣지, 구멍 자동 수리.\ntrimesh: 중복 면/정점 제거, 법선 통일.\nnone: 수리 건너뜀 (이미 깨끗한 메쉬).")
	_add_option(vbox, "remesh_engine", "리메쉬 엔진", ["auto", "vorpalite", "pyacvd", "pymeshlab", "none"], 0,
		"auto: vorpalite(geogram) 우선, 실패 시 pyACVD.\nvorpalite: 특징선(feature edge) 보존하는 고품질 RVD 리메쉬.\npyacvd: Voronoi 기반 균일 리메쉬 (빠르지만 특징선 손실).\npymeshlab: isotropic remeshing.\nnone: 리메쉬 건너뜀.")
	_add_option(vbox, "checker_engine", "검증 엔진", ["auto", "openfoam", "native"], 0,
		"auto: OpenFOAM checkMesh 우선, 미설치 시 native.\nopenfoam: 정확한 품질 지표 (OpenFOAM 필수).\nnative: Python numpy로 직접 계산 (Windows 호환, OpenFOAM 불필요).")
	_add_option(vbox, "postprocess_engine", "후처리 엔진", ["auto", "mmg", "none"], 0,
		"auto: MMG3D 설치 시 사용 (standard/fine만).\nmmg: 셀 크기 균일화, aspect ratio 개선, 표면 충실도 유지.\nnone: 후처리 건너뜀 (TetWild 결과 그대로).")

	# === Cell Size ===
	_add_section(vbox, "셀 크기")
	_add_float(vbox, "element_size", "표면 셀 크기 [m]", 0.0, 10.0, 0.001,
		"물체 표면에서의 목표 셀 크기.\n0 = 자동 (characteristic_length / 50 × quality 배율).\n작을수록 표면 해상도 높아지지만 셀 수 증가.\n예: 1m 물체에 0.01 → 표면에 ~10,000 셀.")
	_add_float(vbox, "base_cell_size", "배경 셀 크기 [m]", 0.0, 10.0, 0.01,
		"도메인 배경(far-field) 셀 크기.\n0 = 자동 (표면 셀 크기 × 4).\nsnappyHexMesh/cfMesh에서 blockMesh의 기본 격자 크기.\n너무 작으면 메모리 초과 주의.")
	_add_float(vbox, "min_cell_size", "최소 셀 크기 [m]", 0.0, 1.0, 0.0001,
		"리파인먼트(refinement)로 도달할 수 있는 최소 셀 크기.\n0 = 자동 (표면 셀 크기 / 4).\n곡률이 높은 영역에서 더 작은 셀 허용.")
	_add_int(vbox, "base_cell_num", "특성길이 분할 수", 5, 500,
		"특성 길이(L)를 이 수로 나눠 base_cell_size 결정.\nbase_cell = L / base_cell_num × quality_factor.\n기본: 50. 작을수록 거친 메쉬 (빠름).\n10 = 매우 거침, 100 = 촘촘.")

	# === Domain ===
	_add_section(vbox, "도메인")
	_add_float(vbox, "domain_upstream", "업스트림 배수", 0.0, 50.0, 0.5,
		"물체 앞쪽(유입) 도메인 크기 = 배수 × L.\n0 = 자동 (draft=3, standard=5, fine=10).\n외부 유동에서 입구가 물체에 너무 가까우면\n유입 속도가 왜곡됩니다.")
	_add_float(vbox, "domain_downstream", "다운스트림 배수", 0.0, 100.0, 1.0,
		"물체 뒤쪽(유출) 도메인 크기 = 배수 × L.\n0 = 자동 (draft=5, standard=10, fine=20).\n후류(wake) 영역을 충분히 포함해야 합니다.")
	_add_float(vbox, "domain_lateral", "측면 배수", 0.0, 50.0, 0.5,
		"물체 측면(y±, z±) 도메인 크기 = 배수 × L.\n0 = 자동 (draft=2, standard=3, fine=5).\n측면이 너무 좁으면 blockage 효과 발생.")
	_add_float(vbox, "domain_scale", "도메인 스케일", 0.1, 10.0, 0.1,
		"도메인 전체 크기에 곱하는 배율.\n1.0 = 기본. 2.0 = 두 배 큰 도메인.\n0.5 = 절반 크기 (빠른 테스트용).")

	# === Memory ===
	_add_section(vbox, "메모리 제한")
	_add_int(vbox, "max_cells", "최대 셀 수", 0, 1000000000,
		"배경 셀 수가 이 값을 초과하면\nbase_cell_size를 자동으로 확대합니다.\n0 = 제한 없음.\n500,000 = draft 권장.\n5,000,000 = standard 권장.\nPC 메모리: 16GB → ~500만 셀, 64GB → ~2000만 셀.")

	# === Boundary Layer ===
	_add_section(vbox, "Boundary Layer")
	_add_int(vbox, "bl_layers", "BL 레이어 수", 0, 20,
		"벽면에 생성할 프리즘(prism) 레이어 수.\n0 = 자동 (fine만 5개, draft/standard는 비활성).\nCFD에서 벽면 전단응력 정확도에 중요.\n3~5: 기본, 10+: 열전달 해석.")
	_add_float(vbox, "bl_first_height", "첫 레이어 높이 [m]", 0.0, 0.1, 0.0001,
		"벽면에서 첫 번째 프리즘 셀의 높이.\n0 = 자동 (y+ 기반 계산).\ny+ ≈ 1 목표: Re 기반으로 계산됨.\n예: 0.001m = 1mm 첫 레이어.")
	_add_float(vbox, "bl_growth_ratio", "성장비", 1.0, 3.0, 0.05,
		"BL 레이어 간 두께 비율.\n1.2 = 기본 (20%씩 성장).\n1.0 = 균일 두께.\n1.5+ = 빠르게 성장 (레이어 수 줄일 수 있음).")

	# === Preprocessor ===
	_add_section(vbox, "전처리")
	_add_check(vbox, "no_repair", "수리 건너뛰기",
		"표면 수리(L1)를 완전히 건너뜁니다.\n이미 깨끗한 메쉬이거나,\n수리가 형상을 왜곡하는 경우 사용.")
	_add_check(vbox, "force_remesh", "리메쉬 강제 실행",
		"L1 게이트 통과 여부와 관계없이\nL2 리메쉬를 강제 실행합니다.\n삼각형 크기가 불균일한 STL에 유용.")
	_add_int(vbox, "remesh_target_faces", "리메쉬 목표 삼각형 수", 0, 1000000,
		"리메쉬 후 목표 삼각형 수.\n0 = 자동 (표면적과 셀 크기 기반).\n10,000~100,000이 일반적.\n너무 적으면 형상 손실, 너무 많으면 느림.")
	_add_check(vbox, "allow_ai_fallback", "AI 표면 재생성 (GPU)",
		"L2 리메쉬 후에도 watertight 실패 시\nmeshgpt-pytorch로 AI 표면 재생성을 시도합니다.\nGPU(CUDA) 필수. 최후 수단.")

	# === TetWild ===
	_add_section(vbox, "TetWild 파라미터")
	_add_float(vbox, "tetwild_epsilon", "Epsilon", 0.0, 0.1, 0.001,
		"표면 근사 허용 오차 (BBox 대각선 대비 비율).\n0 = 자동 (draft=0.02, standard=0.001).\n클수록 빠르지만 표면 충실도 저하.\n작을수록 정밀하지만 느림.")
	_add_float(vbox, "tetwild_stop_energy", "Stop Energy", 0.0, 100.0, 1.0,
		"최적화 종료 에너지 기준.\n0 = 자동 (draft=20, standard=10).\n작을수록 고품질이지만 시간 증가.\n1~5: 고품질, 20+: 빠른 검증.")

	# === snappyHexMesh ===
	_add_section(vbox, "snappyHexMesh 파라미터")
	_add_int(vbox, "snappy_castellated_min", "Castellated Min Level", 0, 10,
		"표면 근처 최소 리파인먼트 레벨.\n각 레벨은 셀을 8등분.\n레벨 1 = 기본 셀의 1/2 크기.\n레벨 2 = 1/4. 레벨 3 = 1/8.")
	_add_int(vbox, "snappy_castellated_max", "Castellated Max Level", 0, 10,
		"표면 근처 최대 리파인먼트 레벨.\nMin과 Max 사이에서 곡률에 따라 자동 결정.\n예: [1, 3] = 평면은 레벨 1, 곡면은 레벨 3.")
	_add_float(vbox, "snappy_snap_tolerance", "Snap Tolerance", 0.1, 10.0, 0.1,
		"표면 스냅 허용 거리 (셀 크기 대비 비율).\n기본: 2.0. 클수록 더 멀리서도 스냅.\n표면 적합도(snap quality)에 영향.\nnon-ortho가 높으면 이 값을 높여보세요.")
	_add_int(vbox, "snappy_snap_iterations", "Snap Iterations", 1, 100,
		"표면 스냅 최적화 반복 횟수.\n기본: 5. 높을수록 정밀하지만 느림.\nnon-ortho 개선이 필요하면 10~30.")

	# === Output ===
	_add_section(vbox, "출력")
	_add_int(vbox, "max_iterations", "최대 재시도 횟수", 1, 10,
		"메쉬 생성 FAIL 시 파라미터를 자동 조정하고 재시도.\n기본: 3. 1 = 재시도 없음.\n재시도마다: 셀 크기 축소, snap 강화, tier 변경 등.")
	_add_check(vbox, "export_vtk", "VTK 내보내기",
		"완료 후 .vtu 파일을 자동 생성합니다.\nParaView에서 메쉬 품질(non-ortho, cell volume) 시각화 가능.")
	_add_int(vbox, "parallel", "MPI 병렬 프로세서 수", 0, 128,
		"decomposeParDict를 자동 생성합니다.\n0 = 비활성 (시리얼 실행).\n4~8: 일반 워크스테이션.\n16+: 서버/클러스터.")


# -----------------------------------------------------------------------
# UI helpers
# -----------------------------------------------------------------------
func _add_section(parent: VBoxContainer, title: String) -> void:
	var sep := HSeparator.new()
	parent.add_child(sep)
	var label := Label.new()
	label.text = title
	label.add_theme_font_size_override("font_size", 14)
	label.add_theme_color_override("font_color", Color(0.65, 0.78, 0.95))
	parent.add_child(label)


func _make_info_button(tooltip: String) -> Button:
	"""(i) 정보 버튼 생성. hover/click 시 상세 설명 표시."""
	var btn := Button.new()
	btn.text = "ⓘ"
	btn.tooltip_text = tooltip
	btn.custom_minimum_size = Vector2(24, 24)
	btn.flat = true
	btn.add_theme_font_size_override("font_size", 12)
	btn.add_theme_color_override("font_color", Color(0.4, 0.7, 1.0, 0.8))
	btn.add_theme_color_override("font_hover_color", Color(0.5, 0.85, 1.0, 1.0))
	btn.mouse_default_cursor_shape = Control.CURSOR_HELP
	# 클릭 시 팝업 대화상자로 전체 설명 표시
	btn.pressed.connect(func() -> void:
		var dialog := AcceptDialog.new()
		dialog.title = "파라미터 설명"
		dialog.dialog_text = tooltip
		dialog.min_size = Vector2i(400, 200)
		add_child(dialog)
		dialog.popup_centered()
		dialog.confirmed.connect(dialog.queue_free)
		dialog.canceled.connect(dialog.queue_free)
	)
	return btn


func _add_option(parent: VBoxContainer, key: String, label_text: String, options: Array, default_idx: int, info: String = "") -> void:
	var hbox := HBoxContainer.new()
	parent.add_child(hbox)
	if not info.is_empty():
		hbox.add_child(_make_info_button(info))
	var label := Label.new()
	label.text = label_text
	label.custom_minimum_size.x = 140
	label.tooltip_text = info
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


func _add_float(parent: VBoxContainer, key: String, label_text: String, min_val: float, max_val: float, step: float, info: String = "") -> void:
	var hbox := HBoxContainer.new()
	parent.add_child(hbox)
	if not info.is_empty():
		hbox.add_child(_make_info_button(info))
	var label := Label.new()
	label.text = label_text
	label.custom_minimum_size.x = 140
	label.tooltip_text = info
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


func _add_int(parent: VBoxContainer, key: String, label_text: String, min_val: int, max_val: int, info: String = "") -> void:
	var hbox := HBoxContainer.new()
	parent.add_child(hbox)
	if not info.is_empty():
		hbox.add_child(_make_info_button(info))
	var label := Label.new()
	label.text = label_text
	label.custom_minimum_size.x = 140
	label.tooltip_text = info
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


func _add_check(parent: VBoxContainer, key: String, label_text: String, info: String = "") -> void:
	var hbox := HBoxContainer.new()
	parent.add_child(hbox)
	if not info.is_empty():
		hbox.add_child(_make_info_button(info))
	var check := CheckBox.new()
	check.text = label_text
	check.tooltip_text = info
	check.button_pressed = _params[key]
	check.toggled.connect(func(pressed: bool) -> void:
		_params[key] = pressed
		params_changed.emit(_params)
	)
	hbox.add_child(check)
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
