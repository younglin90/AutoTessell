## 메인 UI 컨트롤러
## 파일 선택 → 업로드 → 메쉬 생성 → 결과 표시 플로우를 관리한다.
extends Control

# -----------------------------------------------------------------------
# Node references
# -----------------------------------------------------------------------
@onready var file_button: Button = %FileButton if has_node("%FileButton") else $VBoxContainer/HSplitContainer/Sidebar/SidebarContent/FileSection/FileButton
@onready var file_info: RichTextLabel = $VBoxContainer/HSplitContainer/Sidebar/SidebarContent/FileSection/FileInfo
@onready var quality_options: OptionButton = $VBoxContainer/HSplitContainer/Sidebar/SidebarContent/QualitySection/QualityOptions
@onready var generate_button: Button = $VBoxContainer/HSplitContainer/Sidebar/SidebarContent/ActionSection/GenerateButton
@onready var progress_bar: ProgressBar = $VBoxContainer/HSplitContainer/Sidebar/SidebarContent/ActionSection/ProgressBar
@onready var progress_label: Label = $VBoxContainer/HSplitContainer/Sidebar/SidebarContent/ActionSection/ProgressLabel
@onready var result_info: RichTextLabel = $VBoxContainer/HSplitContainer/Sidebar/SidebarContent/ResultSection/ResultInfo
@onready var status_label: Label = $VBoxContainer/StatusBar/HBoxContainer/StatusLabel
@onready var server_status: Label = $VBoxContainer/StatusBar/HBoxContainer/ServerStatus
@onready var file_dialog: FileDialog = $FileDialog

var _selected_file_path: String = ""
var _quality_map := ["draft", "standard", "fine"]

# -----------------------------------------------------------------------
# Lifecycle
# -----------------------------------------------------------------------
func _ready() -> void:
	# 시그널 연결
	file_button.pressed.connect(_on_file_button_pressed)
	file_dialog.file_selected.connect(_on_file_selected)
	generate_button.pressed.connect(_on_generate_pressed)
	quality_options.item_selected.connect(_on_quality_selected)

	# WebSocket 시그널
	WebSocketClient.upload_completed.connect(_on_upload_completed)
	WebSocketClient.progress_updated.connect(_on_progress_updated)
	WebSocketClient.strategy_received.connect(_on_strategy_received)
	WebSocketClient.evaluation_received.connect(_on_evaluation_received)
	WebSocketClient.mesh_completed.connect(_on_mesh_completed)
	WebSocketClient.error_occurred.connect(_on_error)

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
# File selection
# -----------------------------------------------------------------------
func _on_file_button_pressed() -> void:
	file_dialog.popup_centered()


func _on_file_selected(path: String) -> void:
	_selected_file_path = path
	var file_name := path.get_file()
	var file_ext := path.get_extension().to_upper()

	file_info.text = "[b]%s[/b]\n[color=gray]%s | %s[/color]" % [
		file_name,
		file_ext,
		_format_size(FileAccess.get_file_as_bytes(path).size()),
	]

	generate_button.disabled = false
	status_label.text = "파일 선택됨: %s" % file_name
	AppState.add_recent_file(path)


# -----------------------------------------------------------------------
# Quality selection
# -----------------------------------------------------------------------
func _on_quality_selected(index: int) -> void:
	AppState.quality_level = _quality_map[index]
	status_label.text = "품질: %s" % AppState.quality_level


# -----------------------------------------------------------------------
# Mesh generation
# -----------------------------------------------------------------------
func _on_generate_pressed() -> void:
	if _selected_file_path.is_empty():
		return

	# UI 상태 전환
	generate_button.disabled = true
	progress_bar.visible = true
	progress_bar.value = 0
	progress_label.text = "업로드 중..."
	result_info.text = "[color=gray]처리 중...[/color]"
	AppState.current_state = AppState.State.UPLOADING

	# 파일 업로드
	WebSocketClient.upload_file(_selected_file_path)


func _on_upload_completed(job_id: String) -> void:
	AppState.current_job_id = job_id
	AppState.current_state = AppState.State.MESHING
	progress_label.text = "메쉬 생성 시작..."

	# WebSocket으로 메쉬 생성 시작
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


func _on_strategy_received(tier: String, quality: String, cell_size: float) -> void:
	status_label.text = "전략: %s (cell_size=%.4f)" % [tier, cell_size]


func _on_evaluation_received(iteration: int, verdict: String, cells: int, non_ortho: float) -> void:
	status_label.text = "평가 #%d: %s (cells=%d, non-ortho=%.1f°)" % [iteration, verdict, cells, non_ortho]


func _on_mesh_completed(success: bool, data: Dictionary) -> void:
	progress_bar.value = 100
	generate_button.disabled = false
	AppState.last_result = data

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

		# 3D 뷰어에 메쉬 로드 요청
		# TODO: MeshViewer.load_from_server(AppState.current_job_id)

	else:
		AppState.current_state = AppState.State.FAILED
		var msg: String = data.get("message", "알 수 없는 오류")
		result_info.text = "[b][color=red]FAIL[/color][/b]\n\n%s" % msg
		progress_label.text = "실패"
		status_label.text = "메쉬 생성 실패"


func _on_error(message: String) -> void:
	result_info.text = "[b][color=red]오류[/color][/b]\n\n%s" % message
	progress_label.text = "오류 발생"
	generate_button.disabled = false
	progress_bar.visible = false
	AppState.current_state = AppState.State.FAILED


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
