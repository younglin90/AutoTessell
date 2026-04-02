## 사이드바 패널 스크립트
extends PanelContainer

func _ready() -> void:
	# Theme이 PanelContainer 기본 스타일 적용.
	# 사이드바만 우측 border 추가:
	var base: StyleBoxFlat = get_theme_stylebox("panel", "PanelContainer").duplicate() if get_theme_stylebox("panel", "PanelContainer") is StyleBoxFlat else StyleBoxFlat.new()
	base.border_width_right = 1
	base.corner_radius_top_left = 0
	base.corner_radius_bottom_left = 0
	base.corner_radius_top_right = 0
	base.corner_radius_bottom_right = 0
	add_theme_stylebox_override("panel", base)
