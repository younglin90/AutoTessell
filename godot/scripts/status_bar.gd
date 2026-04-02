## 하단 상태바
extends PanelContainer

func _ready() -> void:
	# Theme 기반 + 상단 border만 추가
	var base: StyleBoxFlat = get_theme_stylebox("panel", "PanelContainer").duplicate() if get_theme_stylebox("panel", "PanelContainer") is StyleBoxFlat else StyleBoxFlat.new()
	base.bg_color = Color(0.059, 0.055, 0.078)  # bg_base (더 어두운 배경)
	base.border_width_top = 1
	base.set_corner_radius_all(0)
	base.content_margin_top = 4
	base.content_margin_bottom = 4
	add_theme_stylebox_override("panel", base)
