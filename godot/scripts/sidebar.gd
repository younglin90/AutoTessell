## 사이드바 패널 스크립트
extends PanelContainer

func _ready() -> void:
	# 사이드바 스타일 설정
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.12, 0.12, 0.15, 1.0)
	style.content_margin_left = 12
	style.content_margin_right = 12
	style.content_margin_top = 8
	style.content_margin_bottom = 8
	add_theme_stylebox_override("panel", style)
