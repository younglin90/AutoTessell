## Auto-Tessell 앱 테마 팩토리
## 디자인 토큰 기반으로 전체 Theme 리소스를 생성한다.
class_name AppTheme


static func create(mode: String = "dark") -> Theme:
	var tokens := _get_tokens(mode)
	var theme := Theme.new()

	# --- 글로벌 폰트 크기 ---
	theme.default_font_size = 14

	# --- Spacing ---
	theme.set_constant("margin_left", "MarginContainer", tokens.spacing_lg)
	theme.set_constant("margin_right", "MarginContainer", tokens.spacing_lg)
	theme.set_constant("margin_top", "MarginContainer", tokens.spacing_lg)
	theme.set_constant("margin_bottom", "MarginContainer", tokens.spacing_lg)
	theme.set_constant("separation", "VBoxContainer", tokens.spacing_sm)
	theme.set_constant("separation", "HBoxContainer", tokens.spacing_sm)

	# --- Label ---
	theme.set_color("font_color", "Label", tokens.text_primary)

	# --- Button ---
	var btn := _create_button_styles(tokens)
	theme.set_stylebox("normal", "Button", btn.normal)
	theme.set_stylebox("hover", "Button", btn.hover)
	theme.set_stylebox("pressed", "Button", btn.pressed)
	theme.set_stylebox("disabled", "Button", btn.disabled)
	theme.set_color("font_color", "Button", tokens.text_primary)
	theme.set_color("font_hover_color", "Button", Color.WHITE)
	theme.set_color("font_disabled_color", "Button", tokens.text_disabled)

	# --- PanelContainer ---
	theme.set_stylebox("panel", "PanelContainer", _create_surface_style(tokens))

	# --- LineEdit ---
	var input := _create_input_styles(tokens)
	theme.set_stylebox("normal", "LineEdit", input.normal)
	theme.set_stylebox("focus", "LineEdit", input.focus)
	theme.set_stylebox("read_only", "LineEdit", input.read_only)
	theme.set_color("font_color", "LineEdit", tokens.text_primary)
	theme.set_color("font_placeholder_color", "LineEdit", tokens.text_secondary)

	# --- SpinBox (inherits LineEdit) ---
	theme.set_stylebox("normal", "SpinBox", input.normal.duplicate())
	theme.set_stylebox("focus", "SpinBox", input.focus.duplicate())

	# --- OptionButton ---
	theme.set_stylebox("normal", "OptionButton", btn.normal.duplicate())
	theme.set_stylebox("hover", "OptionButton", btn.hover.duplicate())
	theme.set_stylebox("pressed", "OptionButton", btn.pressed.duplicate())
	theme.set_color("font_color", "OptionButton", tokens.text_primary)

	# --- CheckBox ---
	theme.set_color("font_color", "CheckBox", tokens.text_primary)
	theme.set_color("font_hover_color", "CheckBox", tokens.accent_hover)

	# --- PopupMenu ---
	var popup_style := _create_popup_style(tokens)
	theme.set_stylebox("panel", "PopupMenu", popup_style)
	theme.set_stylebox("hover", "PopupMenu", _create_menu_hover_style(tokens))
	theme.set_color("font_color", "PopupMenu", tokens.text_primary)

	# --- RichTextLabel ---
	theme.set_color("default_color", "RichTextLabel", tokens.text_primary)

	# --- HSeparator ---
	var sep_style := StyleBoxLine.new()
	sep_style.color = tokens.border_subtle
	sep_style.thickness = 1
	theme.set_stylebox("separator", "HSeparator", sep_style)

	# --- ProgressBar ---
	var pb_bg := StyleBoxFlat.new()
	pb_bg.bg_color = tokens.bg_input
	pb_bg.set_corner_radius_all(tokens.corner_sm)
	theme.set_stylebox("background", "ProgressBar", pb_bg)
	var pb_fill := StyleBoxFlat.new()
	pb_fill.bg_color = tokens.accent
	pb_fill.set_corner_radius_all(tokens.corner_sm)
	theme.set_stylebox("fill", "ProgressBar", pb_fill)

	# --- ScrollContainer ---
	var scroll_bg := StyleBoxFlat.new()
	scroll_bg.bg_color = Color.TRANSPARENT
	theme.set_stylebox("panel", "ScrollContainer", scroll_bg)

	# --- TabContainer ---
	var tab_sel := StyleBoxFlat.new()
	tab_sel.bg_color = tokens.bg_surface
	tab_sel.border_width_top = 2
	tab_sel.border_color = tokens.accent
	tab_sel.corner_radius_top_left = tokens.corner_sm
	tab_sel.corner_radius_top_right = tokens.corner_sm
	tab_sel.set_content_margin_all(tokens.spacing_sm)
	theme.set_stylebox("tab_selected", "TabContainer", tab_sel)

	var tab_unsel := StyleBoxFlat.new()
	tab_unsel.bg_color = Color.TRANSPARENT
	tab_unsel.set_content_margin_all(tokens.spacing_sm)
	theme.set_stylebox("tab_unselected", "TabContainer", tab_unsel)

	var tab_panel := StyleBoxFlat.new()
	tab_panel.bg_color = tokens.bg_surface
	tab_panel.border_color = tokens.border_subtle
	tab_panel.set_border_width_all(1)
	tab_panel.border_width_top = 0
	tab_panel.set_content_margin_all(tokens.spacing_lg)
	theme.set_stylebox("panel", "TabContainer", tab_panel)

	return theme


# -----------------------------------------------------------------------
# Token definitions
# -----------------------------------------------------------------------

static func _get_tokens(mode: String) -> Dictionary:
	if mode == "dark":
		return {
			"bg_base":        Color(0.059, 0.055, 0.078),
			"bg_surface":     Color(0.102, 0.098, 0.141),
			"bg_elevated":    Color(0.145, 0.141, 0.188),
			"bg_input":       Color(0.071, 0.067, 0.094),
			"border_subtle":  Color(0.165, 0.161, 0.227),
			"border_focus":   Color(0.290, 0.424, 0.969),
			"text_primary":   Color(0.886, 0.886, 0.910),
			"text_secondary": Color(0.533, 0.533, 0.627),
			"text_disabled":  Color(0.333, 0.333, 0.408),
			"accent":         Color(0.290, 0.424, 0.969),
			"accent_hover":   Color(0.365, 0.490, 0.976),
			"accent_pressed": Color(0.227, 0.361, 0.878),
			"success":        Color(0.290, 0.871, 0.502),
			"warning":        Color(0.984, 0.749, 0.141),
			"error":          Color(0.973, 0.443, 0.443),
			"spacing_xs": 4, "spacing_sm": 8, "spacing_md": 12,
			"spacing_lg": 16, "spacing_xl": 24, "spacing_2xl": 32,
			"corner_sm": 4, "corner_md": 6, "corner_lg": 8,
		}
	else:
		return {
			"bg_base":        Color(0.973, 0.973, 0.980),
			"bg_surface":     Color(1.0, 1.0, 1.0),
			"bg_elevated":    Color(1.0, 1.0, 1.0),
			"bg_input":       Color(0.941, 0.941, 0.957),
			"border_subtle":  Color(0.847, 0.847, 0.878),
			"border_focus":   Color(0.290, 0.424, 0.969),
			"text_primary":   Color(0.102, 0.102, 0.141),
			"text_secondary": Color(0.420, 0.420, 0.502),
			"text_disabled":  Color(0.620, 0.620, 0.680),
			"accent":         Color(0.290, 0.424, 0.969),
			"accent_hover":   Color(0.365, 0.490, 0.976),
			"accent_pressed": Color(0.227, 0.361, 0.878),
			"success":        Color(0.133, 0.694, 0.298),
			"warning":        Color(0.800, 0.600, 0.000),
			"error":          Color(0.863, 0.196, 0.196),
			"spacing_xs": 4, "spacing_sm": 8, "spacing_md": 12,
			"spacing_lg": 16, "spacing_xl": 24, "spacing_2xl": 32,
			"corner_sm": 4, "corner_md": 6, "corner_lg": 8,
		}


# -----------------------------------------------------------------------
# StyleBox factories
# -----------------------------------------------------------------------

static func _create_surface_style(t: Dictionary) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = t.bg_surface
	s.border_color = t.border_subtle
	s.set_border_width_all(1)
	s.set_corner_radius_all(t.corner_md)
	s.set_content_margin_all(t.spacing_lg)
	return s


static func _create_button_styles(t: Dictionary) -> Dictionary:
	var normal := StyleBoxFlat.new()
	normal.bg_color = t.bg_elevated
	normal.border_color = t.border_subtle
	normal.set_border_width_all(1)
	normal.set_corner_radius_all(t.corner_sm)
	normal.content_margin_left = 12
	normal.content_margin_right = 12
	normal.content_margin_top = 6
	normal.content_margin_bottom = 6

	var hover := normal.duplicate()
	hover.bg_color = Color(t.accent, 0.15)
	hover.border_color = t.accent

	var pressed := normal.duplicate()
	pressed.bg_color = t.accent_pressed

	var disabled := normal.duplicate()
	disabled.bg_color = t.bg_input
	disabled.border_color = Color(t.border_subtle, 0.5)

	return {"normal": normal, "hover": hover, "pressed": pressed, "disabled": disabled}


static func _create_input_styles(t: Dictionary) -> Dictionary:
	var normal := StyleBoxFlat.new()
	normal.bg_color = t.bg_input
	normal.border_color = t.border_subtle
	normal.set_border_width_all(1)
	normal.set_corner_radius_all(t.corner_sm)
	normal.set_content_margin_all(6)

	var focus := normal.duplicate()
	focus.border_color = t.border_focus
	focus.set_border_width_all(2)

	var read_only := normal.duplicate()
	read_only.bg_color = t.bg_surface

	return {"normal": normal, "focus": focus, "read_only": read_only}


static func _create_popup_style(t: Dictionary) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = t.bg_elevated
	s.border_color = t.border_subtle
	s.set_border_width_all(1)
	s.set_corner_radius_all(t.corner_lg)
	s.shadow_size = 6
	s.shadow_offset = Vector2(0, 3)
	s.shadow_color = Color(0, 0, 0, 0.25)
	s.set_content_margin_all(t.spacing_sm)
	return s


static func _create_menu_hover_style(t: Dictionary) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = Color(t.accent, 0.15)
	s.set_corner_radius_all(t.corner_sm)
	s.set_content_margin_all(4)
	return s
