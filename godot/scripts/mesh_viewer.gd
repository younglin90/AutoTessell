## 3D 메쉬 뷰어
## STL/OBJ 파일 또는 서버에서 받은 메쉬 데이터를 3D로 표시한다.
## 마우스로 회전/줌/패닝 가능.
##
## 추가 키보드 단축키:
##   F — 현재 메쉬 Bounding Box에 카메라를 자동 맞춤 (fit to view)
##   W — 와이어프레임 모드 토글
##   R — 카메라를 초기 위치로 리셋
extends Node3D

# -----------------------------------------------------------------------
# Node references
# -----------------------------------------------------------------------
@onready var camera: Camera3D = $Camera3D
@onready var mesh_instance: MeshInstance3D = $MeshInstance

# -----------------------------------------------------------------------
# Camera orbit state
# -----------------------------------------------------------------------
var _orbit_distance: float = 5.0
var _orbit_yaw: float = 0.0
var _orbit_pitch: float = -30.0
var _orbit_target: Vector3 = Vector3.ZERO
var _is_rotating: bool = false
var _is_panning: bool = false
var _last_mouse_pos: Vector2 = Vector2.ZERO

const ROTATE_SPEED := 0.3
const PAN_SPEED := 0.005
const ZOOM_SPEED := 0.1
const MIN_DISTANCE := 0.5
const MAX_DISTANCE := 100.0

# Default camera state (used by reset view)
const DEFAULT_YAW := 0.0
const DEFAULT_PITCH := -30.0
const DEFAULT_DISTANCE := 5.0
const DEFAULT_TARGET := Vector3.ZERO

# Wireframe state
var _wireframe_enabled: bool = false

# -----------------------------------------------------------------------
# Lifecycle
# -----------------------------------------------------------------------
func _ready() -> void:
	_update_camera()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		match mb.button_index:
			MOUSE_BUTTON_MIDDLE:
				if mb.shift_pressed:
					_is_panning = mb.pressed
				else:
					_is_rotating = mb.pressed
				_last_mouse_pos = mb.position
			MOUSE_BUTTON_RIGHT:
				_is_rotating = mb.pressed
				_last_mouse_pos = mb.position
			MOUSE_BUTTON_WHEEL_UP:
				_orbit_distance = max(MIN_DISTANCE, _orbit_distance * (1.0 - ZOOM_SPEED))
				_update_camera()
			MOUSE_BUTTON_WHEEL_DOWN:
				_orbit_distance = min(MAX_DISTANCE, _orbit_distance * (1.0 + ZOOM_SPEED))
				_update_camera()

	elif event is InputEventMouseMotion:
		var mm := event as InputEventMouseMotion
		var delta := mm.position - _last_mouse_pos
		_last_mouse_pos = mm.position

		if _is_rotating:
			_orbit_yaw -= delta.x * ROTATE_SPEED
			_orbit_pitch = clamp(_orbit_pitch - delta.y * ROTATE_SPEED, -89, 89)
			_update_camera()

		elif _is_panning:
			var right := camera.global_transform.basis.x
			var up := camera.global_transform.basis.y
			_orbit_target -= right * delta.x * PAN_SPEED * _orbit_distance
			_orbit_target += up * delta.y * PAN_SPEED * _orbit_distance
			_update_camera()

	elif event is InputEventKey:
		var ke := event as InputEventKey
		if ke.pressed and not ke.echo:
			match ke.keycode:
				KEY_F:
					get_viewport().set_input_as_handled()
					fit_to_view()
				KEY_W:
					get_viewport().set_input_as_handled()
					_wireframe_enabled = not _wireframe_enabled
					toggle_wireframe(_wireframe_enabled)
				KEY_R:
					get_viewport().set_input_as_handled()
					reset_view()


func _update_camera() -> void:
	var yaw_rad := deg_to_rad(_orbit_yaw)
	var pitch_rad := deg_to_rad(_orbit_pitch)

	var offset := Vector3(
		_orbit_distance * cos(pitch_rad) * sin(yaw_rad),
		_orbit_distance * sin(-pitch_rad),
		_orbit_distance * cos(pitch_rad) * cos(yaw_rad),
	)

	camera.global_position = _orbit_target + offset
	camera.look_at(_orbit_target, Vector3.UP)


# -----------------------------------------------------------------------
# Camera controls
# -----------------------------------------------------------------------

## Fit the camera to the current mesh bounding box.
## Centers the orbit target on the mesh center and sets the distance so
## the entire mesh is visible.  Does nothing if no mesh is loaded.
func fit_to_view() -> void:
	if mesh_instance.mesh == null:
		return

	var aabb := mesh_instance.mesh.get_aabb()
	_orbit_target = aabb.get_center()
	_orbit_distance = clamp(aabb.size.length() * 1.5, MIN_DISTANCE, MAX_DISTANCE)
	_update_camera()
	print("[MeshViewer] Fit to view: center=%s distance=%.3f" % [_orbit_target, _orbit_distance])


## Reset the camera to its default position regardless of loaded mesh.
func reset_view() -> void:
	_orbit_yaw = DEFAULT_YAW
	_orbit_pitch = DEFAULT_PITCH
	_orbit_distance = DEFAULT_DISTANCE
	_orbit_target = DEFAULT_TARGET
	_update_camera()
	print("[MeshViewer] View reset to default")


# -----------------------------------------------------------------------
# Mesh loading
# -----------------------------------------------------------------------

## STL 파일에서 메쉬 로드
func load_stl(file_path: String) -> void:
	var file := FileAccess.open(file_path, FileAccess.READ)
	if not file:
		push_error("Cannot open STL: %s" % file_path)
		return

	var data := file.get_buffer(file.get_length())
	file.close()

	# Binary STL 파싱
	if data.size() < 84:
		push_error("STL file too small")
		return

	# Header (80 bytes) + num_triangles (4 bytes)
	var num_triangles := data.decode_u32(80)
	print("Loading STL: %d triangles" % num_triangles)

	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)

	var offset := 84
	for i in range(num_triangles):
		if offset + 50 > data.size():
			break

		# Normal (12 bytes)
		var nx := data.decode_float(offset)
		var ny := data.decode_float(offset + 4)
		var nz := data.decode_float(offset + 8)
		var normal := Vector3(nx, ny, nz)

		# 3 vertices (36 bytes)
		for v in range(3):
			var vo := offset + 12 + v * 12
			var vx := data.decode_float(vo)
			var vy := data.decode_float(vo + 4)
			var vz := data.decode_float(vo + 8)
			st.set_normal(normal)
			st.add_vertex(Vector3(vx, vy, vz))

		offset += 50  # 12 + 36 + 2 (attribute byte count)

	st.generate_normals()
	var array_mesh := st.commit()

	# 머티리얼 설정
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(0.3, 0.6, 0.9, 1.0)
	material.metallic = 0.1
	material.roughness = 0.7
	material.cull_mode = BaseMaterial3D.CULL_DISABLED  # 양면 렌더링

	mesh_instance.mesh = array_mesh
	mesh_instance.material_override = material

	# Re-apply wireframe state to the new material
	if _wireframe_enabled:
		toggle_wireframe(true)

	# 카메라를 메쉬 중심으로 이동
	fit_to_view()

	print("STL loaded: %d triangles, bounds=%s" % [num_triangles, array_mesh.get_aabb()])


## 서버에서 메쉬 데이터 로드 (JSON)
func load_from_server(job_id: String) -> void:
	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(func(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
		if code == 200:
			var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
			if parsed is Dictionary:
				_build_mesh_from_json(parsed as Dictionary)
		http.queue_free()
	)
	http.request(WebSocketClient.base_url + "/jobs/%s/surface" % job_id)


func _build_mesh_from_json(data: Dictionary) -> void:
	# 서버에서 받은 points + boundary_faces로 메쉬 구성
	var points: Array = data.get("points", [])
	var faces: Array = data.get("boundary_faces", [])

	if points.is_empty() or faces.is_empty():
		return

	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)

	for face in faces:
		if face.size() >= 3:
			# Fan triangulation for polygons
			for i in range(1, face.size() - 1):
				var v0: Array = points[face[0]]
				var v1: Array = points[face[i]]
				var v2: Array = points[face[i + 1]]
				st.add_vertex(Vector3(v0[0], v0[1], v0[2]))
				st.add_vertex(Vector3(v1[0], v1[1], v1[2]))
				st.add_vertex(Vector3(v2[0], v2[1], v2[2]))

	st.generate_normals()
	var array_mesh := st.commit()

	var material := StandardMaterial3D.new()
	material.albedo_color = Color(0.3, 0.7, 0.4, 1.0)
	material.metallic = 0.1
	material.roughness = 0.6
	material.cull_mode = BaseMaterial3D.CULL_DISABLED

	mesh_instance.mesh = array_mesh
	mesh_instance.material_override = material

	# Re-apply wireframe state to the new material
	if _wireframe_enabled:
		toggle_wireframe(true)

	fit_to_view()


## 와이어프레임 오버레이 토글
## W 키 또는 외부에서 직접 호출 가능.
func toggle_wireframe(enabled: bool) -> void:
	_wireframe_enabled = enabled
	if mesh_instance.material_override:
		var mat := mesh_instance.material_override as StandardMaterial3D
		if enabled:
			mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			mat.albedo_color = Color(0.2, 0.8, 1.0, 1.0)
		else:
			mat.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL
			mat.albedo_color = Color(0.3, 0.6, 0.9, 1.0)
	print("[MeshViewer] Wireframe: %s" % ("on" if enabled else "off"))


## 메쉬 초기화
func clear_mesh() -> void:
	mesh_instance.mesh = null
	_wireframe_enabled = false
