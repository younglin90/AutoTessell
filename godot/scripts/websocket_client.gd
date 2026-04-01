## Auto-Tessell WebSocket 클라이언트 (Autoload 싱글톤)
##
## Python 백엔드(desktop/server.py)와 WebSocket으로 통신한다.
## 파일 업로드 → 메쉬 생성 시작 → 진행상황 수신 → 결과 처리.
extends Node

# -----------------------------------------------------------------------
# Signals
# -----------------------------------------------------------------------
signal connected
signal disconnected
signal progress_updated(stage: String, progress: float, message: String)
signal strategy_received(tier: String, quality: String, cell_size: float)
signal evaluation_received(iteration: int, verdict: String, cells: int, non_ortho: float)
signal mesh_completed(success: bool, data: Dictionary)
signal error_occurred(message: String)
signal upload_completed(job_id: String)

# -----------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------
const DEFAULT_HOST := "127.0.0.1"
const DEFAULT_PORT := 9720

var base_url: String:
	get: return "http://%s:%d" % [host, port]

var ws_url: String:
	get: return "ws://%s:%d" % [host, port]

var host := DEFAULT_HOST
var port := DEFAULT_PORT

# -----------------------------------------------------------------------
# State
# -----------------------------------------------------------------------
var _ws := WebSocketPeer.new()
var _ws_connected := false
var _current_job_id := ""
var _http_request: HTTPRequest

# -----------------------------------------------------------------------
# Lifecycle
# -----------------------------------------------------------------------
func _ready() -> void:
	_http_request = HTTPRequest.new()
	add_child(_http_request)
	set_process(false)  # Only process when WS is active


func _process(_delta: float) -> void:
	if not _ws_connected:
		return

	_ws.poll()
	var state := _ws.get_ready_state()

	match state:
		WebSocketPeer.STATE_OPEN:
			while _ws.get_available_packet_count() > 0:
				var packet := _ws.get_packet()
				var text := packet.get_string_from_utf8()
				_handle_message(text)
		WebSocketPeer.STATE_CLOSING:
			pass
		WebSocketPeer.STATE_CLOSED:
			_ws_connected = false
			set_process(false)
			disconnected.emit()
			print("[WS] Disconnected: code=%d reason=%s" % [_ws.get_close_code(), _ws.get_close_reason()])

# -----------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------

## 서버 헬스 체크
func check_health(callback: Callable) -> void:
	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(func(_result: int, _code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
		var json: Variant = JSON.parse_string(body.get_string_from_utf8())
		callback.call(json)
		http.queue_free()
	)
	http.request(base_url + "/health")


## 파일 업로드
func upload_file(file_path: String) -> void:
	# Multipart form data로 파일 업로드
	var file := FileAccess.open(file_path, FileAccess.READ)
	if not file:
		error_occurred.emit("파일을 열 수 없습니다: " + file_path)
		return

	var file_data := file.get_buffer(file.get_length())
	var file_name := file_path.get_file()
	file.close()

	var boundary := "----AutoTessellBoundary"
	var body := PackedByteArray()

	# Multipart form body 구성
	var header_text := "--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\nContent-Type: application/octet-stream\r\n\r\n" % [boundary, file_name]
	body.append_array(header_text.to_utf8_buffer())
	body.append_array(file_data)
	body.append_array(("\r\n--%s--\r\n" % boundary).to_utf8_buffer())

	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(func(_result: int, code: int, _headers: PackedStringArray, resp_body: PackedByteArray) -> void:
		if code == 200:
			var json: Variant = JSON.parse_string(resp_body.get_string_from_utf8())
			if json is Dictionary and (json as Dictionary).has("job_id"):
				var d: Dictionary = json as Dictionary
				_current_job_id = str(d["job_id"])
				upload_completed.emit(_current_job_id)
			else:
				error_occurred.emit("업로드 응답 파싱 실패")
		else:
			error_occurred.emit("업로드 실패: HTTP %d" % code)
		http.queue_free()
	)
	http.request_raw(
		base_url + "/upload",
		["Content-Type: multipart/form-data; boundary=" + boundary],
		HTTPClient.METHOD_POST,
		body,
	)


## 메쉬 생성 시작 (WebSocket)
func start_mesh(job_id: String, quality: String = "standard", tier: String = "auto", max_iterations: int = 3) -> void:
	_current_job_id = job_id
	var url := "%s/ws/mesh/%s" % [ws_url, job_id]
	print("[WS] Connecting to %s" % url)

	var err := _ws.connect_to_url(url)
	if err != OK:
		error_occurred.emit("WebSocket 연결 실패: %d" % err)
		return

	_ws_connected = true
	set_process(true)

	# 연결 완료 후 start 명령 전송 (약간의 지연)
	await get_tree().create_timer(0.5).timeout
	var cmd := JSON.stringify({
		"action": "start",
		"quality": quality,
		"tier": tier,
		"max_iterations": max_iterations,
	})
	_ws.send_text(cmd)
	connected.emit()


## 현재 작업 ID
func get_current_job_id() -> String:
	return _current_job_id

# -----------------------------------------------------------------------
# Message handling
# -----------------------------------------------------------------------
func _handle_message(text: String) -> void:
	var json: Variant = JSON.parse_string(text)
	if not json:
		print("[WS] Invalid JSON: %s" % text)
		return

	var msg_type: String = json.get("type", "")

	match msg_type:
		"progress":
			var stage: String = json.get("stage", "")
			var prog: float = json.get("progress", 0.0)
			var msg: String = json.get("message", "")
			progress_updated.emit(stage, prog, msg)

		"strategy":
			var tier: String = json.get("selected_tier", "")
			var ql: String = json.get("quality_level", "")
			var cs: float = json.get("cell_size", 0.0)
			strategy_received.emit(tier, ql, cs)

		"evaluation":
			var iter: int = json.get("iteration", 0)
			var verdict: String = json.get("verdict", "")
			var cells: int = json.get("cells", 0)
			var no: float = json.get("max_non_ortho", 0.0)
			evaluation_received.emit(iter, verdict, cells, no)

		"result":
			var success: bool = json.get("success", false)
			mesh_completed.emit(success, json)

		"error":
			var msg: String = json.get("message", "Unknown error")
			error_occurred.emit(msg)

		_:
			print("[WS] Unknown message type: %s" % msg_type)
