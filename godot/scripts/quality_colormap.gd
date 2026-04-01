## 메쉬 품질 컬러맵 시각화
##
## 셀/면 품질 값(non-orthogonality, skewness 등)을 색상으로 매핑하여
## MeshViewer에 오버레이한다.
##
## 컬러맵: 파란색(좋음) → 초록 → 노랑 → 빨강(나쁨)
extends RefCounted

# -----------------------------------------------------------------------
# Color mapping
# -----------------------------------------------------------------------

## 품질 값(0~1 정규화)을 색상으로 변환 (jet 컬러맵)
static func quality_to_color(normalized_value: float) -> Color:
	var v := clampf(normalized_value, 0.0, 1.0)

	if v < 0.25:
		# Blue → Cyan
		var t := v / 0.25
		return Color(0.0, t, 1.0)
	elif v < 0.5:
		# Cyan → Green
		var t := (v - 0.25) / 0.25
		return Color(0.0, 1.0, 1.0 - t)
	elif v < 0.75:
		# Green → Yellow
		var t := (v - 0.5) / 0.25
		return Color(t, 1.0, 0.0)
	else:
		# Yellow → Red
		var t := (v - 0.75) / 0.25
		return Color(1.0, 1.0 - t, 0.0)


## Non-orthogonality 값을 정규화 (0°=파랑, 65°=노랑, 85°+=빨강)
static func normalize_non_ortho(degrees: float) -> float:
	return clampf(degrees / 85.0, 0.0, 1.0)


## Skewness 값을 정규화 (0=파랑, 4=노랑, 8+=빨강)
static func normalize_skewness(skew: float) -> float:
	return clampf(skew / 8.0, 0.0, 1.0)


## Aspect ratio를 정규화 (1=파랑, 50=노랑, 100+=빨강)
static func normalize_aspect_ratio(ar: float) -> float:
	return clampf((ar - 1.0) / 99.0, 0.0, 1.0)


# -----------------------------------------------------------------------
# Mesh coloring
# -----------------------------------------------------------------------

## SurfaceTool 메쉬에 per-vertex quality 색상을 적용한다.
## quality_values: face 인덱스 → quality 값 매핑 (배열)
## normalize_fn: 정규화 함수 (위 static func 중 하나)
static func apply_quality_colors(
	mesh: ArrayMesh,
	quality_values: PackedFloat32Array,
	normalize_fn: Callable,
) -> ArrayMesh:
	if mesh == null or quality_values.is_empty():
		return mesh

	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)

	# 기존 메쉬에서 삼각형 추출
	var arrays := mesh.surface_get_arrays(0)
	if arrays.is_empty():
		return mesh

	var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]

	# 각 삼각형(3개 정점)마다 face 품질 값으로 색상 부여
	var face_idx := 0
	for i in range(0, verts.size(), 3):
		var color := Color.WHITE
		if face_idx < quality_values.size():
			var normalized: float = normalize_fn.call(quality_values[face_idx])
			color = quality_to_color(normalized)

		for j in range(3):
			if i + j < verts.size():
				st.set_color(color)
				st.add_vertex(verts[i + j])
		face_idx += 1

	st.generate_normals()
	var colored_mesh := st.commit()

	# 색상이 보이도록 vertex color 머티리얼 적용
	var material := StandardMaterial3D.new()
	material.vertex_color_use_as_albedo = true
	material.cull_mode = BaseMaterial3D.CULL_DISABLED

	return colored_mesh
