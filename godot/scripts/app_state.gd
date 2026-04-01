## 앱 전역 상태 관리 (Autoload 싱글톤)
extends Node

# -----------------------------------------------------------------------
# Signals
# -----------------------------------------------------------------------
signal state_changed(new_state: String)
signal quality_changed(quality: String)

# -----------------------------------------------------------------------
# State
# -----------------------------------------------------------------------
enum State { IDLE, UPLOADING, MESHING, COMPLETED, FAILED }

var current_state: int = State.IDLE:
	set(v):
		current_state = v
		state_changed.emit(State.keys()[v])

var quality_level: String = "standard":
	set(v):
		quality_level = v
		quality_changed.emit(v)

var tier_hint: String = "auto"
var max_iterations: int = 3
var current_job_id: String = ""
var last_result: Dictionary = {}

# 최근 파일 경로
var recent_files: PackedStringArray = []

# -----------------------------------------------------------------------
# Methods
# -----------------------------------------------------------------------
func reset() -> void:
	current_state = State.IDLE
	current_job_id = ""
	last_result = {}


func add_recent_file(path: String) -> void:
	if path in recent_files:
		recent_files.remove_at(recent_files.find(path))
	recent_files.insert(0, path)
	if recent_files.size() > 10:
		recent_files.resize(10)
