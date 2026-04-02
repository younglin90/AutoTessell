# Auto-Tessell Godot Desktop UI Design System

## Direction
Personality: Engineering Precision (CFD/메쉬 도구)
Theme: dark (warm)
Depth: flat (border-only, subtle accents)

## Tokens
### Spacing
Base: 4px
Scale: 4, 8, 12, 16, 24, 32

### Colors (Dark Warm)
bg_base: #0f0e14
bg_surface: #1a1924
bg_elevated: #252430
bg_input: #121118
border_subtle: #2a293a
border_focus: #4a6cf7
text_primary: #e2e2e8
text_secondary: #8888a0
text_disabled: #555568
accent: #4a6cf7
accent_hover: #5d7df9
accent_pressed: #3a5ce0
success: #4ade80
warning: #fbbf24
error: #f87171

### Typography
Default: System font 14px
Heading: Bold
Mono: for mesh stats
Base size: 14px

### Corners
Default: 4px (sm)
Panel: 6px (md)
Dialog: 8px (lg)

## Patterns Established
### Sidebar
- Width: 340px min
- ScrollContainer for long param list
- Sections with colored headers

### ParamsPanel
- ⓘ info buttons with tooltips + click dialogs
- OptionButton for enums, SpinBox for numbers, CheckBox for bools
- Section headers: accent blue-purple

### 3D Viewer
- SubViewportContainer with orbit camera
- STL binary parser
- Quality colormap (jet: blue→green→yellow→red)

### StatusBar
- Height: 30px
- Left: status message, Right: server status
