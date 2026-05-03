"""Salome SMESH tier — Salome 를 subprocess 로 호출하는 경량 wrapper.

Salome SMESH 만 별도로 pip/conda 설치 불가 (KERNEL + MED + GEOM 과 묶여 있음).
대신 사용자가 Salome Platform 공식 binary 를 설치했을 경우 binary 경로를 자동
감지해 headless (``salome -t script.py``) 로 호출한다.

동작:
  1. Salome binary 감지 — PATH / 표준 설치 디렉토리 스캔
  2. 없으면 친절한 설치 가이드 에러
  3. 있으면 입력 STL → Salome Python 스크립트 실행 → MED 출력
  4. MED → .msh (meshio 변환) → gmshToFoam → polyMesh

Volume tier 로도, Layer post tier 로도 재사용 가능 (strategy params 로 분기).

설치 안내 (수동):
  Linux:
    1) https://www.salome-platform.org/downloads/current-version/ 에서
       "Linux - Universal Binary (UB)" 다운로드 (~10GB 압축)
    2) /opt 또는 $HOME 에 압축 해제
    3) 예: /opt/SALOME-9.14.0-native-UB22.04-SRC/salome -t script.py
  Docker (실험적 — 공식 이미지는 부재, 커뮤니티 이미지 검색 필요):
    search 'docker salome mesh'
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

log = get_logger(__name__)

TIER_NAME = "tier_salome_smesh"

_SALOME_SEARCH_ROOTS = [
    "/opt",
    "/usr/local",
    str(Path.home()),
    "/srv",
]
_SALOME_DIR_PATTERNS = ("SALOME-*", "salome-*", "Salome-*", "SALOME_*")


def find_salome_binary() -> str | None:
    """Salome binary 를 찾는다. 우선순위:

    1. PATH 내 ``salome``
    2. 표준 설치 디렉토리의 ``SALOME-*/salome`` 또는 ``salome-*/salome``
    """
    # 1. PATH
    in_path = shutil.which("salome")
    if in_path:
        return in_path

    # 2. 표준 디렉토리 스캔
    for root in _SALOME_SEARCH_ROOTS:
        p = Path(root)
        if not p.exists():
            continue
        for pattern in _SALOME_DIR_PATTERNS:
            for candidate in p.glob(pattern):
                bin_candidates = [
                    candidate / "salome",
                    candidate / "bin" / "salome",
                    candidate / "appli" / "salome",
                ]
                for b in bin_candidates:
                    if b.is_file() and os.access(b, os.X_OK):
                        return str(b)
    return None


# ---------------------------------------------------------------------------
# Salome Python 스크립트 — headless 실행 대상
# ---------------------------------------------------------------------------

_SALOME_MESH_SCRIPT = r"""
# -*- coding: utf-8 -*-
# AutoTessell 이 Salome 에게 넘기는 headless meshing script.
# 인자: <stl_path> <output_med_path> <algo> <max_size>
import sys, os

stl_path, output_med, algo, max_size = sys.argv[1:5]
max_size = float(max_size)

import salome
salome.salome_init()

from salome.geom import geomBuilder
from salome.smesh import smeshBuilder
import SMESH
import GEOM

geompy = geomBuilder.New()
smesh = smeshBuilder.New()

try:
    # STL import 는 Salome 에서 CAD shape 으로 바로 변환되지 않는다 —
    # STEP / BREP 이 이상적. STL 지원 확인.
    if stl_path.lower().endswith((".step", ".stp")):
        shape = geompy.ImportSTEP(stl_path, False, False)
    elif stl_path.lower().endswith((".iges", ".igs")):
        shape = geompy.ImportIGES(stl_path)
    elif stl_path.lower().endswith((".brep",)):
        shape = geompy.ImportBREP(stl_path)
    else:
        # STL: Salome 는 STL 을 직접 meshing 입력으로 받는 ImportSTL (surface mesh)
        # 을 제공. 이 경우 SMESH 가 직접 tetrahedralize.
        shape = geompy.ImportSTL(stl_path)
    geompy.addToStudy(shape, "imported")

    mesh = smesh.Mesh(shape)

    algo = algo.lower()
    if algo == "netgen_tet":
        alg3d = mesh.Tetrahedron(algo=smeshBuilder.NETGEN)
        alg3d.SetMaxSize(max_size)
        mesh.Triangle(algo=smeshBuilder.NETGEN_1D2D)
    elif algo == "ghs3d" or algo == "mg_tetra":
        mesh.Tetrahedron(algo=smeshBuilder.GHS3D)
    elif algo == "hexotic" or algo == "mg_hexa":
        mesh.Hexahedron(algo=smeshBuilder.Hexotic)
    else:
        # 기본: Netgen 1D+2D+3D
        alg3d = mesh.Tetrahedron(algo=smeshBuilder.NETGEN_1D2D3D)
        alg3d.SetMaxSize(max_size)

    ok = mesh.Compute()
    if not ok:
        print("[SMESH] Compute 실패", file=sys.stderr)
        sys.exit(1)

    mesh.ExportMED(output_med, 0)
    print(f"[SMESH] OK cells={mesh.NbVolumes()} nodes={mesh.NbNodes()}", flush=True)
    sys.exit(0)
except Exception as exc:
    import traceback
    traceback.print_exc()
    print(f"[SMESH] 오류: {exc}", file=sys.stderr)
    sys.exit(2)
"""


def _run_salome_mesh(
    salome_bin: str,
    stl_path: Path,
    case_dir: Path,
    algo: str = "netgen_tet",
    max_size: float = 0.1,
    timeout: int = 600,
) -> tuple[bool, str, Path | None]:
    """Salome headless 로 스크립트 실행 → MED 파일 생성.

    Returns:
        (success, message, med_path)
    """
    with tempfile.TemporaryDirectory(prefix="autotessell_salome_") as tmp:
        tmp_dir = Path(tmp)
        script = tmp_dir / "mesh_script.py"
        script.write_text(_SALOME_MESH_SCRIPT, encoding="utf-8")
        med_out = case_dir / "salome_smesh_out.med"
        med_out.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            salome_bin, "-t", str(script),
            "args:", str(stl_path), str(med_out), algo, str(max_size),
        ]
        log.info("salome_smesh_exec", cmd=" ".join(cmd))
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(tmp_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return False, f"Salome 실행 timeout ({timeout}s)", None
        except Exception as exc:
            return False, f"Salome subprocess 실패: {exc}", None

        tail = (proc.stdout + "\n" + proc.stderr)[-500:]
        if proc.returncode != 0 or not med_out.exists():
            return False, f"Salome returncode={proc.returncode}. tail: {tail}", None
        return True, f"Salome SMESH OK. tail: {tail[-200:]}", med_out


def _med_to_polymesh(med_path: Path, case_dir: Path) -> tuple[bool, str]:
    """MED → .msh (meshio) → gmshToFoam → polyMesh."""
    try:
        import meshio
    except ImportError:
        return False, "meshio 미설치 — pip install meshio"

    try:
        m = meshio.read(str(med_path))
    except Exception as exc:
        return False, f"MED 읽기 실패: {exc}"

    msh_path = case_dir / "salome_to_gmsh.msh"
    try:
        meshio.write(str(msh_path), m, file_format="gmsh22")
    except Exception as exc:
        return False, f"MSH 쓰기 실패: {exc}"

    try:
        from core.utils.openfoam_utils import run_openfoam
        # gmshToFoam 용 controlDict placeholder
        (case_dir / "system").mkdir(parents=True, exist_ok=True)
        ctrl = case_dir / "system" / "controlDict"
        if not ctrl.exists():
            ctrl.write_text(
                "FoamFile { version 2.0; format ascii; class dictionary; "
                "object controlDict; }\napplication simpleFoam;\n"
                "startFrom latestTime;\nstartTime 0;\nstopAt endTime;\n"
                "endTime 100;\ndeltaT 1;\nwriteControl timeStep;\n"
                "writeInterval 100;\npurgeWrite 0;\nwriteFormat ascii;\n"
                "writePrecision 6;\nwriteCompression off;\ntimeFormat general;\n"
                "timePrecision 6;\nrunTimeModifiable true;\n",
                encoding="utf-8",
            )
        run_openfoam("gmshToFoam", case_dir, args=[str(msh_path)])
        return True, "MED→gmsh→polyMesh 변환 OK"
    except Exception as exc:
        return False, f"gmshToFoam 실패: {str(exc)[-300:]}"


# ---------------------------------------------------------------------------
# Volume Tier
# ---------------------------------------------------------------------------


class TierSalomeSmeshGenerator:
    """Salome SMESH 기반 볼륨 메쉬 생성기.

    tier_specific_params:
      - salome_smesh_algo: "netgen_tet"(기본) | "ghs3d" | "hexotic"
      - salome_smesh_max_size: float (기본 0.1, bbox 상대)
      - salome_smesh_timeout: int 초 (기본 600)
    """

    TIER_NAME = TIER_NAME

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        t_start = time.monotonic()
        log.info("tier_salome_smesh_start", case_dir=str(case_dir))

        salome_bin = find_salome_binary()
        if salome_bin is None:
            elapsed = time.monotonic() - t_start
            msg = (
                "Salome 미설치 — binary 를 PATH 또는 /opt/SALOME-*/ 에서 찾지 못했습니다.\n"
                "\n"
                "설치 가이드 (약 10GB 압축):\n"
                "  1) https://www.salome-platform.org/downloads/current-version 에서\n"
                "     Linux Universal Binary 다운로드 (현재 9.14.0)\n"
                "  2) /opt 에 압축 해제:\n"
                "     sudo tar xf SALOME-9.14.0-native-UB22.04-SRC.tar.gz -C /opt\n"
                "  3) 확인: /opt/SALOME-9.14.0-*/salome --version\n"
                "\n"
                "설치 후 AutoTessell 은 자동 감지 — 별도 설정 불필요.\n"
                "경량 대안이 필요하면 Netgen tier (tier05_netgen) 권장 "
                "(SMESH 의 NETGEN plugin 과 같은 알고리즘, Salome 없이 동작)."
            )
            log.warning("salome_not_found")
            return TierAttempt(
                tier=self.TIER_NAME, status="failed",
                time_seconds=elapsed, error_message=msg,
            )

        params: dict[str, Any] = strategy.tier_specific_params or {}
        algo = str(params.get("salome_smesh_algo", "netgen_tet")).lower()
        max_size = float(params.get(
            "salome_smesh_max_size",
            strategy.surface_mesh.target_cell_size * 4 if strategy.surface_mesh else 0.1,
        ))
        timeout = int(params.get("salome_smesh_timeout", 600))

        ok, msg, med_path = _run_salome_mesh(
            salome_bin, preprocessed_path, case_dir,
            algo=algo, max_size=max_size, timeout=timeout,
        )
        if not ok or med_path is None:
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=self.TIER_NAME, status="failed",
                time_seconds=elapsed, error_message=f"SMESH 실행 실패: {msg}",
            )

        conv_ok, conv_msg = _med_to_polymesh(med_path, case_dir)
        elapsed = time.monotonic() - t_start
        if not conv_ok:
            return TierAttempt(
                tier=self.TIER_NAME, status="failed",
                time_seconds=elapsed,
                error_message=f"polyMesh 변환 실패: {conv_msg}",
            )
        log.info("tier_salome_smesh_success", elapsed=elapsed,
                 algo=algo, max_size=max_size)
        return TierAttempt(
            tier=self.TIER_NAME, status="success", time_seconds=elapsed,
        )


# ---------------------------------------------------------------------------
# Layer Post helper — 주 엔진 결과 위에 Salome SMESH 로 BL 추가
# ---------------------------------------------------------------------------


def run_salome_bl_post(
    case_dir: Path,
    preprocessed_path: Path,
    num_layers: int,
    growth_ratio: float,
    first_thickness: float,
) -> tuple[bool, str]:
    """Salome SMESH 의 Viscous Layers hypothesis 사용.

    SMESH 의 NETGEN_3D + Viscous Layers 조합으로 BL 생성. 입력이 STL 인 경우
    Salome 내부에서 surface meshing 후 volume + BL prism.
    """
    salome_bin = find_salome_binary()
    if salome_bin is None:
        return False, (
            "Salome 미설치. TierSalomeSmeshGenerator 의 설치 가이드 참조."
        )

    script = _SALOME_BL_SCRIPT
    with tempfile.TemporaryDirectory(prefix="autotessell_salome_bl_") as tmp:
        tmp_dir = Path(tmp)
        sp = tmp_dir / "bl_script.py"
        sp.write_text(script, encoding="utf-8")
        med_out = case_dir / "salome_bl_out.med"
        cmd = [
            salome_bin, "-t", str(sp),
            "args:", str(preprocessed_path), str(med_out),
            str(int(num_layers)), str(float(growth_ratio)),
            str(float(first_thickness)),
        ]
        try:
            proc = subprocess.run(
                cmd, cwd=str(tmp_dir),
                capture_output=True, text=True, timeout=600,
            )
        except subprocess.TimeoutExpired:
            return False, "Salome BL timeout"
        except Exception as exc:
            return False, f"Salome BL subprocess 실패: {exc}"

        if proc.returncode != 0 or not med_out.exists():
            tail = (proc.stdout + "\n" + proc.stderr)[-400:]
            return False, f"Salome BL returncode={proc.returncode}: {tail}"

    return _med_to_polymesh(med_out, case_dir)


_SALOME_BL_SCRIPT = r"""
# -*- coding: utf-8 -*-
import sys, salome
salome.salome_init()
from salome.geom import geomBuilder
from salome.smesh import smeshBuilder
import SMESH

stl_path, med_out, n_layers, growth, first_h = sys.argv[1:6]
n_layers = int(n_layers)
growth = float(growth)
first_h = float(first_h)

geompy = geomBuilder.New()
smesh = smeshBuilder.New()

try:
    shape = geompy.ImportSTL(stl_path)
    geompy.addToStudy(shape, "imported")
    mesh = smesh.Mesh(shape)
    alg3d = mesh.Tetrahedron(algo=smeshBuilder.NETGEN_1D2D3D)
    alg3d.SetMaxSize(1.0)
    # Viscous Layers hypothesis
    try:
        vl = alg3d.ViscousLayers(
            first_h * (growth ** n_layers),  # total thickness
            n_layers,
            growth,
            [], SMESH.EDGE,
        )
    except Exception:
        pass
    mesh.Compute()
    mesh.ExportMED(med_out, 0)
    sys.exit(0)
except Exception as exc:
    print(f"BL 실패: {exc}", file=sys.stderr)
    sys.exit(1)
"""
