"""
Auto-generate OpenFOAM configuration files for snappyHexMesh external-flow meshing.

Domain layout (external aerodynamics, flow in +x direction):
  x:  center - 10L  →  center + 20L   (upstream 10L, downstream 20L)
  y:  center - 5L   →  center + 5L
  z:  center - 5L   →  center + 5L

where L = characteristic_length (longest bbox dimension).
"""

from dataclasses import dataclass
from math import ceil, log2


@dataclass
class FlowDomain:
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    zmin: float
    zmax: float
    nx: int       # background mesh cells in x
    ny: int       # background mesh cells in y
    nz: int       # background mesh cells in z
    stl_name: str  # e.g. "geometry.stl" (filename only)
    # A point guaranteed to be in the flow region (outside the geometry)
    location_x: float
    location_y: float
    location_z: float


def build_domain(bbox, stl_filename: str, target_background_cells: int = 40_000) -> FlowDomain:
    """
    Calculate the CFD domain and background mesh resolution from the geometry bounding box.

    target_background_cells controls the coarseness of the blockMesh hex grid.
    snappyHexMesh will then refine this grid near the surface.
    """
    L = bbox.characteristic_length
    if L == 0:
        raise ValueError("STL bounding box has zero characteristic length — empty geometry?")

    cx, cy, cz = bbox.center_x, bbox.center_y, bbox.center_z

    xmin = cx - 10 * L
    xmax = cx + 20 * L
    ymin = cy - 5 * L
    ymax = cy + 5 * L
    zmin = cz - 5 * L
    zmax = cz + 5 * L

    dx = xmax - xmin  # 30L
    dy = ymax - ymin  # 10L
    dz = zmax - zmin  # 10L

    # Target cell size so total cells ≈ target_background_cells
    # dx/h * dy/h * dz/h = N  →  h = (dx*dy*dz / N)^(1/3)
    h = (dx * dy * dz / target_background_cells) ** (1 / 3)

    nx = max(4, round(dx / h))
    ny = max(4, round(dy / h))
    nz = max(4, round(dz / h))

    # The "locationInMesh" must be OUTSIDE the geometry.
    # Place it upstream and slightly off-center.
    loc_x = cx - 8 * L   # far upstream
    loc_y = cy + 0.1 * L  # slightly off axis to avoid degenerate cases
    loc_z = cz + 0.1 * L

    return FlowDomain(
        xmin=xmin, xmax=xmax,
        ymin=ymin, ymax=ymax,
        zmin=zmin, zmax=zmax,
        nx=nx, ny=ny, nz=nz,
        stl_name=stl_filename,
        location_x=loc_x,
        location_y=loc_y,
        location_z=loc_z,
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


def surface_feature_extract_dict(stl_name: str) -> str:
    stem = stl_name.rsplit(".", 1)[0]
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
        includedAngle   150;
    }}
    writeObj    yes;
}}
"""


def snappy_hex_mesh_dict(domain: FlowDomain, refinement_level: int = 2) -> str:
    """
    Generate snappyHexMeshDict for external flow meshing.

    refinement_level controls surface refinement:
      1 → coarse  (2× background cell size)
      2 → medium  (4× background cell size)  ← default
      3 → fine    (8× background cell size)
    """
    d = domain
    stem = d.stl_name.rsplit(".", 1)[0]
    rl = refinement_level
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
            level {rl};
        }}
    );

    refinementSurfaces
    {{
        {stem}
        {{
            level ( {rl} {rl} );
        }}
    }};

    resolveFeatureAngle 30;

    refinementRegions
    {{
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
            nSurfaceLayers  3;
        }}
    }}
    expansionRatio          1.2;
    finalLayerThickness     0.3;
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
    maxNonOrtho             70;
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
        maxNonOrtho 75;
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
