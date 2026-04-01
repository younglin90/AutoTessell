## 설정 저장/불러오기 매니저
## user:// 디렉터리에 JSON으로 설정을 영구 저장한다.
extends RefCounted

const SETTINGS_PATH := "user://autotessell_settings.json"

# -----------------------------------------------------------------------
# Default settings
# -----------------------------------------------------------------------
var _defaults := {
	"server_host": "127.0.0.1",
	"server_port": 9720,
	"quality_level": "standard",
	"tier_hint": "auto",
	"max_iterations": 3,
	"auto_export_vtk": false,
	"recent_files": [],
	"window_width": 1400,
	"window_height": 900,
	"theme": "dark",
	"language": "ko",
	"viewer_wireframe": false,
	"viewer_show_grid": true,
}

var _data: Dictionary = {}

# -----------------------------------------------------------------------
# Load / Save
# -----------------------------------------------------------------------

func load_settings() -> Dictionary:
	"""설정 파일을 로드한다. 없으면 기본값 반환."""
	if FileAccess.file_exists(SETTINGS_PATH):
		var file := FileAccess.open(SETTINGS_PATH, FileAccess.READ)
		if file:
			var json_str := file.get_as_text()
			file.close()
			var parsed: Variant = JSON.parse_string(json_str)
			if parsed is Dictionary:
				_data = parsed as Dictionary
				# 누락된 키에 기본값 채우기
				for key in _defaults:
					if not _data.has(key):
						_data[key] = _defaults[key]
				return _data
	_data = _defaults.duplicate()
	return _data


func save_settings(data: Dictionary = {}) -> void:
	"""설정을 파일에 저장한다."""
	if not data.is_empty():
		_data = data
	var file := FileAccess.open(SETTINGS_PATH, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify(_data, "\t"))
		file.close()


func get_setting(key: String, default: Variant = null) -> Variant:
	if _data.is_empty():
		load_settings()
	return _data.get(key, _defaults.get(key, default))


func set_setting(key: String, value: Variant) -> void:
	if _data.is_empty():
		load_settings()
	_data[key] = value
	save_settings()
