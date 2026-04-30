# Auto-Tessell 알고리즘 Reference (BETA2617)

자체 구현된 핵심 알고리즘의 reference. 외부 lib 참조 + 자체 변형 + 출처.

## 1. Tet quality (Klingner mean-ratio)

**file**: `core/generator/native_tet/quality.py`

```
Q = 12 × (3V)^(2/3) / Σ_e |e|²
```
여기서 V = tet 부피, e = 6 edges. 정사면체 → Q = 1.

**출처**: Klingner & Shewchuk 2008, "Aggressive Tetrahedral Mesh Improvement".

## 2. Stellar 4-op queue (P2.1, beta2582)

**file**: `core/generator/native_tet/stellar.py`

worst-first queue 처리:
- 32 flip (3-2 face flip)
- 44 flip (4-4 chord flip)
- collapse / split (env-gated, default ON beta2582)
- smooth (AVOID list — Klingner monotone proof 보존)

**출처**: Klingner 2008 §3.2, §4.

## 3. AMIPS smoothing (RRR2, beta2307)

**file**: `core/generator/native_tet/mesher.py:2566`

target: worst quality 회복.
guard (D-cell recovery, P1.3 추가):
```
worst_drop ≤ 0.015 AND mean_gain ≥ -1e-12
OR (P1.3 brand): min_gain ≥ 0.005 AND mean_gain ≥ -0.005
```

**출처**: fTetWild §3.5 (envelope-bounded relocation).

## 4. Volumetric Lloyd CVT 3D (P3.1, beta2363)

**file**: `core/generator/native_tet/cvt3d.py`

target = 인접 tet centroid 평균 (Voronoi-like).
quality-weighted (beta2586): poor tet (q<0.3) 의 centroid weight = 1/(q+0.05).

**출처**: Du, Faber, Gunzburger 1999 (CVT theory).

## 5. Self-intersection detect (Möller 1997)

**file**: `core/preprocessor/native_repair/self_intersect.py`

algorithm:
1. AABB tree (KDTree) 로 후보 페어.
2. tri-tri intersection (separating axis test).
3. resolve (P2.6, beta2585): 교차 face drop + hole_fill chain.

**출처**: Möller 1997, "A Fast Triangle-Triangle Intersection Test".

## 6. Eberly point-to-triangle distance (C8-2.1.2, beta2592)

**file**: `core/generator/native_ai/gpu_envelope.py`

7-region 분류:
- region 0: q 가 tri 평면 정사영 → 내부 (s≥0, t≥0, s+t≤1).
- region 1: vertex A.
- region 2/3: edge AB / AC.
- region 4: edge BC.

torch.compile + fp16 (CUDA) → 50-100× speedup.

**출처**: Eberly, "Distance Between Point and Triangle in 3D" (Geometric Tools).

## 7. Garland-Heckbert quadric decimation (P2.3)

**file**: `core/preprocessor/native_remesh/quadric_decimate.py`

각 vertex 의 quadric Q_v = Σ K_f (incident face plane).
edge collapse cost = (v_target)ᵀ Q_combined v_target.

**출처**: Garland & Heckbert 1997, "Surface Simplification Using Quadric Error Metrics".

## 8. Pointwise T-Rex Layer Count Reduction (P3.3, beta2367)

**file**: `core/layers/native_bl_lcr.py`

per-vertex collision_distance 기반 max_layers 계산:
```
sum(first × growth^k, k=0..n-1) ≤ safety × collision_dist
→ n = floor(log_g(1 + (g - 1) × safety × collision / first))
```
G3.3 / beta2587: 50%+ reduce 시 cfg.num_layers 를 globally median.

## 9. cfMesh splitInternalLayers (P3.4, beta2591)

**file**: `core/layers/native_bl.py:2247`

mean aspect > threshold 시 layer 균일 subdivide:
```
[0, 1, 2, ..., N] → [0, 0.5, 1, 1.5, ..., N]
mid_dict[v] = 0.5 × (fp[lp_ids[k][v]] + fp[lp_ids[k+1][v]])
cfg.num_layers ← 2N
```

**출처**: cfMesh User's Guide.

## 10. y+ targeting (Schlichting flat plate, beta2267 + H4)

**file**: `core/layers/native_bl.py:1680`

```
Re = U·L/ν
Cf = 0.058 / Re^0.2  (Schlichting 1979)
u_τ = U·√(Cf/2)
y₁ = y⁺·ν/u_τ
```
H4 (beta2613): env `AUTO_TESSELL_BL_AUTO_YPLUS=N` 자동.

**출처**: Schlichting "Boundary Layer Theory" 7판 §17.

## 11. Mixed-element pyramid interface (G2/H3, beta2603/2612)

**file**: `core/layers/mixed_pyramid.py`

interface quad 식별 → 5-vertex pyramid + 4 tri face per quad.
apex = centroid + face_normal × (mean_edge × offset_factor).

quality: 정사각뿔 (apex 정상 위치 = base 대각선 × √2/2) → Q≈1.

## 12. ML quality predictor (AI-V1, beta2559+)

**file**: `core/generator/native_ai/training_data.py` + `train_predictor.py`

- V1: 12-dim coords + 8-dim 1-ring context → MLP 20→64→64→1 (sigmoid).
- V2 (H5/beta2614): + 4-dim curvature features → 24-dim 입력.
- loss: MSE on Klingner quality.
- val_loss 0.005-0.006 (CUDA, 7800 samples).

## 13. Möller AABB-tree spatial query

**file**: `core/preprocessor/native_repair/self_intersect.py:_kdtree_overlap_pairs`

triangle centroid KDTree → k-nearest 후보 → AABB filter → tri-tri test.

**출처**: Möller, Akenine-Möller, Trumbore "Real-Time Rendering" 4판.

## 14. fTetWild envelope (Hu 2020)

**file**: `core/generator/native_tet/envelope.py`

eps = max(bbox_diag × base_ratio, shortest_edge × 0.05).
mesh operation 후 모든 surface vertex 가 envelope 안에 있는지 검증.
violations → relocate to closest envelope point.

**출처**: Hu, Schneider, Wang, Zorin, Panozzo 2020 "Fast Tetrahedral Meshing in the Wild" (fTetWild).

## 15. CGNS / CCMIO HDF5 hierarchy

**file**: `core/utils/cgns_writer.py` / `core/utils/ccmio_writer.py`

CGNS SIDS v4.4: `/Base/Zone-N/{GridCoordinates, NGonElements, NFaceElements, ZoneBC}`.
CCMIO (Siemens reverse): `/Meshes/Mesh-N/{Vertices, Cells, InternalFaces, BoundaryFaces-K}`.

**출처**: CGNS Standard Interface Data Structures v4.4 + libccmio public API.

## 16. Fluent .msh ASCII (TGrid format)

**file**: `core/utils/fluent_writer.py`

records (10/12/13/45) — node/cell/face/zone-name. hex notation IDs.

**출처**: ANSYS Fluent User's Guide "Mesh File Format" 부록.

## 17. VTK UnstructuredGrid XML

**file**: `core/utils/vtk_writer.py`

cell types (vtkCellType.h): TETRA=10, HEXA=12, WEDGE=13, PYRAMID=14, POLYHEDRON=42.
polyhedron: faces + faceoffsets data array.

**출처**: VTK User's Guide / vtkXMLUnstructuredGridWriter.

## 참고 논문 / 표준

- Klingner & Shewchuk 2008 (Aggressive Tet)
- Hu 2020 fTetWild
- Möller 1997 (Tri-Tri intersection)
- Eberly Geometric Tools (Distance to triangle)
- Garland & Heckbert 1997 (QEM decimation)
- Schlichting "Boundary Layer Theory"
- Marechal 2009 (Octree mesh balance)
- CGNS SIDS v4.4
- Siemens libccmio public API.
