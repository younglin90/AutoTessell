"""OpenFOAM 경계 조건(BC) 자동 생성기.

boundary_classifier의 분류 결과를 기반으로 0/ 디렉터리에
p, U, k, omega, nut 등의 초기/경계 조건 파일을 생성한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.utils.logging import get_logger

log = get_logger(__name__)

_FOAM_HEADER = """\
FoamFile
{{
    version     2.0;
    format      ascii;
    class       {foam_class};
    object      {object_name};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

"""


def write_boundary_conditions(
    case_dir: Path,
    patches: list[dict[str, Any]],
    flow_velocity: float = 1.0,
    turbulence_model: str = "kOmegaSST",
) -> list[str]:
    """경계 조건 파일을 생성한다.

    Args:
        case_dir: OpenFOAM case 디렉터리.
        patches: boundary_classifier 결과 (name, type 포함).
        flow_velocity: 유입 속도 크기 [m/s].
        turbulence_model: 난류 모델 ("kOmegaSST" 또는 "kEpsilon").

    Returns:
        생성된 파일 경로 목록.
    """
    zero_dir = case_dir / "0"
    zero_dir.mkdir(parents=True, exist_ok=True)

    files_written: list[str] = []

    # p (압력)
    _write_field(zero_dir / "p", "volScalarField", "p",
                 _build_p_bc(patches), "0")
    files_written.append("0/p")

    # U (속도)
    _write_field(zero_dir / "U", "volVectorField", "U",
                 _build_U_bc(patches, flow_velocity), "(0 0 0)")
    files_written.append("0/U")

    # k (난류 운동 에너지)
    k_val = 0.5 * (0.05 * flow_velocity) ** 2 * 3  # I=5%
    _write_field(zero_dir / "k", "volScalarField", "k",
                 _build_k_bc(patches, k_val), f"{k_val:.6g}")
    files_written.append("0/k")

    # omega
    omega_val = k_val ** 0.5 / (0.09 ** 0.25 * 0.1)  # l=0.1m
    _write_field(zero_dir / "omega", "volScalarField", "omega",
                 _build_omega_bc(patches, omega_val), f"{omega_val:.6g}")
    files_written.append("0/omega")

    # nut (난류 점성)
    _write_field(zero_dir / "nut", "volScalarField", "nut",
                 _build_nut_bc(patches), "0")
    files_written.append("0/nut")

    # constant/ 설정 파일
    _write_transport_properties(case_dir)
    files_written.append("constant/transportProperties")

    _write_turbulence_properties(case_dir, turbulence_model)
    files_written.append("constant/turbulenceProperties")

    log.info("boundary_conditions_written", files=files_written)
    return files_written


def _write_transport_properties(case_dir: Path) -> None:
    """constant/transportProperties 파일 생성."""
    path = case_dir / "constant" / "transportProperties"
    path.parent.mkdir(parents=True, exist_ok=True)
    header = _FOAM_HEADER.format(foam_class="dictionary", object_name="transportProperties")
    path.write_text(
        header
        + "transportModel  Newtonian;\n\n"
        + "nu              [0 2 -1 0 0 0 0] 1e-06;\n\n"
        + "// ************************************************************************* //\n"
    )


def _write_turbulence_properties(case_dir: Path, model: str = "kOmegaSST") -> None:
    """constant/turbulenceProperties 파일 생성."""
    path = case_dir / "constant" / "turbulenceProperties"
    path.parent.mkdir(parents=True, exist_ok=True)
    header = _FOAM_HEADER.format(foam_class="dictionary", object_name="turbulenceProperties")
    path.write_text(
        header
        + "simulationType  RAS;\n\n"
        + "RAS\n{\n"
        + f"    RASModel        {model};\n"
        + "    turbulence      on;\n"
        + "    printCoeffs     on;\n"
        + "}\n\n"
        + "// ************************************************************************* //\n"
    )


_DIMENSIONS = {
    "p": "[0 2 -2 0 0 0 0]",   # m^2/s^2 (kinematic)
    "U": "[0 1 -1 0 0 0 0]",   # m/s
    "k": "[0 2 -2 0 0 0 0]",   # m^2/s^2
    "omega": "[0 0 -1 0 0 0 0]",  # 1/s
    "nut": "[0 2 -1 0 0 0 0]",   # m^2/s
}


def _write_field(
    path: Path,
    foam_class: str,
    object_name: str,
    boundary_field: str,
    internal_field: str,
) -> None:
    """OpenFOAM field 파일을 쓴다."""
    header = _FOAM_HEADER.format(foam_class=foam_class, object_name=object_name)
    dims = _DIMENSIONS.get(object_name, "[0 0 0 0 0 0 0]")
    content = (
        header
        + f"dimensions      {dims};\n\n"
        + f"internalField   uniform {internal_field};\n\n"
        + f"boundaryField\n{{\n{boundary_field}}}\n\n"
        + "// ************************************************************************* //\n"
    )
    path.write_text(content)


def _build_p_bc(patches: list[dict[str, Any]]) -> str:
    """압력 경계 조건 생성."""
    lines: list[str] = []
    for p in patches:
        name = p["name"]
        ptype = p["type"]
        if ptype == "inlet":
            lines.append(f"    {name}\n    {{\n        type    zeroGradient;\n    }}\n")
        elif ptype == "outlet":
            lines.append(f"    {name}\n    {{\n        type    fixedValue;\n        value   uniform 0;\n    }}\n")
        elif ptype in ("wall", "symmetryPlane"):
            lines.append(f"    {name}\n    {{\n        type    zeroGradient;\n    }}\n")
        else:
            lines.append(f"    {name}\n    {{\n        type    zeroGradient;\n    }}\n")
    return "".join(lines)


def _build_U_bc(patches: list[dict[str, Any]], velocity: float) -> str:
    """속도 경계 조건 생성."""
    lines: list[str] = []
    for p in patches:
        name = p["name"]
        ptype = p["type"]
        if ptype == "inlet":
            lines.append(
                f"    {name}\n    {{\n"
                f"        type    fixedValue;\n"
                f"        value   uniform ({velocity} 0 0);\n"
                f"    }}\n"
            )
        elif ptype == "outlet":
            lines.append(f"    {name}\n    {{\n        type    zeroGradient;\n    }}\n")
        elif ptype == "wall":
            lines.append(f"    {name}\n    {{\n        type    noSlip;\n    }}\n")
        elif ptype == "symmetryPlane":
            lines.append(f"    {name}\n    {{\n        type    symmetry;\n    }}\n")
        else:
            lines.append(f"    {name}\n    {{\n        type    zeroGradient;\n    }}\n")
    return "".join(lines)


def _build_k_bc(patches: list[dict[str, Any]], k_val: float) -> str:
    """k 경계 조건 생성."""
    lines: list[str] = []
    for p in patches:
        name = p["name"]
        ptype = p["type"]
        if ptype == "inlet":
            lines.append(
                f"    {name}\n    {{\n"
                f"        type    fixedValue;\n"
                f"        value   uniform {k_val:.6g};\n"
                f"    }}\n"
            )
        elif ptype == "outlet":
            lines.append(f"    {name}\n    {{\n        type    zeroGradient;\n    }}\n")
        elif ptype == "wall":
            lines.append(
                f"    {name}\n    {{\n"
                f"        type    kqRWallFunction;\n"
                f"        value   uniform {k_val:.6g};\n"
                f"    }}\n"
            )
        else:
            lines.append(f"    {name}\n    {{\n        type    zeroGradient;\n    }}\n")
    return "".join(lines)


def _build_omega_bc(patches: list[dict[str, Any]], omega_val: float) -> str:
    """omega 경계 조건 생성."""
    lines: list[str] = []
    for p in patches:
        name = p["name"]
        ptype = p["type"]
        if ptype == "inlet":
            lines.append(
                f"    {name}\n    {{\n"
                f"        type    fixedValue;\n"
                f"        value   uniform {omega_val:.6g};\n"
                f"    }}\n"
            )
        elif ptype == "outlet":
            lines.append(f"    {name}\n    {{\n        type    zeroGradient;\n    }}\n")
        elif ptype == "wall":
            lines.append(
                f"    {name}\n    {{\n"
                f"        type    omegaWallFunction;\n"
                f"        value   uniform {omega_val:.6g};\n"
                f"    }}\n"
            )
        else:
            lines.append(f"    {name}\n    {{\n        type    zeroGradient;\n    }}\n")
    return "".join(lines)


def _build_nut_bc(patches: list[dict[str, Any]]) -> str:
    """nut 경계 조건 생성."""
    lines: list[str] = []
    for p in patches:
        name = p["name"]
        ptype = p["type"]
        if ptype == "wall":
            lines.append(
                f"    {name}\n    {{\n"
                f"        type    nutkWallFunction;\n"
                f"        value   uniform 0;\n"
                f"    }}\n"
            )
        else:
            lines.append(
                f"    {name}\n    {{\n"
                f"        type    calculated;\n"
                f"        value   uniform 0;\n"
                f"    }}\n"
            )
    return "".join(lines)
