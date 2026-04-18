"""OpenFOAM case 템플릿 생성 — system/controlDict, fvSchemes, fvSolution.

파이프라인이 polyMesh만 생성하므로 바로 solver 실행하려면 system/ 디렉토리와
initial condition(0/)이 필요. 이 모듈은 범용 incompressible steady-state 시작점을 제공.
"""
from __future__ import annotations

from pathlib import Path

# OpenFOAM 2406 표준 헤더
_FOAM_HEADER = """\
/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM                                        |
|  \\\\    /   O peration     | AutoTessell generated                           |
|   \\\\  /    A nd           |                                                 |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
"""

_CONTROLDICT = _FOAM_HEADER + """\
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      controlDict;
}}

application     simpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         1000;
deltaT          1;
writeControl    runTime;
writeInterval   100;
purgeWrite      0;
writeFormat     binary;
writePrecision  6;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;

functions
{{
    #include "streamlines"
    #include "residuals"
}}
"""

_FVSCHEMES = _FOAM_HEADER + """\
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSchemes;
}}

ddtSchemes       {{ default  steadyState; }}

gradSchemes      {{ default  Gauss linear; }}

divSchemes
{{
    default         none;
    div(phi,U)      bounded Gauss linearUpwind grad(U);
    div(phi,k)      bounded Gauss upwind;
    div(phi,omega)  bounded Gauss upwind;
    div(phi,epsilon) bounded Gauss upwind;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}}

laplacianSchemes {{ default  Gauss linear corrected; }}

interpolationSchemes {{ default  linear; }}

snGradSchemes    {{ default  corrected; }}

wallDist {{ method meshWave; }}
"""

_FVSOLUTION = _FOAM_HEADER + """\
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSolution;
}}

solvers
{{
    p
    {{
        solver          GAMG;
        tolerance       1e-7;
        relTol          0.01;
        smoother        GaussSeidel;
    }}

    "(U|k|omega|epsilon)"
    {{
        solver          smoothSolver;
        smoother        GaussSeidel;
        tolerance       1e-8;
        relTol          0.1;
        nSweeps         1;
    }}
}}

SIMPLE
{{
    nNonOrthogonalCorrectors 0;
    consistent       yes;
    residualControl
    {{
        p               1e-4;
        U               1e-4;
        "(k|omega|epsilon)" 1e-4;
    }}
}}

relaxationFactors
{{
    equations
    {{
        U               0.9;
        "(k|omega|epsilon)" 0.7;
    }}
    fields
    {{
        p               0.3;
    }}
}}
"""

_STREAMLINES_INC = """\
streamlines
{
    type            streamLine;
    libs            ("liblagrangian.so");
    writeControl    writeTime;
    setFormat       vtk;
    trackingMethod  stationary;
    U               U;
    fields          (U p);
    lifeTime        10000;
    nSubCycle       5;
    cloudName       particleTracks;
    seedSampleSet   uniform;
    uniformCoeffs
    {
        type        uniform;
        axis        x;
        start       (0 0 0.5);
        end         (0 0 0.5);
        nPoints     20;
    }
}
"""

_RESIDUALS_INC = """\
residuals
{
    type            residuals;
    libs            ("libutilityFunctionObjects.so");
    writeControl    timeStep;
    writeInterval   1;
    fields          (p U k omega epsilon);
}
"""


def write_case_template(case_dir: Path) -> list[str]:
    """case_dir (= polyMesh 상위) 에 system/ 템플릿 작성. 쓴 파일 경로 목록 반환.

    기존 파일은 덮어쓰지 않는다 (사용자가 수정했을 수 있음).
    """
    case_dir = Path(case_dir)
    system = case_dir / "system"
    system.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    files = [
        ("controlDict", _CONTROLDICT),
        ("fvSchemes", _FVSCHEMES),
        ("fvSolution", _FVSOLUTION),
        ("streamlines", _STREAMLINES_INC),
        ("residuals", _RESIDUALS_INC),
    ]
    for name, content in files:
        path = system / name
        if path.exists():
            continue  # 사용자 편집 보호
        path.write_text(content, encoding="utf-8")
        written.append(str(path))

    # 0/ 초기조건 디렉토리도 주석 README 정도 생성
    zero = case_dir / "0.orig"
    zero.mkdir(parents=True, exist_ok=True)
    readme = zero / "README.txt"
    if not readme.exists():
        readme.write_text(
            "이 디렉토리는 AutoTessell이 만든 플레이스홀더입니다.\n"
            "solver 실행 전에 경계조건 파일(p, U, k, omega 등)을 여기에 추가하세요.\n"
            "그 후 'cp -r 0.orig 0' 으로 초기조건 복사 후 simpleFoam 실행.\n",
            encoding="utf-8",
        )
        written.append(str(readme))

    return written
