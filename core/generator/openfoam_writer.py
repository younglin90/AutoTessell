"""OpenFOAM polyMesh 및 Dict 파일 생성 유틸리티."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.utils.logging import get_logger

logger = get_logger(__name__)

# OpenFOAM FoamFile 헤더 템플릿
_FOAM_HEADER = """\
/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     |
    \\\\  /    A nd           | Version: 13
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       {foam_class};
    location    "{location}";
    object      {object_name};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

"""


def _foam_header(
    foam_class: str,
    location: str,
    object_name: str,
) -> str:
    return _FOAM_HEADER.format(
        foam_class=foam_class,
        location=location,
        object_name=object_name,
    )


class OpenFOAMWriter:
    """OpenFOAM 케이스 디렉터리 구조와 설정 파일을 생성하는 클래스."""

    # ------------------------------------------------------------------
    # 디렉터리 구조
    # ------------------------------------------------------------------

    def ensure_case_structure(self, case_dir: Path) -> None:
        """케이스 디렉터리의 필수 하위 디렉터리를 생성한다.

        생성 디렉터리:
            - constant/polyMesh/
            - constant/triSurface/
            - system/
        """
        dirs = [
            case_dir / "constant" / "polyMesh",
            case_dir / "constant" / "triSurface",
            case_dir / "system",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
            logger.debug("ensure_dir", path=str(d))

        logger.info("case_structure_created", case_dir=str(case_dir))

    # ------------------------------------------------------------------
    # system/ 파일
    # ------------------------------------------------------------------

    def write_control_dict(
        self,
        case_dir: Path,
        application: str = "simpleFoam",
    ) -> None:
        """system/controlDict 파일을 작성한다."""
        header = _foam_header(
            foam_class="dictionary",
            location="system",
            object_name="controlDict",
        )
        body = f"""\
application     {application};

startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         1000;
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

// ************************************************************************* //
"""
        out_path = case_dir / "system" / "controlDict"
        out_path.write_text(header + body)
        logger.info("wrote_control_dict", path=str(out_path), application=application)

    def write_fv_schemes(self, case_dir: Path) -> None:
        """system/fvSchemes 파일을 작성한다."""
        header = _foam_header(
            foam_class="dictionary",
            location="system",
            object_name="fvSchemes",
        )
        body = """\
ddtSchemes
{
    default         steadyState;
}

gradSchemes
{
    default         Gauss linear;
}

divSchemes
{
    default         none;
    div(phi,U)      bounded Gauss linearUpwind grad(U);
    div(phi,k)      bounded Gauss upwind;
    div(phi,omega)  bounded Gauss upwind;
    "div((nuEff*dev2(T(grad(U)))))" Gauss linear;
}

laplacianSchemes
{
    default         Gauss linear corrected;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         corrected;
}

wallDist
{
    method          meshWave;
}

// ************************************************************************* //
"""
        out_path = case_dir / "system" / "fvSchemes"
        out_path.write_text(header + body)
        logger.info("wrote_fv_schemes", path=str(out_path))

    def write_fv_solution(self, case_dir: Path) -> None:
        """system/fvSolution 파일을 작성한다."""
        header = _foam_header(
            foam_class="dictionary",
            location="system",
            object_name="fvSolution",
        )
        body = """\
solvers
{
    p
    {
        solver          GAMG;
        tolerance       1e-06;
        relTol          0.1;
        smoother        GaussSeidel;
    }
    U
    {
        solver          smoothSolver;
        smoother        GaussSeidel;
        tolerance       1e-06;
        relTol          0.1;
    }
    k
    {
        solver          smoothSolver;
        smoother        GaussSeidel;
        tolerance       1e-06;
        relTol          0.1;
    }
    omega
    {
        solver          smoothSolver;
        smoother        GaussSeidel;
        tolerance       1e-06;
        relTol          0.1;
    }
}

SIMPLE
{
    nNonOrthogonalCorrectors 1;
    consistent      yes;
    pRefCell        0;
    pRefValue       0;

    residualControl
    {
        p               1e-4;
        U               1e-4;
        k               1e-4;
        omega           1e-4;
    }
}

relaxationFactors
{
    fields
    {
        p               0.3;
    }
    equations
    {
        U               0.7;
        k               0.7;
        omega           0.7;
    }
}

// ************************************************************************* //
"""
        out_path = case_dir / "system" / "fvSolution"
        out_path.write_text(header + body)
        logger.info("wrote_fv_solution", path=str(out_path))

    # ------------------------------------------------------------------
    # Dict 직렬화
    # ------------------------------------------------------------------

    def write_foam_dict(
        self,
        path: Path,
        data: dict[str, Any],
        foam_class: str = "dictionary",
        location: str = "system",
        object_name: str | None = None,
    ) -> None:
        """Python dict를 OpenFOAM Dict 형식으로 직렬화하여 파일에 쓴다."""
        if object_name is None:
            object_name = path.name

        header = _foam_header(
            foam_class=foam_class,
            location=location,
            object_name=object_name,
        )
        body = self._dict_to_foam(data, indent=0)
        footer = "\n// ************************************************************************* //\n"
        path.write_text(header + body + footer)
        logger.info("wrote_foam_dict", path=str(path))

    def _dict_to_foam(self, data: dict[str, Any] | list[Any] | str | int | float | bool, indent: int = 0) -> str:
        """Python データ構造をOpenFOAM形式にシリアライズする。"""
        pad = "    " * indent
        "    " * (indent + 1)

        if isinstance(data, dict):
            lines = []
            for key, value in data.items():
                if isinstance(value, dict):
                    lines.append(f"{pad}{key}")
                    lines.append(f"{pad}{{")
                    lines.append(self._dict_to_foam(value, indent + 1))
                    lines.append(f"{pad}}}")
                elif isinstance(value, list):
                    rendered = " ".join(str(v) for v in value)
                    lines.append(f"{pad}{key}    ({rendered});")
                else:
                    lines.append(f"{pad}{key}    {value};")
            return "\n".join(lines) + "\n"
        elif isinstance(data, list):
            rendered = " ".join(str(v) for v in data)
            return f"{pad}({rendered})\n"
        else:
            return f"{pad}{data}\n"
