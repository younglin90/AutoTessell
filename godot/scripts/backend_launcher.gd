## Python 백엔드 서버 자동 실행/종료 관리 (Autoload 싱글톤)
##
## Godot 시작 시 backend/auto-tessell.exe (또는 python -m desktop.server)를
## 자동으로 실행하고, Godot 종료 시 함께 종료한다.
## 사용자는 Godot .exe만 더블클릭하면 됨.
extends Node

# -----------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------
const BACKEND_PORT := 9720
const HEALTH_CHECK_INTERVAL := 2.0
const STARTUP_TIMEOUT := 15.0

# 백엔드 실행 파일 탐색 순서
const BACKEND_PATHS := [
	"res://backend/auto-tessell.exe",        # PyInstaller 번들 (Windows)
	"res://backend/auto-tessell",            # PyInstaller 번들 (Linux)
	"../dist/auto-tessell/auto-tessell.exe", # 개발 모드 (Windows)
	"../dist/auto-tessell/auto-tessell",     # 개발 모드 (Linux)
]

# Python fallback (개발 모드)
const PYTHON_COMMANDS := [
	"python", "python3", "py",
]

# -----------------------------------------------------------------------
# Signals
# -----------------------------------------------------------------------
signal backend_started
signal backend_failed(reason: String)
signal backend_stopped

# -----------------------------------------------------------------------
# State
# -----------------------------------------------------------------------
var _pid: int = -1
var _is_running := false
var _health_timer: Timer

# -----------------------------------------------------------------------
# Lifecycle
# -----------------------------------------------------------------------
func _ready() -> void:
	# 헬스 체크 타이머
	_health_timer = Timer.new()
	_health_timer.wait_time = HEALTH_CHECK_INTERVAL
	_health_timer.timeout.connect(_on_health_check)
	add_child(_health_timer)

	# 자동 시작
	_start_backend()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		_stop_backend()
		get_tree().quit()


# -----------------------------------------------------------------------
# Backend management
# -----------------------------------------------------------------------
func _start_backend() -> void:
	# 먼저 이미 실행 중인지 헬스 체크
	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(func(_result: int, code: int, _headers: PackedStringArray, _body: PackedByteArray) -> void:
		http.queue_free()
		if code == 200:
			# 이미 실행 중
			print("[Backend] Already running on port %d" % BACKEND_PORT)
			_is_running = true
			_health_timer.start()
			backend_started.emit()
		else:
			# 실행 필요
			_launch_backend()
	)
	http.request("http://127.0.0.1:%d/health" % BACKEND_PORT)


func _launch_backend() -> void:
	# 1. PyInstaller 번들 찾기
	for path in BACKEND_PATHS:
		var abs_path := ""
		if path.begins_with("res://"):
			abs_path = ProjectSettings.globalize_path(path)
		else:
			abs_path = OS.get_executable_path().get_base_dir().path_join(path)

		if FileAccess.file_exists(abs_path):
			print("[Backend] Found: %s" % abs_path)
			_pid = OS.create_process(abs_path, ["--port", str(BACKEND_PORT)])
			if _pid > 0:
				print("[Backend] Started PID=%d" % _pid)
				_wait_for_startup()
				return

	# 2. Python fallback (개발 모드)
	for python in PYTHON_COMMANDS:
		var exit_code := OS.execute(python, ["--version"], [], false)
		if exit_code == 0:
			var project_root := OS.get_executable_path().get_base_dir()
			# Godot에서 한 단계 위가 프로젝트 루트
			if project_root.ends_with("godot"):
				project_root = project_root.get_base_dir()
			print("[Backend] Python fallback: %s -m desktop.server" % python)
			_pid = OS.create_process(python, [
				"-m", "desktop.server", "--port", str(BACKEND_PORT)
			])
			if _pid > 0:
				print("[Backend] Started PID=%d (Python)" % _pid)
				_wait_for_startup()
				return

	# 3. 실패
	print("[Backend] Failed to start backend server")
	backend_failed.emit("백엔드 서버를 찾을 수 없습니다.\n\n" +
		"방법 1: python -m desktop.server 직접 실행\n" +
		"방법 2: PyInstaller로 빌드 후 backend/ 폴더에 배치")


func _wait_for_startup() -> void:
	"""백엔드가 준비될 때까지 헬스 체크 반복."""
	var elapsed := 0.0
	while elapsed < STARTUP_TIMEOUT:
		await get_tree().create_timer(0.5).timeout
		elapsed += 0.5

		var http := HTTPRequest.new()
		add_child(http)
		var got_response := false
		http.request_completed.connect(func(_r: int, code: int, _h: PackedStringArray, _b: PackedByteArray) -> void:
			http.queue_free()
			got_response = true
			if code == 200:
				_is_running = true
				_health_timer.start()
				backend_started.emit()
				print("[Backend] Ready! (%.1fs)" % elapsed)
		)
		http.request("http://127.0.0.1:%d/health" % BACKEND_PORT)

		await get_tree().create_timer(1.0).timeout
		if _is_running:
			return

	# 타임아웃
	backend_failed.emit("백엔드 서버 시작 타임아웃 (%.0fs)" % STARTUP_TIMEOUT)


func _stop_backend() -> void:
	"""백엔드 프로세스 종료."""
	_health_timer.stop()
	_is_running = false
	if _pid > 0:
		print("[Backend] Stopping PID=%d" % _pid)
		OS.kill(_pid)
		_pid = -1
	backend_stopped.emit()


func _on_health_check() -> void:
	"""주기적 헬스 체크."""
	if not _is_running:
		return

	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(func(_r: int, code: int, _h: PackedStringArray, _b: PackedByteArray) -> void:
		http.queue_free()
		if code != 200:
			print("[Backend] Health check failed, attempting restart...")
			_is_running = false
			_launch_backend()
	)
	http.request("http://127.0.0.1:%d/health" % BACKEND_PORT)


# -----------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------
func is_running() -> bool:
	return _is_running


func restart() -> void:
	"""백엔드 재시작."""
	_stop_backend()
	await get_tree().create_timer(1.0).timeout
	_launch_backend()
