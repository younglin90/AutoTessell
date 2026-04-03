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
signal server_log(level: String, message: String)

# -----------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------
const DEFAULT_HOST := "127.0.0.1"
const DEFAULT_PORT := 9720

## Maximum reconnection attempts before giving up.
const MAX_RECONNECT_ATTEMPTS := 3
## Seconds to wait between reconnection attempts.
const RECONNECT_DELAY_SECONDS := 1.0
## Seconds allowed for mesh generation before a timeout is raised.
const MESH_TIMEOUT_SECONDS := 300.0  # 5분 (Fine tier는 오래 걸림)

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

# Reconnection state
var _reconnect_attempts := 0
var _reconnect_pending_payload: Dictionary = {"action": "start", "quality": "standard", "tier": "auto", "max_iterations": 3}

# Timeout tracking
var _mesh_start_time := 0.0
var _mesh_running := false

# -----------------------------------------------------------------------
# Lifecycle
# -----------------------------------------------------------------------
func _ready() -> void:
	_http_request = HTTPRequest.new()
	add_child(_http_request)
	set_process(false)  # Only process when WS is active


func _process(delta: float) -> void:
	if not _ws_connected:
		return

	# Mesh generation timeout guard
	if _mesh_running:
		_mesh_start_time += delta
		if _mesh_start_time >= MESH_TIMEOUT_SECONDS:
			_mesh_running = false
			error_occurred.emit(
				"Mesh generation timed out after %.0f seconds" % MESH_TIMEOUT_SECONDS
			)
			_disconnect()
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


## 메쉬 생성 시작 (WebSocket). 연결 실패 시 MAX_RECONNECT_ATTEMPTS회까지 재시도한다.
func start_mesh(job_id: String, quality: String = "standard", tier: String = "auto", max_iterations: int = 3) -> void:
	var payload := {"action": "start", "quality": quality, "tier": tier, "max_iterations": max_iterations}
	start_mesh_with_params(job_id, payload)


## 전체 파라미터 payload로 메쉬 생성 시작.
## payload는 params_panel.get_ws_start_payload()에서 생성된 Dictionary.
func start_mesh_with_params(job_id: String, payload: Dictionary) -> void:
	_current_job_id = job_id
	_reconnect_attempts = 0
	_reconnect_pending_payload = payload
	_do_connect_mesh_with_payload(job_id, payload)


## 현재 작업 ID
func get_current_job_id() -> String:
	return _current_job_id


# -----------------------------------------------------------------------
# Internal connection / reconnection
# -----------------------------------------------------------------------

func _do_connect_mesh_with_payload(job_id: String, payload: Dictionary) -> void:
	var url := "%s/ws/mesh/%s" % [ws_url, job_id]
	print("[WS] Connecting to %s (attempt %d/%d)" % [url, _reconnect_attempts + 1, MAX_RECONNECT_ATTEMPTS])
	print("[WS] Params: %s" % JSON.stringify(payload))

	_ws = WebSocketPeer.new()
	var err := _ws.connect_to_url(url)
	if err != OK:
		_on_connect_failed(job_id, payload, "WebSocket 연결 실패: %d" % err)
		return

	_ws_connected = true
	_mesh_running = false
	_mesh_start_time = 0.0
	set_process(true)

	await get_tree().create_timer(0.5).timeout

	_ws.poll()
	if _ws.get_ready_state() != WebSocketPeer.STATE_OPEN:
		_on_connect_failed(job_id, payload, "WebSocket 연결 끊김 (handshake 실패)")
		return

	# 전체 payload 전송 (quality, tier, max_iterations + 모든 파라미터)
	payload["action"] = "start"
	var cmd := JSON.stringify(payload)
	_ws.send_text(cmd)

	_mesh_running = true
	_mesh_start_time = 0.0
	connected.emit()


func _on_connect_failed(job_id: String, payload: Dictionary, reason: String) -> void:
	_reconnect_attempts += 1
	if _reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
		print("[WS] %s — retrying in %.0fs (%d/%d)" % [
			reason, RECONNECT_DELAY_SECONDS, _reconnect_attempts + 1, MAX_RECONNECT_ATTEMPTS
		])
		await get_tree().create_timer(RECONNECT_DELAY_SECONDS).timeout
		_do_connect_mesh_with_payload(job_id, payload)
	else:
		error_occurred.emit("%s (최대 재시도 횟수 초과)" % reason)


func _disconnect() -> void:
	if _ws_connected:
		_ws.close()
		_ws_connected = false
		_mesh_running = false
		set_process(false)


## 외부에서 호출 가능한 강제 연결 해제
func disconnect_ws() -> void:
	print("[WS] Force disconnect requested")
	_disconnect()
	disconnected.emit()


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
			_mesh_running = false
			mesh_completed.emit(success, json)

		"error":
			var msg: String = json.get("message", "Unknown error")
			_mesh_running = false
			error_occurred.emit(msg)

		"log":
			var level: String = json.get("level", "info")
			var msg: String = json.get("message", "")
			server_log.emit(level, msg)

		_:
			print("[WS] Unknown message type: %s" % msg_type)
