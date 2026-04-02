## 메인 UI 컨트롤러
## 파일 선택 → 업로드 → 메쉬 생성 → 결과 표시 플로우를 관리한다.
##
## 추가 기능:
##   - 3D 뷰포트 영역에 파일 드래그 앤 드롭 지원
##   - Ctrl+O 단축키로 파일 열기
##   - 메쉬 완료 후 서버에서 STL 자동 요청 → MeshViewer에 로드
extends Control

# -----------------------------------------------------------------------
# Node references (paths match main.tscn)
# -----------------------------------------------------------------------
const _SB := "VBoxContainer/HSplitContainer/Sidebar/SidebarScroll/SidebarContent"

@onready var file_button: Button = get_node(_SB + "/FileSection/FileButton")
@onready var file_info: RichTextLabel = get_node(_SB + "/FileSection/FileInfo")
@onready var params_panel: PanelContainer = get_node(_SB + "/ParamsPanel")
@onready var generate_button: Button = get_node(_SB + "/ActionSection/ButtonRow/GenerateButton")
@onready var stop_button: Button = get_node(_SB + "/ActionSection/ButtonRow/StopButton")
@onready var progress_bar: ProgressBar = get_node(_SB + "/ActionSection/ProgressBar")
@onready var progress_label: Label = get_node(_SB + "/ActionSection/ProgressLabel")
@onready var result_info: RichTextLabel = get_node(_SB + "/ResultSection/ResultInfo")
@onready var status_label: Label = $VBoxContainer/StatusBar/HBoxContainer/StatusLabel
@onready var server_status: Label = $VBoxContainer/StatusBar/HBoxContainer/ServerStatus
@onready var file_dialog: FileDialog = $FileDialog
@onready var viewport_area: Control = $VBoxContainer/HSplitContainer/RightPanel/ViewerContainer if has_node("VBoxContainer/HSplitContainer/RightPanel/ViewerContainer") else null
@onready var mesh_viewer = $VBoxContainer/HSplitContainer/RightPanel/ViewerContainer/SubViewport/MeshViewer if has_node("VBoxContainer/HSplitContainer/RightPanel/ViewerContainer/SubViewport/MeshViewer") else null
@onready var console_log: RichTextLabel = $VBoxContainer/HSplitContainer/RightPanel/ConsolePanel/ConsoleVBox/ConsoleLog if has_node("VBoxContainer/HSplitContainer/RightPanel/ConsolePanel/ConsoleVBox/ConsoleLog") else null
@onready var clear_button: Button = $VBoxContainer/HSplitContainer/RightPanel/ConsolePanel/ConsoleVBox/ConsoleHeader/ClearButton if has_node("VBoxContainer/HSplitContainer/RightPanel/ConsolePanel/ConsoleVBox/ConsoleHeader/ClearButton") else null

var _selected_file_path: String = ""

# -----------------------------------------------------------------------
# Lifecycle
# -----------------------------------------------------------------------
func _ready() -> void:
	# 토큰 기반 테마 적용
	theme = AppTheme.create("dark")

	# 시그널 연결
	file_button.pressed.connect(_on_file_button_pressed)
	file_dialog.file_selected.connect(_on_file_selected)
	generate_button.pressed.connect(_on_generate_pressed)
	stop_button.pressed.connect(_on_stop_pressed)
	if clear_button:
		clear_button.pressed.connect(func() -> void:
			if console_log: console_log.text = "[color=gray]Console cleared[/color]\n"
		)

	# WebSocket 시그널
	WebSocketClient.upload_completed.connect(_on_upload_completed)
	WebSocketClient.progress_updated.connect(_on_progress_updated)
	WebSocketClient.strategy_received.connect(_on_strategy_received)
	WebSocketClient.evaluation_received.connect(_on_evaluation_received)
	WebSocketClient.mesh_completed.connect(_on_mesh_completed)
	WebSocketClient.error_occurred.connect(_on_error)

	# 드래그 앤 드롭 지원 활성화
	if viewport_area != null:
		viewport_area.mouse_filter = Control.MOUSE_FILTER_STOP

	# 백엔드 자동 시작 시그널
	BackendLauncher.backend_started.connect(func() -> void:
		server_status.text = "서버: 시작됨"
		server_status.add_theme_color_override("font_color", Color.GREEN)
		_log("백엔드 서버 시작됨", "success")
		_check_server()
	)
	BackendLauncher.backend_failed.connect(func(reason: String) -> void:
		server_status.text = "서버: 시작 실패"
		server_status.add_theme_color_override("font_color", Color.RED)
		status_label.text = reason
		_log("백엔드 서버 시작 실패: %s" % reason, "error")
	)

	# 서버 헬스 체크
	_check_server()


func _check_server() -> void:
	server_status.text = "서버: 연결 확인 중..."
	WebSocketClient.check_health(func(result):
		if result and result.get("status") == "ok":
			server_status.text = "서버: 연결됨 (v%s)" % result.get("version", "?")
			server_status.add_theme_color_override("font_color", Color.GREEN)
		else:
			server_status.text = "서버: 연결 실패"
			server_status.add_theme_color_override("font_color", Color.RED)
	)


# -----------------------------------------------------------------------
# Keyboard shortcuts
# -----------------------------------------------------------------------
func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey:
		var ke := event as InputEventKey
		if ke.pressed and not ke.echo:
			# Ctrl+O — open file dialog
			if ke.keycode == KEY_O and ke.ctrl_pressed:
				get_viewport().set_input_as_handled()
				file_dialog.popup_centered()


# -----------------------------------------------------------------------
# Drag and drop (viewport area)
# -----------------------------------------------------------------------

## Called by the viewport Control node's _can_drop_data virtual.
func _viewport_can_drop_data(_at_position: Vector2, data: Variant) -> bool:
	if data is Dictionary:
		var d: Dictionary = data as Dictionary
		if d.get("type") == "files":
			var files: Array = d.get("files", [])
			for f in files:
				var ext: String = str(f).get_extension().to_lower()
				if ext in ["stl", "obj", "ply", "off", "step", "iges", "msh"]:
					return true
	return false


## Called by the viewport Control node's _drop_data virtual.
func _viewport_drop_data(_at_position: Vector2, data: Variant) -> void:
	if data is Dictionary:
		var d: Dictionary = data as Dictionary
		if d.get("type") == "files":
			var files: Array = d.get("files", [])
			if files.size() > 0:
				_on_file_selected(str(files[0]))


# -----------------------------------------------------------------------
# File selection
# -----------------------------------------------------------------------
func _on_file_button_pressed() -> void:
	file_dialog.popup_centered()


func _on_file_selected(path: String) -> void:
	_selected_file_path = path
	var file_name := path.get_file()
	_log("파일 선택: %s" % file_name)
	var file_ext := path.get_extension().to_upper()

	file_info.text = "[b]%s[/b]\n[color=gray]%s | %s[/color]" % [
		file_name,
		file_ext,
		_format_size(FileAccess.get_file_as_bytes(path).size()),
	]

	generate_button.disabled = false
	status_label.text = "파일 선택됨: %s" % file_name
	AppState.add_recent_file(path)

	# 파일 선택 즉시 3D 뷰어에 표면 메쉬 로드
	if mesh_viewer and mesh_viewer.has_method("load_stl"):
		var ext := path.get_extension().to_lower()
		if ext in ["stl", "obj", "ply"]:
			mesh_viewer.load_stl(path)
			status_label.text = "파일 로드됨: %s (%s)" % [file_name, ext.to_upper()]


# -----------------------------------------------------------------------
# Mesh generation
# -----------------------------------------------------------------------
func _on_generate_pressed() -> void:
	if _selected_file_path.is_empty():
		return

	# UI 상태 전환
	generate_button.disabled = true
	stop_button.visible = true
	progress_bar.visible = true
	progress_bar.value = 0
	progress_label.text = "업로드 중..."
	result_info.text = "[color=gray]처리 중...[/color]"
	AppState.current_state = AppState.State.UPLOADING

	# 파일 업로드
	_log("업로드 시작: %s" % _selected_file_path.get_file())
	WebSocketClient.upload_file(_selected_file_path)


func _on_stop_pressed() -> void:
	"""메쉬 생성 강제 중지."""
	_log("사용자가 메쉬 생성을 중지했습니다", "warn")
	WebSocketClient.disconnect_ws()
	_reset_ui_after_stop()
	status_label.text = "사용자에 의해 중지됨"
	result_info.text = "[color=yellow]메쉬 생성이 중지되었습니다.[/color]"


func _reset_ui_after_stop() -> void:
	generate_button.disabled = false
	stop_button.visible = false
	progress_bar.visible = false
	progress_bar.value = 0
	progress_label.text = ""
	AppState.current_state = AppState.State.IDLE


func _on_upload_completed(job_id: String) -> void:
	AppState.current_job_id = job_id
	AppState.current_state = AppState.State.MESHING
	progress_label.text = "메쉬 생성 시작..."
	_log("업로드 완료. Job ID: %s" % job_id, "success")

	# ParamsPanel에서 모든 파라미터를 가져와 WebSocket으로 전달
	if params_panel and params_panel.has_method("get_ws_start_payload"):
		var payload: Dictionary = params_panel.get_ws_start_payload()
		# start_mesh에 전체 payload 전달
		WebSocketClient.start_mesh_with_params(job_id, payload)
	else:
		# fallback: 기본 파라미터
		WebSocketClient.start_mesh(
			job_id,
			AppState.quality_level,
			AppState.tier_hint,
			AppState.max_iterations,
		)


# -----------------------------------------------------------------------
# Progress callbacks
# -----------------------------------------------------------------------
func _on_progress_updated(stage: String, progress: float, message: String) -> void:
	progress_bar.value = progress * 100
	progress_label.text = message
	status_label.text = "[%s] %s" % [stage, message]
	_log("[%.0f%%] %s: %s" % [progress * 100, stage, message])


func _on_strategy_received(tier: String, quality: String, cell_size: float) -> void:
	status_label.text = "전략: %s (cell_size=%.4f)" % [tier, cell_size]
	_log("전략 수립: tier=%s, quality=%s, cell_size=%.4f" % [tier, quality, cell_size], "info")


func _on_evaluation_received(iteration: int, verdict: String, cells: int, non_ortho: float) -> void:
	status_label.text = "평가 #%d: %s (cells=%d, non-ortho=%.1f°)" % [iteration, verdict, cells, non_ortho]
	var level := "success" if "PASS" in verdict else "error"
	_log("평가 #%d: %s | cells=%d | non-ortho=%.1f°" % [iteration, verdict, cells, non_ortho], level)


func _on_mesh_completed(success: bool, data: Dictionary) -> void:
	progress_bar.value = 100
	generate_button.disabled = false
	stop_button.visible = false
	AppState.last_result = data
	if success:
		_log("메쉬 생성 완료: %s | %d cells" % [data.get("verdict", ""), data.get("cells", 0)], "success")
	else:
		_log("메쉬 생성 실패: %s" % data.get("message", "unknown"), "error")

	if success:
		AppState.current_state = AppState.State.COMPLETED
		var verdict: String = data.get("verdict", "")
		var cells: int = data.get("cells", 0)
		var tier: String = data.get("tier", "")
		var non_ortho: float = data.get("max_non_ortho", 0.0)
		var skewness: float = data.get("max_skewness", 0.0)

		result_info.text = (
			"[b][color=green]PASS[/color][/b]\n\n"
			+ "[b]Tier:[/b] %s\n" % tier
			+ "[b]Cells:[/b] %s\n" % _format_number(cells)
			+ "[b]Non-ortho:[/b] %.1f°\n" % non_ortho
			+ "[b]Skewness:[/b] %.3f\n" % skewness
		)
		progress_label.text = "완료!"
		status_label.text = "메쉬 생성 완료: %s" % verdict

		# 3D 뷰어에 서버 STL 자동 로드
		_load_mesh_into_viewer(AppState.current_job_id)

	else:
		AppState.current_state = AppState.State.FAILED
		var msg: String = data.get("message", "알 수 없는 오류")
		result_info.text = "[b][color=red]FAIL[/color][/b]\n\n%s" % msg
		progress_label.text = "실패"
		status_label.text = "메쉬 생성 실패"


func _on_error(message: String) -> void:
	result_info.text = "[b][color=red]오류[/color][/b]\n\n%s" % message
	progress_label.text = "오류 발생"
	_log("오류: %s" % message, "error")
	generate_button.disabled = false
	stop_button.visible = false
	progress_bar.visible = false
	AppState.current_state = AppState.State.FAILED


# -----------------------------------------------------------------------
# MeshViewer integration
# -----------------------------------------------------------------------

## Fetch the preprocessed STL from the server and load it into MeshViewer.
func _load_mesh_into_viewer(job_id: String) -> void:
	if mesh_viewer == null:
		return

	# Download the surface STL to a local temp file then hand to mesh_viewer
	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(
		func(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
			http.queue_free()
			if code != 200:
				status_label.text = "뷰어 로드 실패: HTTP %d" % code
				return

			# Write to a temp file so load_stl can read it
			var tmp_path := "user://autotessell_surface_%s.stl" % job_id
			var f := FileAccess.open(tmp_path, FileAccess.WRITE)
			if f == null:
				status_label.text = "임시 파일 쓰기 실패"
				return
			f.store_buffer(body)
			f.close()

			mesh_viewer.load_stl(tmp_path)
			status_label.text = "3D 뷰어에 메쉬 로드 완료"
	)
	http.request(WebSocketClient.base_url + "/jobs/%s/surface" % job_id)


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------
func _format_size(bytes: int) -> String:
	if bytes < 1024:
		return "%d B" % bytes
	elif bytes < 1024 * 1024:
		return "%.1f KB" % (bytes / 1024.0)
	else:
		return "%.1f MB" % (bytes / (1024.0 * 1024.0))


func _format_number(n: int) -> String:
	var s := str(n)
	var result := ""
	for i in range(s.length()):
		if i > 0 and (s.length() - i) % 3 == 0:
			result += ","
		result += s[i]
	return result


# -----------------------------------------------------------------------
# Console logging
# -----------------------------------------------------------------------
func _log(message: String, level: String = "info") -> void:
	"""콘솔 패널에 로그 메시지 추가."""
	if console_log == null:
		return
	var color := "white"
	var prefix := ""
	match level:
		"info":    color = "#b0b8c8"; prefix = "INFO"
		"success": color = "#4ade80"; prefix = " OK "
		"warn":    color = "#fbbf24"; prefix = "WARN"
		"error":   color = "#f87171"; prefix = "ERR "
		"debug":   color = "#8888a0"; prefix = "DBG "
	var timestamp := Time.get_time_string_from_system()
	console_log.append_text(
		"[color=#555568]%s[/color] [color=%s][%s][/color] %s\n" % [timestamp, color, prefix, message]
	)
