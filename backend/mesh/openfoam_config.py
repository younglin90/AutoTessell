"""
Auto-generate OpenFOAM configuration files for snappyHexMesh external-flow meshing.

Domain layout (external aerodynamics, flow in +x direction):
  x:  center - 10L  →  center + 20L   (upstream 10L, downstream 20L)
  y:  center - 5L   →  center + 5L
  z:  center - 5L   →  center + 5L

where L = characteristic_length (longest bbox dimension).

snappy_hex_mesh_dict() accepts an optional StlComplexity (from stl_utils) to
enable curvature-based adaptive refinement:
  - Simple geometry   (ratio < 3):  refine level 1-2, featureAngle 40°
  - Moderate geometry (ratio 3-10): refine level 1-3, featureAngle 30°
  - Complex geometry  (ratio > 10): refine level 2-4, featureAngle 20°

Distance-based refinementRegions:
  - Within 10% L: max refinement (sharp near-wall cells)
  - Within 50% L: mid refinement (geometry boundary layer)
  - Within 200% L: base refinement (wake region)
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, log2
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mesh.stl_utils import StlComplexity


@dataclass
class FlowDomain:
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    zmin: float
    zmax: float
    nx: int         # background mesh cells in x
    ny: int         # background mesh cells in y
    nz: int         # background mesh cells in z
    stl_name: str   # e.g. "geometry.stl"
    location_x: float
    location_y: float
    location_z: float
    char_length: float  # characteristic length L (for refinementRegions distances)


def build_domain(bbox, stl_filename: str, target_background_cells: int = 40_000) -> FlowDomain:
    """
    STL BBox에서 CFD 도메인과 blockMesh 해상도 계산.
    """
    L = bbox.characteristic_length
    if L <= 0:
        raise ValueError("STL bounding box has zero characteristic length — empty geometry?")

    cx, cy, cz = bbox.center_x, bbox.center_y, bbox.center_z

    xmin = cx - 10 * L
    xmax = cx + 20 * L
    ymin = cy - 5 * L
    ymax = cy + 5 * L
    zmin = cz - 5 * L
    zmax = cz + 5 * L

    dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin

    h = (dx * dy * dz / target_background_cells) ** (1 / 3)
    nx = max(4, round(dx / h))
    ny = max(4, round(dy / h))
    nz = max(4, round(dz / h))

    return FlowDomain(
        xmin=xmin, xmax=xmax,
        ymin=ymin, ymax=ymax,
        zmin=zmin, zmax=zmax,
        nx=nx, ny=ny, nz=nz,
        stl_name=stl_filename,
        location_x=cx - 8 * L,
        location_y=cy + 0.1 * L,
        location_z=cz + 0.1 * L,
        char_length=L,
    )


def block_mesh_dict(domain: FlowDomain) -> str:
    d = domain
    return f"""\
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}}

scale 1;

vertices
(
    ( {d.xmin:.6g}  {d.ymin:.6g}  {d.zmin:.6g} )  // 0
    ( {d.xmax:.6g}  {d.ymin:.6g}  {d.zmin:.6g} )  // 1
    ( {d.xmax:.6g}  {d.ymax:.6g}  {d.zmin:.6g} )  // 2
    ( {d.xmin:.6g}  {d.ymax:.6g}  {d.zmin:.6g} )  // 3
    ( {d.xmin:.6g}  {d.ymin:.6g}  {d.zmax:.6g} )  // 4
    ( {d.xmax:.6g}  {d.ymin:.6g}  {d.zmax:.6g} )  // 5
    ( {d.xmax:.6g}  {d.ymax:.6g}  {d.zmax:.6g} )  // 6
    ( {d.xmin:.6g}  {d.ymax:.6g}  {d.zmax:.6g} )  // 7
);

blocks
(
    hex (0 1 2 3 4 5 6 7) ({d.nx} {d.ny} {d.nz}) simpleGrading (1 1 1)
);

boundary
(
    inlet
    {{
        type patch;
        faces ( (0 4 7 3) );
    }}
    outlet
    {{
        type patch;
        faces ( (1 2 6 5) );
    }}
    sides
    {{
        type symmetryPlane;
        faces
        (
            (0 1 5 4)
            (3 7 6 2)
            (0 3 2 1)
            (4 5 6 7)
        );
    }}
);
"""


def surface_feature_extract_dict(stl_name: str, complexity: StlComplexity | None = None) -> str:
    """
    surfaceFeatureExtractDict 생성.

    complexity가 있으면 STL 복잡도에 따라 includedAngle 자동 조정:
      복잡한 geometry → 낮은 includedAngle (더 많은 feature edge 캡처)
      단순한 geometry → 높은 includedAngle (주요 feature만 캡처)
    """
    stem = stl_name.rsplit(".", 1)[0]

    if complexity is not None:
        # resolveFeatureAngle이 작을수록 세밀한 feature 캡처
        # includedAngle = 180 - resolve_feature_angle
        included_angle = int(180 - complexity.resolve_feature_angle)
    else:
        included_angle = 150  # 기본값: 30° sharpness threshold

    return f"""\
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      surfaceFeatureExtractDict;
}}

{stl_name}
{{
    extractionMethod    extractFromSurface;
    extractFromSurfaceCoeffs
    {{
        includedAngle   {included_angle};
    }}
    writeObj    yes;
}}
"""


def snappy_hex_mesh_dict(
    domain: FlowDomain,
    complexity: StlComplexity | None = None,
    params=None,  # MeshParams | None
) -> str:
    """
    snappyHexMeshDict 생성.

    complexity (StlComplexity)가 전달되면 곡률 기반 적응형 정밀화 적용:
      - refinementSurfaces: geometry 표면 min/max 레벨 자동 설정
      - refinementRegions: geometry와의 거리별 체적 정밀화 자동 생성
        · 0.1L 이내:  최대 정밀화 (near-wall, 경계층)
        · 0.5L 이내:  중간 정밀화
        · 2.0L 이내:  기본 정밀화 (후류 영역)
      - resolveFeatureAngle: STL feature angle에 맞게 자동 조정
      - addLayersControls: 복잡도에 따라 경계층 레이어 수 조정
    """
    from mesh.params import MeshParams
    mp: MeshParams = params if params is not None else MeshParams()

    d = domain
    stem = d.stl_name.rsplit(".", 1)[0]
    L = d.char_length

    if complexity is not None:
        s_min = complexity.surface_refine_min
        s_max = complexity.surface_refine_max
        feat_level = complexity.feature_refine_level
        feat_angle = complexity.resolve_feature_angle
        n_layers_auto = 3 if complexity.complexity_ratio < 3 else 5
    else:
        s_min, s_max, feat_level = 1, 3, 3
        feat_angle = 30.0
        n_layers_auto = 3

    # Pro-mode overrides (take precedence over auto values)
    if mp.snappy_refine_min is not None:
        s_min = mp.snappy_refine_min
    if mp.snappy_refine_max is not None:
        s_max = max(s_min, mp.snappy_refine_max)
    n_layers = mp.snappy_n_layers if mp.snappy_n_layers is not None else n_layers_auto
    expansion_ratio = mp.snappy_expansion_ratio
    final_layer_thickness = mp.snappy_final_layer_thickness
    max_non_ortho = mp.snappy_max_non_ortho

    # 거리 기반 정밀화 영역 (complexity에 따라 레벨 조정)
    near_dist = L * 0.10
    mid_dist  = L * 0.50
    wake_dist = L * 2.00
    near_level = s_max + 1
    mid_level  = s_max
    wake_level = max(s_min, s_max - 1)

    refinement_regions = f"""\
        {stem}
        {{
            mode distance;
            levels
            (
                ( {near_dist:.6g}  {near_level} )
                ( {mid_dist:.6g}   {mid_level}  )
                ( {wake_dist:.6g}  {wake_level} )
            );
        }}"""

    max_non_ortho_relaxed = min(85, max_non_ortho + 5)

    return f"""\
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      snappyHexMeshDict;
}}

castellatedMesh true;
snap            true;
addLayers       true;

geometry
{{
    {d.stl_name}
    {{
        type triSurfaceMesh;
        name {stem};
    }}
}};

castellatedMeshControls
{{
    maxLocalCells       1000000;
    maxGlobalCells      4000000;
    minRefinementCells  10;
    maxLoadUnbalance    0.10;
    nCellsBetweenLevels 3;

    features
    (
        {{
            file "{stem}.eMesh";
            level {feat_level};
        }}
    );

    refinementSurfaces
    {{
        {stem}
        {{
            level ( {s_min} {s_max} );
        }}
    }};

    resolveFeatureAngle {feat_angle:.1f};

    refinementRegions
    {{
{refinement_regions}
    }}

    locationInMesh ( {d.location_x:.6g} {d.location_y:.6g} {d.location_z:.6g} );
    allowFreeStandingZoneFaces true;
}};

snapControls
{{
    nSmoothPatch        3;
    tolerance           2.0;
    nSolveIter          100;
    nRelaxIter          5;
    nFeatureSnapIter    10;
    implicitFeatureSnap false;
    explicitFeatureSnap true;
    multiRegionFeatureSnap false;
}};

addLayersControls
{{
    relativeSizes       true;
    layers
    {{
        {stem}
        {{
            nSurfaceLayers  {n_layers};
        }}
    }}
    expansionRatio          {expansion_ratio:.3g};
    finalLayerThickness     {final_layer_thickness:.3g};
    minThickness            0.1;
    nGrow                   0;
    featureAngle            60;
    slipFeatureAngle        30;
    nRelaxIter              3;
    nSmoothSurfaceNormals   1;
    nSmoothNormals          3;
    nSmoothThickness        10;
    maxFaceThicknessRatio   0.5;
    maxThicknessToMedialRatio 0.3;
    minMedialAxisAngle      90;
    nBufferCellsNoExtrude   0;
    nLayerIter              50;
}};

meshQualityControls
{{
    maxNonOrtho             {max_non_ortho:.0f};
    maxBoundarySkewness     20;
    maxInternalSkewness     4;
    maxConcave              80;
    minVol                  1e-13;
    minTetQuality           1e-15;
    minArea                 -1;
    minTwist                0.02;
    minDeterminant          0.001;
    minFaceWeight           0.02;
    minVolRatio             0.01;
    minTriangleTwist        -1;
    nSmoothScale            4;
    errorReduction          0.75;
    relaxed
    {{
        maxNonOrtho {max_non_ortho_relaxed:.0f};
    }}
}};

debug 0;
mergeTolerance 1e-6;
"""


def control_dict(end_time: int = 0) -> str:
    return f"""\
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      controlDict;
}}

application     simpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {end_time};
deltaT          1;
writeControl    timeStep;
writeInterval   100;
purgeWrite      0;
writeFormat     ascii;
writePrecision  6;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;
"""


def fv_schemes() -> str:
    return """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSchemes;
}

ddtSchemes      { default steadyState; }
gradSchemes     { default Gauss linear; }
divSchemes      { default none; div(phi,U) Gauss limitedLinearV 1; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes   { default corrected; }
"""


def fv_solution() -> str:
    return """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSolution;
}

solvers
{
    p    { solver GAMG; smoother GaussSeidel; tolerance 1e-7; relTol 0.01; }
    U    { solver smoothSolver; smoother GaussSeidel; tolerance 1e-8; relTol 0.1; }
    k    { solver smoothSolver; smoother GaussSeidel; tolerance 1e-8; relTol 0.1; }
    omega { solver smoothSolver; smoother GaussSeidel; tolerance 1e-8; relTol 0.1; }
}

SIMPLE
{
    nNonOrthogonalCorrectors 2;
    consistent yes;
}
"""
