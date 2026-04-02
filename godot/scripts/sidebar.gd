## 사이드바 패널 스크립트
extends PanelContainer

func _ready() -> void:
	# Warm dark 사이드바 스타일
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.14, 0.13, 0.16, 1.0)  # 약간 따뜻한 다크
	style.border_color = Color(0.25, 0.22, 0.30, 0.5)
	style.border_width_right = 1
	style.content_margin_left = 12
	style.content_margin_right = 12
	style.content_margin_top = 8
	style.content_margin_bottom = 8
	style.corner_radius_top_left = 0
	style.corner_radius_bottom_left = 0
	add_theme_stylebox_override("panel", style)
