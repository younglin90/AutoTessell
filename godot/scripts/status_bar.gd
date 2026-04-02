## 하단 상태바
extends PanelContainer

func _ready() -> void:
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.11, 0.10, 0.13, 1.0)
	style.border_color = Color(0.25, 0.22, 0.30, 0.3)
	style.border_width_top = 1
	style.content_margin_left = 10
	style.content_margin_right = 10
	style.content_margin_top = 4
	style.content_margin_bottom = 4
	add_theme_stylebox_override("panel", style)
