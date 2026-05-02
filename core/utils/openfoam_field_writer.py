"""C / beta2802 — OpenFOAM 0/ field 파일 자동 생성.

BCManager 의 patch 별 BC type + values → OpenFOAM 0/U, 0/p, 0/T, 0/k, 0/epsilon 등
field dictionary 파일 생성. solver (simpleFoam/icoFoam/buoyantFoam) 즉시 실행 가능.

Field type 매핑:
    velocity       → 0/U  (volVectorField, m/s)
    pressure       → 0/p  (volScalarField, Pa)
    temperature    → 0/T  (volScalarField, K)
    k              → 0/k  (volScalarField, m^2/s^2)
    epsilon        → 0/epsilon (volScalarField, m^2/s^3)
    omega          → 0/omega (volScalarField, 1/s)
    htc            → 0/T (with externalWallHeatFluxTemperature)

BC type → OpenFOAM patch type 변환표:
    wall              → fixedValue / noSlip
    velocity_inlet    → fixedValue (uniform velocity)
    pressure_outlet   → zeroGradient (U) + fixedValue (p)
    outflow           → zeroGradient
    symmetry          → symmetryPlane
    periodic          → cyclic
    cyclic_ami        → cyclicAMI
    fan               → fan
    porous_jump       → porousJump
    sliding_mesh      → movingWallVelocity
    interface_heat    → externalWallHeatFluxTemperature
    mass_flow_inlet   → flowRateInletVelocity
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class FieldWriteResult:
    success: bool = False
    n_fields_written: int = 0
    field_paths: list[str] = None
    message: str = ""

    def __post_init__(self):
        if self.field_paths is None:
            self.field_paths = []


# OpenFOAM file header.
_HEADER = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2406                                 |
|   \\\\  /    A nd           | Web:      www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       {field_class};
    location    "0";
    object      {field_name};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      {dimensions};

internalField   {internal};

boundaryField
{{
"""

_FOOTER = """}}


// ************************************************************************* //
"""


# OpenFOAM dimensions [kg m s K mol A cd].
_FIELD_DIMS = {
    "U":       "[0 1 -1 0 0 0 0]",        # m/s
    "p":       "[0 2 -2 0 0 0 0]",        # m^2/s^2 (kinematic pressure)
    "p_rgh":   "[0 2 -2 0 0 0 0]",
    "T":       "[0 0 0 1 0 0 0]",         # K
    "k":       "[0 2 -2 0 0 0 0]",        # m^2/s^2
    "epsilon": "[0 2 -3 0 0 0 0]",        # m^2/s^3
    "omega":   "[0 0 -1 0 0 0 0]",        # 1/s
    "nut":     "[0 2 -1 0 0 0 0]",        # m^2/s
}

# field name → OpenFOAM class.
_FIELD_CLASS = {
    "U":       "volVectorField",
    "p":       "volScalarField",
    "p_rgh":   "volScalarField",
    "T":       "volScalarField",
    "k":       "volScalarField",
    "epsilon": "volScalarField",
    "omega":   "volScalarField",
    "nut":     "volScalarField",
}

# default internal value (uniform).
_FIELD_INTERNAL_DEFAULT = {
    "U":       "uniform (0 0 0)",
    "p":       "uniform 0",
    "p_rgh":   "uniform 0",
    "T":       "uniform 300",
    "k":       "uniform 0.01",
    "epsilon": "uniform 0.01",
    "omega":   "uniform 1.0",
    "nut":     "uniform 0",
}


def _format_vector(v) -> str:
    """[1, 0, 0] → '(1 0 0)'"""
    if hasattr(v, "tolist"):
        v = v.tolist()
    if isinstance(v, (list, tuple)) and len(v) == 3:
        return f"({float(v[0])} {float(v[1])} {float(v[2])})"
    return f"({v})"


def _bc_to_patch_dict(field_name: str, ba) -> str:
    """단일 patch 의 boundaryField entry 생성.

    Args:
        field_name: 'U' / 'p' / 'T' / etc.
        ba: BCAssignment.

    Returns:
        '    name { type ...; value ...; }\n' 형식 string.
    """
    bc_type = ba.bc_type
    vals = ba.values or {}

    # field 별 patch type 결정.
    if field_name == "U":
        if bc_type in ("wall", "moving_wall"):
            v = vals.get("velocity", [0, 0, 0])
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            fixedValue;\n"
                f"        value           uniform {_format_vector(v)};\n"
                f"    }}\n"
            )
        elif bc_type in ("velocity_inlet", "inlet"):
            v = vals.get("velocity", [1, 0, 0])
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            fixedValue;\n"
                f"        value           uniform {_format_vector(v)};\n"
                f"    }}\n"
            )
        elif bc_type in ("outlet", "outflow", "pressure_outlet"):
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            zeroGradient;\n"
                f"    }}\n"
            )
        elif bc_type == "symmetry":
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            symmetryPlane;\n"
                f"    }}\n"
            )
        elif bc_type in ("periodic", "cyclic_ami"):
            patch_t = "cyclic" if bc_type == "periodic" else "cyclicAMI"
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            {patch_t};\n"
                f"    }}\n"
            )
        elif bc_type == "mass_flow_inlet":
            mf = vals.get("mass_flow", 1.0)
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            flowRateInletVelocity;\n"
                f"        massFlowRate    constant {float(mf)};\n"
                f"        value           uniform (0 0 0);\n"
                f"    }}\n"
            )
        elif bc_type == "sliding_mesh":
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            movingWallVelocity;\n"
                f"        value           uniform (0 0 0);\n"
                f"    }}\n"
            )
        elif bc_type == "fan":
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            cyclic;\n"
                f"    }}\n"
            )
        elif bc_type == "porous_jump":
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            cyclic;\n"
                f"    }}\n"
            )
        elif bc_type == "empty":
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            empty;\n"
                f"    }}\n"
            )
        else:  # wedge, interface, etc.
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            {bc_type};\n"
                f"    }}\n"
            )

    elif field_name in ("p", "p_rgh"):
        if bc_type in ("outlet", "pressure_outlet"):
            p = vals.get("pressure", 0.0)
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            fixedValue;\n"
                f"        value           uniform {float(p)};\n"
                f"    }}\n"
            )
        elif bc_type in ("wall", "moving_wall", "inlet", "velocity_inlet",
                         "mass_flow_inlet", "outflow"):
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            zeroGradient;\n"
                f"    }}\n"
            )
        elif bc_type == "symmetry":
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            symmetryPlane;\n"
                f"    }}\n"
            )
        elif bc_type in ("periodic", "cyclic_ami"):
            patch_t = "cyclic" if bc_type == "periodic" else "cyclicAMI"
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            {patch_t};\n"
                f"    }}\n"
            )
        elif bc_type == "fan":
            jp = vals.get("pressure_jump", 100.0)
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            fan;\n"
                f"        patchType       cyclic;\n"
                f"        jumpTable       table ((0 {float(jp)}));\n"
                f"        value           uniform 0;\n"
                f"    }}\n"
            )
        elif bc_type == "porous_jump":
            r = vals.get("resistance", 1e6)
            t = vals.get("thickness", 0.001)
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            porousJump;\n"
                f"        patchType       cyclic;\n"
                f"        D               {float(r)};\n"
                f"        I               0;\n"
                f"        L               {float(t)};\n"
                f"        value           uniform 0;\n"
                f"    }}\n"
            )
        elif bc_type == "empty":
            entry = (
                f"    {ba.name}\n    {{\n        type            empty;\n    }}\n"
            )
        else:
            entry = (
                f"    {ba.name}\n    {{\n        type            zeroGradient;\n    }}\n"
            )

    elif field_name == "T":
        if bc_type == "interface_heat":
            htc = vals.get("htc", 1000.0)
            t_ext = vals.get("T_ext", 300.0)
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            externalWallHeatFluxTemperature;\n"
                f"        mode            coefficient;\n"
                f"        h               uniform {float(htc)};\n"
                f"        Ta              uniform {float(t_ext)};\n"
                f"        value           uniform {float(t_ext)};\n"
                f"    }}\n"
            )
        elif "temperature" in vals:
            entry = (
                f"    {ba.name}\n    {{\n"
                f"        type            fixedValue;\n"
                f"        value           uniform {float(vals['temperature'])};\n"
                f"    }}\n"
            )
        elif bc_type == "symmetry":
            entry = (
                f"    {ba.name}\n    {{\n        type            symmetryPlane;\n    }}\n"
            )
        elif bc_type in ("periodic", "cyclic_ami"):
            patch_t = "cyclic" if bc_type == "periodic" else "cyclicAMI"
            entry = (
                f"    {ba.name}\n    {{\n        type            {patch_t};\n    }}\n"
            )
        elif bc_type == "empty":
            entry = (
                f"    {ba.name}\n    {{\n        type            empty;\n    }}\n"
            )
        else:
            entry = (
                f"    {ba.name}\n    {{\n        type            zeroGradient;\n    }}\n"
            )

    else:
        # generic fallback: zeroGradient.
        entry = (
            f"    {ba.name}\n    {{\n        type            zeroGradient;\n    }}\n"
        )

    return entry


def write_openfoam_field(
    case_dir: str | Path,
    field_name: str,
    bc_manager,
    *,
    internal_value=None,
) -> bool:
    """단일 OpenFOAM 0/<field> 파일 생성.

    Args:
        case_dir: case directory (0/ subdir 자동 생성).
        field_name: 'U' / 'p' / 'T' / etc.
        bc_manager: BCManager.
        internal_value: optional override (string).

    Returns:
        성공 여부.
    """
    case_path = Path(case_dir)
    zero_dir = case_path / "0"
    zero_dir.mkdir(parents=True, exist_ok=True)
    out_path = zero_dir / field_name

    fclass = _FIELD_CLASS.get(field_name, "volScalarField")
    dims = _FIELD_DIMS.get(field_name, "[0 0 0 0 0 0 0]")
    internal = (
        internal_value if internal_value is not None
        else _FIELD_INTERNAL_DEFAULT.get(field_name, "uniform 0")
    )

    try:
        head = _HEADER.format(
            field_class=fclass, field_name=field_name,
            dimensions=dims, internal=internal,
        )
        body_parts = []
        for ba in bc_manager.assignments:
            body_parts.append(_bc_to_patch_dict(field_name, ba))
        out_path.write_text(head + "".join(body_parts) + _FOOTER.format())
        return True
    except Exception:
        return False


def write_openfoam_fields(
    case_dir: str | Path,
    bc_manager,
    *,
    fields: tuple = ("U", "p"),
    include_turbulence: bool = False,
    include_temperature: bool = False,
) -> FieldWriteResult:
    """multi-field 자동 생성.

    Args:
        case_dir: case directory.
        bc_manager: BCManager.
        fields: 기본 ('U', 'p').
        include_turbulence: True 면 k, epsilon, omega, nut 포함.
        include_temperature: True 면 T 포함.

    Returns:
        FieldWriteResult.
    """
    case_path = Path(case_dir)
    res = FieldWriteResult()
    fields_to_write = list(fields)
    if include_turbulence:
        fields_to_write.extend(["k", "epsilon", "omega", "nut"])
    if include_temperature:
        fields_to_write.append("T")
    fields_to_write = list(dict.fromkeys(fields_to_write))   # dedupe.

    for fname in fields_to_write:
        if write_openfoam_field(case_path, fname, bc_manager):
            res.field_paths.append(str(case_path / "0" / fname))
            res.n_fields_written += 1

    res.success = res.n_fields_written > 0
    res.message = (
        f"wrote {res.n_fields_written} field(s) to {case_path / '0'}"
    )
    return res
