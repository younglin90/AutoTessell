"""OpenFOAM 케이스 디렉터리 자동 생성기.

foamlib를 사용하여 메쉬 생성 후 즉시 실행 가능한 OpenFOAM 케이스를 만든다.

foamlib는 단순 key-value 딕셔너리 파일(controlDict, transportProperties 등)에
사용하고, 복잡한 다중 단어 스킴(fvSchemes, fvSolution)과 0/ 필드 파일은
수동 문자열 쓰기 방식을 사용한다.

foamlib import 실패 시 전체 파일을 수동 쓰기로 fallback한다.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from core.utils.logging import get_logger

log = get_logger(__name__)

# foamlib import 시도
try:
    from foamlib import FoamFile as _FoamFile

    _FOAMLIB_AVAILABLE = True
except ImportError:  # pragma: no cover
    _FOAMLIB_AVAILABLE = False
    _FoamFile = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# OpenFOAM 파일 헤더/풋터
# ---------------------------------------------------------------------------

_HEADER = """\
FoamFile
{{
    version     2.0;
    format      ascii;
    class       {cls};
    object      {obj};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

"""

_FOOTER = "\n// ************************************************************************* //\n"

_DIMENSIONS = {
    "p": "[0 2 -2 0 0 0 0]",
    "U": "[0 1 -1 0 0 0 0]",
    "k": "[0 2 -2 0 0 0 0]",
    "epsilon": "[0 2 -3 0 0 0 0]",
    "omega": "[0 0 -1 0 0 0 0]",
    "nut": "[0 2 -1 0 0 0 0]",
}


# ---------------------------------------------------------------------------
# 저수준 헬퍼: foamlib로 단순 딕셔너리 쓰기
# ---------------------------------------------------------------------------


def _write_simple_foam_file(path: Path, entries: dict[str, Any]) -> None:
    """foamlib FoamFile을 사용해 단순 primitive 딕셔너리 파일을 작성한다.

    값이 foamlib가 직렬화할 수 없는 복잡한 형식(차원 문자열, 다중 단어 등)인
    경우 ValueError를 발생시키므로, 그런 경우에는 호출하지 말 것.
    foamlib 비가용 시 수동으로 쓴다.
    """
    if _FOAMLIB_AVAILABLE and _FoamFile is not None:
        f = _FoamFile(path)
        with f:
            for k, v in entries.items():
                f[k] = v
    else:
        _write_raw_dict(path, entries)


def _write_raw_dict(path: Path, entries: dict[str, Any]) -> None:
    """수동으로 FoamFile 딕셔너리를 작성한다."""
    obj_name = path.name
    content = _HEADER.format(cls="dictionary", obj=obj_name)
    for k, v in entries.items():
        if isinstance(v, dict):
            content += f"{k}\n{{\n"
            for sk, sv in v.items():
                content += f"    {sk}    {sv};\n"
            content += "}\n\n"
        elif isinstance(v, bool):
            content += f"{k}    {'true' if v else 'false'};\n"
        else:
            content += f"{k}    {v};\n"
    content += _FOOTER
    path.write_text(content)


# ---------------------------------------------------------------------------
# FoamCaseWriter
# ---------------------------------------------------------------------------


class FoamCaseWriter:
    """foamlib 기반 OpenFOAM 케이스 디렉터리 생성기.

    Parameters
    ----------
    flow_velocity:
        기본 유입 속도 [m/s]. BC 생성 시 사용.
    turbulence_model:
        난류 모델 ("kEpsilon" | "kOmegaSST").
    """

    def __init__(
        self,
        flow_velocity: float = 1.0,
        turbulence_model: str = "kEpsilon",
    ) -> None:
        self.flow_velocity = flow_velocity
        self.turbulence_model = turbulence_model

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def write_case(
        self,
        mesh_dir: Path,
        case_dir: Path,
        flow_type: str = "external",
        solver: str = "simpleFoam",
        patches: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        """완전한 OpenFOAM 케이스 디렉터리를 생성한다.

        Parameters
        ----------
        mesh_dir:
            polyMesh가 있는 디렉터리.
            case_dir/constant/polyMesh 와 경로가 다를 경우 복사한다.
        case_dir:
            출력 OpenFOAM 케이스 루트.
        flow_type:
            "external" | "internal". 기본 패치 생성 힌트로 사용.
        solver:
            "simpleFoam" | "pimpleFoam".
        patches:
            경계 패치 목록 [{"name": str, "type": str}, ...].
            None이면 flow_type 기반 기본 패치 사용.

        Returns
        -------
        list[str]
            생성된 파일의 case_dir 기준 상대 경로 목록.
        """
        case_dir = Path(case_dir)
        mesh_dir = Path(mesh_dir)

        # polyMesh 복사 (다른 위치인 경우)
        target_polymesh = case_dir / "constant" / "polyMesh"
        if mesh_dir.exists() and mesh_dir.resolve() != target_polymesh.resolve():
            target_polymesh.parent.mkdir(parents=True, exist_ok=True)
            if target_polymesh.exists():
                shutil.rmtree(target_polymesh)
            shutil.copytree(mesh_dir, target_polymesh)
            log.info("polymesh_copied", src=str(mesh_dir), dst=str(target_polymesh))

        if patches is None:
            patches = self._default_patches(flow_type)

        written: list[str] = []
        written += self._write_system(case_dir, solver)
        written += self._write_constant(case_dir)
        written += self._write_zero(case_dir, patches)

        log.info(
            "openfoam_case_written",
            case_dir=str(case_dir),
            solver=solver,
            files=len(written),
        )
        return written

    # ------------------------------------------------------------------
    # system/
    # ------------------------------------------------------------------

    def _write_system(self, case_dir: Path, solver: str) -> list[str]:
        system_dir = case_dir / "system"
        system_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []

        self._write_control_dict(system_dir / "controlDict", solver)
        written.append("system/controlDict")

        self._write_fv_schemes(system_dir / "fvSchemes", solver)
        written.append("system/fvSchemes")

        self._write_fv_solution(system_dir / "fvSolution", solver)
        written.append("system/fvSolution")

        self._write_decompose_par(system_dir / "decomposeParDict")
        written.append("system/decomposeParDict")

        return written

    def _write_control_dict(self, path: Path, solver: str) -> None:
        is_transient = solver == "pimpleFoam"
        if _FOAMLIB_AVAILABLE and _FoamFile is not None:
            f = _FoamFile(path)
            with f:
                f["application"] = solver
                f["startFrom"] = "latestTime"
                f["startTime"] = 0
                f["stopAt"] = "endTime"
                f["endTime"] = 0.1 if is_transient else 1000
                f["deltaT"] = 0.001 if is_transient else 1
                f["writeControl"] = "timeStep" if is_transient else "runTime"
                f["writeInterval"] = 100
                f["purgeWrite"] = 0
                f["writeFormat"] = "ascii"
                f["writePrecision"] = 6
                f["writeCompression"] = False  # foamlib stores "off" as False
                f["timeFormat"] = "general"
                f["timePrecision"] = 6
                f["runTimeModifiable"] = True
        else:
            entries: dict[str, Any] = {
                "application": solver,
                "startFrom": "latestTime",
                "startTime": 0,
                "stopAt": "endTime",
                "endTime": 0.1 if is_transient else 1000,
                "deltaT": 0.001 if is_transient else 1,
                "writeControl": "timeStep" if is_transient else "runTime",
                "writeInterval": 100,
                "purgeWrite": 0,
                "writeFormat": "ascii",
                "writePrecision": 6,
                "writeCompression": "off",
                "timeFormat": "general",
                "timePrecision": 6,
                "runTimeModifiable": "true",
            }
            _write_raw_dict(path, entries)

    def _write_fv_schemes(self, path: Path, solver: str) -> None:
        """fvSchemes는 복잡한 다중 단어 값을 포함해 수동으로 쓴다."""
        is_transient = solver == "pimpleFoam"
        ddt = "Euler" if is_transient else "steadyState"
        content = _HEADER.format(cls="dictionary", obj="fvSchemes")
        content += f"ddtSchemes\n{{\n    default         {ddt};\n}}\n\n"
        content += (
            "gradSchemes\n{\n"
            "    default         Gauss linear;\n"
            "    grad(U)         cellLimited Gauss linear 1;\n"
            "}\n\n"
        )
        content += (
            "divSchemes\n{\n"
            "    default         none;\n"
            "    div(phi,U)      bounded Gauss linearUpwind grad(U);\n"
            "    div(phi,k)      bounded Gauss upwind;\n"
            "    div(phi,epsilon) bounded Gauss upwind;\n"
            "    div(phi,omega)  bounded Gauss upwind;\n"
            "    div((nuEff*dev(T(grad(U))))) Gauss linear;\n"
            "    div((nuEff*dev2(T(grad(U))))) Gauss linear;\n"
            "}\n\n"
        )
        content += "laplacianSchemes\n{\n    default         Gauss linear corrected;\n}\n\n"
        content += "interpolationSchemes\n{\n    default         linear;\n}\n\n"
        content += "snGradSchemes\n{\n    default         corrected;\n}\n\n"
        content += "fluxRequired\n{\n    default         no;\n    p               ;\n}\n"
        content += _FOOTER
        path.write_text(content)

    def _write_fv_solution(self, path: Path, solver: str) -> None:
        """fvSolution도 중첩 구조가 복잡해 수동으로 쓴다."""
        is_transient = solver == "pimpleFoam"
        content = _HEADER.format(cls="dictionary", obj="fvSolution")
        content += (
            "solvers\n{\n"
            "    p\n    {\n"
            "        solver          GAMG;\n"
            "        smoother        GaussSeidel;\n"
            "        tolerance       1e-6;\n"
            "        relTol          0.1;\n"
            "    }\n"
            "    U\n    {\n"
            "        solver          smoothSolver;\n"
            "        smoother        GaussSeidel;\n"
            "        tolerance       1e-6;\n"
            "        relTol          0.1;\n"
            "    }\n"
            "    k\n    {\n"
            "        solver          smoothSolver;\n"
            "        smoother        GaussSeidel;\n"
            "        tolerance       1e-6;\n"
            "        relTol          0.1;\n"
            "    }\n"
            "    epsilon\n    {\n"
            "        solver          smoothSolver;\n"
            "        smoother        GaussSeidel;\n"
            "        tolerance       1e-6;\n"
            "        relTol          0.1;\n"
            "    }\n"
            "    omega\n    {\n"
            "        solver          smoothSolver;\n"
            "        smoother        GaussSeidel;\n"
            "        tolerance       1e-6;\n"
            "        relTol          0.1;\n"
            "    }\n"
            "}\n\n"
        )
        if is_transient:
            content += (
                "PIMPLE\n{\n"
                "    nOuterCorrectors    1;\n"
                "    nCorrectors         2;\n"
                "    nNonOrthogonalCorrectors 1;\n"
                "}\n"
            )
        else:
            content += (
                "SIMPLE\n{\n"
                "    nNonOrthogonalCorrectors 0;\n"
                "    consistent          true;\n"
                "    residualControl\n    {\n"
                "        p               1e-4;\n"
                "        U               1e-4;\n"
                "        k               1e-4;\n"
                "        epsilon         1e-4;\n"
                "    }\n"
                "}\n\n"
                "relaxationFactors\n{\n"
                "    equations\n    {\n"
                "        U               0.9;\n"
                "        k               0.7;\n"
                "        epsilon         0.7;\n"
                "    }\n"
                "}\n"
            )
        content += _FOOTER
        path.write_text(content)

    def _write_decompose_par(self, path: Path) -> None:
        if _FOAMLIB_AVAILABLE and _FoamFile is not None:
            f = _FoamFile(path)
            with f:
                f["numberOfSubdomains"] = 4
                f["method"] = "scotch"
        else:
            _write_raw_dict(path, {"numberOfSubdomains": 4, "method": "scotch"})

    # ------------------------------------------------------------------
    # constant/
    # ------------------------------------------------------------------

    @staticmethod
    def _write_transport_properties(path: Path) -> None:
        """constant/transportProperties 수동 쓰기.

        foamlib는 "[0 2 -1 0 0 0 0] 1e-06" 형태의 차원 문자열을
        Dimensioned 타입으로 파싱하므로 일반 문자열로 저장할 수 없다.
        foamlib.Dimensioned를 사용하거나 수동으로 쓴다.
        """
        if _FOAMLIB_AVAILABLE and _FoamFile is not None:
            try:
                from foamlib import Dimensioned, DimensionSet  # noqa: PLC0415

                dim = DimensionSet(length=2, time=-1)
                nu = Dimensioned(1e-6, dim)
                f = _FoamFile(path)
                with f:
                    f["transportModel"] = "Newtonian"
                    f["nu"] = nu
                return
            except Exception:  # noqa: BLE001
                pass  # fallback to manual

        content = _HEADER.format(cls="dictionary", obj="transportProperties")
        content += "transportModel  Newtonian;\n\nnu              [0 2 -1 0 0 0 0] 1e-06;\n"
        content += _FOOTER
        path.write_text(content)

    def _write_constant(self, case_dir: Path) -> list[str]:
        const_dir = case_dir / "constant"
        const_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []

        # transportProperties: "nu" 값이 차원 문자열이라 foamlib Dimensioned 타입 필요
        # 호환성을 위해 수동 쓰기 사용
        self._write_transport_properties(const_dir / "transportProperties")
        written.append("constant/transportProperties")

        model = self.turbulence_model
        # turbulenceProperties의 중첩 RAS 서브딕셔너리를 수동으로 작성
        content = _HEADER.format(cls="dictionary", obj="turbulenceProperties")
        content += (
            "simulationType  RAS;\n\n"
            f"RAS\n{{\n"
            f"    RASModel        {model};\n"
            "    turbulence      on;\n"
            "    printCoeffs     on;\n"
            "}\n"
        )
        content += _FOOTER
        (const_dir / "turbulenceProperties").write_text(content)
        written.append("constant/turbulenceProperties")

        return written

    # ------------------------------------------------------------------
    # 0/
    # ------------------------------------------------------------------

    def _write_zero(
        self,
        case_dir: Path,
        patches: list[dict[str, Any]],
    ) -> list[str]:
        zero_dir = case_dir / "0"
        zero_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []

        fields = ["p", "U", "k", "nut"]
        if self.turbulence_model == "kEpsilon":
            fields.append("epsilon")
        else:
            fields.append("omega")

        for field_name in fields:
            self._write_field_file(zero_dir / field_name, field_name, patches)
            written.append(f"0/{field_name}")

        return written

    def _write_field_file(
        self,
        path: Path,
        field_name: str,
        patches: list[dict[str, Any]],
    ) -> None:
        dims = _DIMENSIONS.get(field_name, "[0 0 0 0 0 0 0]")
        internal = self._internal_value(field_name)
        bc_lines = self._build_boundary_field(field_name, patches)
        foam_class = "volVectorField" if field_name == "U" else "volScalarField"

        content = _HEADER.format(cls=foam_class, obj=field_name)
        content += f"dimensions      {dims};\n\n"
        content += f"internalField   uniform {internal};\n\n"
        content += f"boundaryField\n{{\n{bc_lines}}}\n"
        content += _FOOTER
        path.write_text(content)

    def _internal_value(self, field_name: str) -> str:
        v = self.flow_velocity
        k_val = 0.5 * (0.05 * v) ** 2 * 3
        defaults: dict[str, str] = {
            "p": "0",
            "U": f"({v} 0 0)",
            "k": f"{k_val:.6g}",
            "epsilon": f"{k_val ** 1.5 / 0.1:.6g}",
            "omega": f"{k_val ** 0.5 / (0.09 ** 0.25 * 0.1):.6g}",
            "nut": "0",
        }
        return defaults.get(field_name, "0")

    def _build_boundary_field(
        self, field_name: str, patches: list[dict[str, Any]]
    ) -> str:
        v = self.flow_velocity
        k_val = 0.5 * (0.05 * v) ** 2 * 3
        omega_val = k_val**0.5 / (0.09**0.25 * 0.1)
        lines: list[str] = []
        for patch in patches:
            name = patch["name"]
            ptype = patch.get("type", "wall")
            lines.append(
                self._patch_bc(field_name, name, ptype, v, k_val, omega_val)
            )
        return "".join(lines)

    @staticmethod
    def _patch_bc(
        field_name: str,
        name: str,
        ptype: str,
        velocity: float,
        k_val: float,
        omega_val: float,
    ) -> str:
        i = "    "

        def entry(bc_type: str, extra: str = "") -> str:
            return f"{i}{name}\n{i}{{\n{i}    type    {bc_type};{extra}\n{i}}}\n"

        if field_name == "p":
            if ptype == "outlet":
                return entry("fixedValue", "\n        value   uniform 0;")
            return entry("zeroGradient")

        if field_name == "U":
            if ptype == "inlet":
                return entry(
                    "fixedValue", f"\n        value   uniform ({velocity} 0 0);"
                )
            if ptype == "wall":
                return entry("noSlip")
            if ptype == "symmetryPlane":
                return entry("symmetry")
            return entry("zeroGradient")

        if field_name == "k":
            if ptype == "inlet":
                return entry("fixedValue", f"\n        value   uniform {k_val:.6g};")
            if ptype == "wall":
                return entry(
                    "kqRWallFunction", f"\n        value   uniform {k_val:.6g};"
                )
            return entry("zeroGradient")

        if field_name == "epsilon":
            eps = k_val**1.5 / 0.1
            if ptype == "inlet":
                return entry("fixedValue", f"\n        value   uniform {eps:.6g};")
            if ptype == "wall":
                return entry(
                    "epsilonWallFunction", f"\n        value   uniform {eps:.6g};"
                )
            return entry("zeroGradient")

        if field_name == "omega":
            if ptype == "inlet":
                return entry(
                    "fixedValue", f"\n        value   uniform {omega_val:.6g};"
                )
            if ptype == "wall":
                return entry(
                    "omegaWallFunction", f"\n        value   uniform {omega_val:.6g};"
                )
            return entry("zeroGradient")

        if field_name == "nut":
            if ptype == "wall":
                return entry("nutkWallFunction", "\n        value   uniform 0;")
            return entry("calculated", "\n        value   uniform 0;")

        return entry("zeroGradient")

    # ------------------------------------------------------------------
    # 유틸
    # ------------------------------------------------------------------

    @staticmethod
    def _default_patches(flow_type: str) -> list[dict[str, Any]]:
        if flow_type == "internal":
            return [
                {"name": "inlet", "type": "inlet"},
                {"name": "outlet", "type": "outlet"},
                {"name": "walls", "type": "wall"},
            ]
        return [
            {"name": "inlet", "type": "inlet"},
            {"name": "outlet", "type": "outlet"},
            {"name": "top", "type": "symmetryPlane"},
            {"name": "bottom", "type": "symmetryPlane"},
            {"name": "sides", "type": "symmetryPlane"},
            {"name": "body", "type": "wall"},
        ]
