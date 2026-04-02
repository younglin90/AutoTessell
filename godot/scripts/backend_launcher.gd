## Python 백엔드 서버 자동 실행/종료 관리 (Autoload 싱글톤)
##
## Godot 시작 시 backend .exe를 자동 실행하고, 종료 시 함께 종료한다.
## 사용자는 Godot만 실행하면 됨.
extends Node

const BACKEND_PORT := 9720
const STARTUP_TIMEOUT := 20.0
const HEALTH_CHECK_INTERVAL := 5.0

signal backend_started
signal backend_failed(reason: String)
signal backend_stopped

var _pid: int = -1
var _is_running := false
var _health_timer: Timer

func _ready() -> void:
	_health_timer = Timer.new()
	_health_timer.wait_time = HEALTH_CHECK_INTERVAL
	_health_timer.timeout.connect(_on_health_check)
	add_child(_health_timer)

	# 자동 시작
	print("[Backend] Auto-starting...")
	_start_backend()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		_stop_backend()
		get_tree().quit()


func _start_backend() -> void:
	# 1. 이미 실행 중인지 헬스 체크
	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(func(_r: int, code: int, _h: PackedStringArray, _b: PackedByteArray) -> void:
		http.queue_free()
		if code == 200:
			print("[Backend] Already running on port %d" % BACKEND_PORT)
			_is_running = true
			_health_timer.start()
			backend_started.emit()
		else:
			_launch_backend()
	)
	var err := http.request("http://127.0.0.1:%d/health" % BACKEND_PORT)
	if err != OK:
		_launch_backend()


func _launch_backend() -> void:
	# 프로젝트 루트 경로 (godot/ 의 상위)
	var project_dir := ProjectSettings.globalize_path("res://")
	# godot/ 폴더 안에서 실행 중이므로 상위가 auto-tessell 루트
	var root := project_dir.get_base_dir()

	print("[Backend] Project dir: %s" % project_dir)
	print("[Backend] Root dir: %s" % root)

	# 탐색 순서
	var search_paths: Array[String] = [
		# 설치 모드: Godot .exe 옆 backend/
		OS.get_executable_path().get_base_dir().path_join("backend/auto-tessell.exe"),
		OS.get_executable_path().get_base_dir().path_join("backend/auto-tessell"),
		# 개발 모드: 프로젝트 루트의 dist/
		root.path_join("dist/auto-tessell/auto-tessell.exe"),
		root.path_join("dist/auto-tessell/auto-tessell"),
		# 개발 모드 대안: 절대 경로 (Windows)
		"D:/work/claude_code/auto-tessell/dist/auto-tessell/auto-tessell.exe",
	]

	for path in search_paths:
		# Windows 경로 정규화
		var normalized := path.replace("/", "\\") if OS.get_name() == "Windows" else path
		print("[Backend] Trying: %s" % normalized)
		if FileAccess.file_exists(path):
			print("[Backend] Found: %s" % path)
			_pid = OS.create_process(path, [])
			if _pid > 0:
				print("[Backend] Started PID=%d" % _pid)
				_wait_for_startup()
				return
			else:
				print("[Backend] Failed to create process")

	# Python fallback (개발 모드 — WSL 또는 Windows Python)
	print("[Backend] No .exe found, trying Python...")
	var python_cmds := ["py", "python", "python3"]
	for py in python_cmds:
		# desktop.server 모듈 실행
		_pid = OS.create_process(py, ["-m", "desktop.server", "--port", str(BACKEND_PORT)], false)
		if _pid > 0:
			print("[Backend] Started via %s, PID=%d" % [py, _pid])
			_wait_for_startup()
			return

	# 모든 방법 실패
	var msg := "백엔드 서버를 시작할 수 없습니다.\n\n"
	msg += "시도한 경로:\n"
	for p in search_paths:
		msg += "  - %s\n" % p
	msg += "\n해결 방법:\n"
	msg += "1. CMD에서 직접 실행: python -m desktop.server\n"
	msg += "2. dist/auto-tessell/auto-tessell.exe 가 있는지 확인\n"
	print("[Backend] FAILED: " + msg)
	backend_failed.emit(msg)


func _wait_for_startup() -> void:
	var elapsed := 0.0
	while elapsed < STARTUP_TIMEOUT:
		await get_tree().create_timer(1.0).timeout
		elapsed += 1.0

		# 헬스 체크
		var http := HTTPRequest.new()
		add_child(http)
		var success := false
		http.request_completed.connect(func(_r: int, code: int, _h: PackedStringArray, _b: PackedByteArray) -> void:
			http.queue_free()
			if code == 200:
				success = true
				_is_running = true
				_health_timer.start()
				print("[Backend] Ready! (%.0fs)" % elapsed)
				backend_started.emit()
		)
		http.request("http://127.0.0.1:%d/health" % BACKEND_PORT)

		await get_tree().create_timer(1.5).timeout
		if _is_running:
			return

	backend_failed.emit("서버 시작 타임아웃 (%.0fs)\n\nCMD에서 직접 실행해보세요:\ndist\\auto-tessell\\auto-tessell.exe" % STARTUP_TIMEOUT)


func _stop_backend() -> void:
	_health_timer.stop()
	_is_running = false
	if _pid > 0:
		print("[Backend] Stopping PID=%d" % _pid)
		OS.kill(_pid)
		_pid = -1
	backend_stopped.emit()


func _on_health_check() -> void:
	if not _is_running:
		return
	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(func(_r: int, code: int, _h: PackedStringArray, _b: PackedByteArray) -> void:
		http.queue_free()
		if code != 200:
			print("[Backend] Health check failed")
			_is_running = false
			_launch_backend()
	)
	http.request("http://127.0.0.1:%d/health" % BACKEND_PORT)


func is_running() -> bool:
	return _is_running


func restart() -> void:
	_stop_backend()
	await get_tree().create_timer(1.0).timeout
	_launch_backend()
