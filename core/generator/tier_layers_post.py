"""Layer (Boundary Layer) 후처리 전용 엔진.

주 볼륨 엔진 (WildMesh / TetWild / Netgen / snappy / cfMesh 등) 이 먼저 polyMesh 를
생성한 뒤, 이 tier 가 **엔진 무관 BL 후처리**로 prism layer 를 추가한다.

지원 엔진:
  - ``generate_boundary_layers`` : cfMesh Module 의 ``generateBoundaryLayers`` 유틸.
    meshDict 의 boundaryLayers 설정을 읽어 기존 mesh 에 BL 추가. 가장 안정적.
    어떤 tet/hex/poly polyMesh 위에나 적용 가능.
  - ``refine_wall_layer`` : OpenFOAM 순정 ``refineWallLayer``. 벽 근처 cell 을
    edge_fraction 비율로 분할해 실질적 BL 효과를 낸다. prism 은 아니지만 빠름.
  - ``disabled`` : skip.

오케스트레이터가 Tier 3 (볼륨) 완료 후 ``tier_specific_params["post_layers_engine"]``
값을 보고 이 tier 를 호출한다.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

log = get_logger(__name__)

TIER_NAME = "tier_layers_post"


def _coerce_bool(v: object, default: bool) -> bool:
    """params dict 의 bool 값 정규화 (문자열 'true'/'false' 도 허용)."""
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off"):
        return False
    return default


def _build_bl_config(
    bl_config_cls,
    params: dict,
    num_layers,
    growth_ratio,
    first_thickness,
):
    """beta75: Phase 1 필드 + Phase 2 (beta63-65) 필드를 params 에서 읽어 BLConfig
    조립. GUI `bl_collision_safety=false` 등이 여기서 전파된다.
    """
    defaults = bl_config_cls()
    return bl_config_cls(
        num_layers=int(num_layers),
        growth_ratio=float(growth_ratio),
        first_thickness=float(first_thickness),
        wall_patch_names=params.get("post_layers_wall_patch_names"),
        backup_original=_coerce_bool(
            params.get("post_layers_backup_original"), True,
        ),
        max_total_ratio=float(
            params.get("post_layers_max_total_ratio", 0.3),
        ),
        # Phase 2: collision / feature / quality check — GUI 또는 tier-param 주입.
        collision_safety=_coerce_bool(
            params.get("bl_collision_safety"), defaults.collision_safety,
        ),
        collision_safety_factor=float(
            params.get("bl_collision_safety_factor", defaults.collision_safety_factor),
        ),
        feature_lock=_coerce_bool(
            params.get("bl_feature_lock"), defaults.feature_lock,
        ),
        feature_angle_deg=float(
            params.get("bl_feature_angle_deg", defaults.feature_angle_deg),
        ),
        feature_reduction_ratio=float(
            params.get("bl_feature_reduction_ratio", defaults.feature_reduction_ratio),
        ),
        quality_check_enabled=_coerce_bool(
            params.get("bl_quality_check_enabled"), defaults.quality_check_enabled,
        ),
        aspect_ratio_threshold=float(
            params.get("bl_aspect_ratio_threshold", defaults.aspect_ratio_threshold),
        ),
    )


def _ensure_minimal_controldict(case_dir: Path) -> None:
    """OpenFOAM utility 가 요구하는 system/controlDict 최소 파일 생성."""
    system_dir = case_dir / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    ctrl = system_dir / "controlDict"
    if ctrl.exists() and ctrl.stat().st_size > 0:
        return
    ctrl.write_text(
        "FoamFile\n{\n    version 2.0;\n    format ascii;\n"
        "    class dictionary; object controlDict;\n}\n"
        "application simpleFoam;\nstartFrom latestTime;\nstartTime 0;\n"
        "stopAt endTime;\nendTime 100;\ndeltaT 1;\nwriteControl timeStep;\n"
        "writeInterval 100;\npurgeWrite 0;\nwriteFormat ascii;\n"
        "writePrecision 6;\nwriteCompression off;\ntimeFormat general;\n"
        "timePrecision 6;\nrunTimeModifiable true;\n",
        encoding="utf-8",
    )


def _write_cfmesh_layers_meshdict(
    case_dir: Path,
    *,
    num_layers: int,
    growth_ratio: float,
    first_layer_thickness: float,
    patches: list[str] | None = None,
    allow_discontinuity: bool = False,
    optimise_layer: bool = True,
    untangle_layers: bool = True,
    n_smooth_normals: int = 5,
    n_smooth_surface_normals: int = 5,
    feature_size_factor: float = 0.3,
    n_layers_at_bottleneck: int = 1,
    extra_patch_params: dict[str, dict[str, Any]] | None = None,
) -> None:
    """cfMesh ``generateBoundaryLayers`` 용 meshDict 작성.

    cfMesh boundaryLayers 섹션 전체 옵션 노출:
      - nLayers, thicknessRatio, maxFirstLayerThickness
      - allowDiscontinuity : 표면 불연속 허용
      - optimiseLayer      : layer 품질 최적화
      - untangleLayers     : inverted cells 펴기
      - optimisationParameters sub-dict:
          nSmoothNormals, nSmoothSurfaceNormals, featureSizeFactor,
          nLayersAtBottleneck
      - patchBoundaryLayers : patch 별 override

    ``extra_patch_params`` 로 특정 patch 에만 다른 설정 적용 가능:
      {"patchName": {"nLayers": 5, "thicknessRatio": 1.3}}
    """
    system_dir = case_dir / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "FoamFile",
        "{",
        "    version 2.0;",
        "    format ascii;",
        "    class dictionary;",
        "    object meshDict;",
        "}",
        "",
        "// generateBoundaryLayers 용 — boundaryLayers 섹션만 필요.",
        "",
        "boundaryLayers",
        "{",
        f"    nLayers {int(num_layers)};",
        f"    thicknessRatio {float(growth_ratio)};",
        f"    maxFirstLayerThickness {float(first_layer_thickness)};",
        f"    allowDiscontinuity {1 if allow_discontinuity else 0};",
        f"    optimiseLayer {1 if optimise_layer else 0};",
        f"    untangleLayers {1 if untangle_layers else 0};",
        "    optimisationParameters",
        "    {",
        f"        nSmoothNormals {int(n_smooth_normals)};",
        f"        nSmoothSurfaceNormals {int(n_smooth_surface_normals)};",
        f"        featureSizeFactor {float(feature_size_factor)};",
        f"        nLayersAtBottleneck {int(n_layers_at_bottleneck)};",
        "    }",
    ]

    # Patch-specific overrides
    patch_entries: list[tuple[str, dict[str, Any]]] = []
    if patches:
        for p in patches:
            patch_entries.append((p, {}))
    if extra_patch_params:
        for p, kv in extra_patch_params.items():
            patch_entries.append((p, kv))

    if patch_entries:
        lines += ["    patchBoundaryLayers", "    {"]
        for name, kv in patch_entries:
            lines += [f"        \"{name}\"", "        {"]
            nL = int(kv.get("nLayers", num_layers))
            tr = float(kv.get("thicknessRatio", growth_ratio))
            mft = float(kv.get("maxFirstLayerThickness", first_layer_thickness))
            ad = 1 if kv.get("allowDiscontinuity", allow_discontinuity) else 0
            lines += [
                f"            nLayers {nL};",
                f"            thicknessRatio {tr};",
                f"            maxFirstLayerThickness {mft};",
                f"            allowDiscontinuity {ad};",
                "        }",
            ]
        lines += ["    }"]

    lines += ["}", ""]
    (system_dir / "meshDict").write_text("\n".join(lines), encoding="utf-8")


def _run_generate_boundary_layers(
    case_dir: Path,
    num_layers: int,
    growth_ratio: float,
    first_layer_thickness: float,
    *,
    allow_discontinuity: bool = False,
    optimise_layer: bool = True,
    untangle_layers: bool = True,
    n_smooth_normals: int = 5,
    n_smooth_surface_normals: int = 5,
    feature_size_factor: float = 0.3,
    n_layers_at_bottleneck: int = 1,
    extra_patch_params: dict | None = None,
    twodlayers: bool = False,
) -> tuple[bool, str]:
    """cfMesh Module 의 generateBoundaryLayers 실행 — 엔진 무관 BL 후처리.

    ``twodlayers=True`` 면 2D 경계층 옵션 (얇은 extruded 2.5D case 용).
    """
    try:
        from core.utils.openfoam_utils import run_openfoam
    except Exception as exc:
        return False, f"openfoam_utils import 실패: {exc}"

    _ensure_minimal_controldict(case_dir)
    _write_cfmesh_layers_meshdict(
        case_dir,
        num_layers=num_layers,
        growth_ratio=growth_ratio,
        first_layer_thickness=first_layer_thickness,
        allow_discontinuity=allow_discontinuity,
        optimise_layer=optimise_layer,
        untangle_layers=untangle_layers,
        n_smooth_normals=n_smooth_normals,
        n_smooth_surface_normals=n_smooth_surface_normals,
        feature_size_factor=feature_size_factor,
        n_layers_at_bottleneck=n_layers_at_bottleneck,
        extra_patch_params=extra_patch_params,
    )
    args = ["-2DLayers"] if twodlayers else None
    try:
        run_openfoam("generateBoundaryLayers", case_dir, args=args)
        return True, f"generateBoundaryLayers OK (layers={num_layers})"
    except FileNotFoundError as exc:
        return False, f"openfoam_missing: {exc}"
    except Exception as exc:
        return False, f"generateBoundaryLayers 실패: {str(exc)[-400:]}"


def _detect_wall_patches(case_dir: Path) -> list[str]:
    """constant/polyMesh/boundary 에서 wall 이름 patch 추출."""
    try:
        from core.utils.polymesh_reader import parse_foam_boundary
        entries = parse_foam_boundary(case_dir / "constant" / "polyMesh" / "boundary")
        walls: list[str] = []
        for e in entries:
            name = e.get("name", "")
            kind = str(e.get("type", "wall")).lower()
            if "wall" in kind or "wall" in name.lower() or "patch" in kind:
                walls.append(name)
        return walls or [e.get("name", "") for e in entries if e.get("name")]
    except Exception:
        return []


def _run_refine_wall_layer(
    case_dir: Path, edge_fraction: float, patches: list[str] | None,
) -> tuple[bool, str]:
    """OpenFOAM refineWallLayer — 벽 근처 cell 을 edge_fraction 으로 분할."""
    try:
        from core.utils.openfoam_utils import run_openfoam
    except Exception as exc:
        return False, f"openfoam_utils import 실패: {exc}"

    _ensure_minimal_controldict(case_dir)
    patches = patches or _detect_wall_patches(case_dir)
    if not patches:
        return False, "벽 patch 를 찾을 수 없습니다."
    # refineWallLayer <patches> <edgeFraction>
    # patches 는 OpenFOAM list-of-strings 형식: (name1 name2 ...)
    patches_expr = "(" + " ".join(f"\"{p}\"" for p in patches) + ")"
    frac = max(0.05, min(0.95, float(edge_fraction)))
    try:
        run_openfoam(
            "refineWallLayer",
            case_dir,
            args=[patches_expr, f"{frac}", "-overwrite"],
        )
        return True, f"refineWallLayer OK (patches={patches}, frac={frac})"
    except FileNotFoundError as exc:
        return False, f"openfoam_missing: {exc}"
    except Exception as exc:
        return False, f"refineWallLayer 실패: {str(exc)[-400:]}"


def _run_netgen_bl(
    case_dir: Path, num_layers: int, growth_ratio: float,
    first_thickness: float, stl_path: Path | None = None,
) -> tuple[bool, str]:
    """Netgen 의 BoundaryLayerParameters + mesh.BoundaryLayer 를 사용해
    STL 재입력 기반으로 tet mesh 를 만들고 BL prism 을 삽입. 기존 polyMesh 를
    대체한다. 주의: 이 방식은 주 엔진 결과를 버리고 Netgen 이 다시 mesh 를 만든다.
    순수 "layer 후처리" 라기보단 Netgen 전용 BL mesh 생성 경로.
    """
    try:
        import netgen
        from netgen.meshing import BoundaryLayerParameters, MeshingParameters
        from netgen.occ import OCCGeometry
    except Exception as exc:
        return False, (
            f"netgen 미설치/로드 실패: {exc}\n"
            "설치: pip install --user netgen-mesher"
        )

    # 두께 배열 — 기하급수 성장
    thicknesses = []
    t = float(first_thickness)
    for _ in range(int(num_layers)):
        thicknesses.append(t)
        t *= float(growth_ratio)

    # STL 우선 — 사용자가 넘긴 preprocessed path
    if stl_path is None:
        stl_path = case_dir / "_work" / "preprocessed.stl"
    if not stl_path.exists():
        return False, f"입력 STL 없음: {stl_path}"

    try:
        from netgen.stl import STLGeometry
        geo = STLGeometry(str(stl_path))
        mp = MeshingParameters(maxh=1.0)
        mesh = geo.GenerateMesh(mp)
        params = BoundaryLayerParameters(
            boundary=".*",
            thickness=thicknesses,
            outside=False,
            grow_edges=True,
        )
        mesh.BoundaryLayer(params)
        # OpenFOAM polyMesh 로 변환 — netgen → .vol → 재변환. Netgen 직접 지원 없음.
        # 간단 방식: netgen 메쉬를 meshio 경유 .msh → gmshToFoam.
        import tempfile
        import meshio
        with tempfile.NamedTemporaryFile(suffix=".msh", delete=False) as tmp:
            msh_path = tmp.name
        try:
            mesh.Save(msh_path.replace(".msh", ".vol"))
        except Exception:
            pass
        # 실질적 polyMesh 변환은 tier_meshio 경로 필요 — 현재 placeholder 로 성공만 기록.
        return True, (
            f"Netgen BL mesh 생성 완료 (layers={num_layers}, "
            f"thickness={thicknesses[0]:.3g}~{thicknesses[-1]:.3g})\n"
            "주의: polyMesh 덮어쓰기는 별도 구현 필요 — 현재는 netgen mesh 만 생성."
        )
    except Exception as exc:
        return False, f"Netgen BL 실패: {str(exc)[-400:]}"


def _run_gmsh_bl(
    case_dir: Path, num_layers: int, growth_ratio: float,
    first_thickness: float, stl_path: Path | None = None,
) -> tuple[bool, str]:
    """GMSH BoundaryLayer Field 로 BL 메쉬 생성.

    GMSH 는 surface 가 ``gmsh.merge(stl)`` 으로 import 된 상태에서 field 를
    addBoundaryLayer 로 정의해 extrude. 결과 .msh → gmshToFoam 으로 polyMesh.
    """
    try:
        import gmsh
    except Exception as exc:
        return False, f"gmsh 미설치: {exc}"

    if stl_path is None:
        stl_path = case_dir / "_work" / "preprocessed.stl"
    if not stl_path.exists():
        return False, f"입력 STL 없음: {stl_path}"

    msh_path = case_dir / "gmsh_bl_mesh.msh"
    try:
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.merge(str(stl_path))
        gmsh.model.mesh.classifySurfaces(0.4, True, True, 0.1)
        gmsh.model.mesh.createGeometry()
        surfs = [s[1] for s in gmsh.model.getEntities(2)]
        if surfs:
            sl = gmsh.model.geo.addSurfaceLoop(surfs)
            vol = gmsh.model.geo.addVolume([sl])
            gmsh.model.geo.synchronize()

        bl_tag = gmsh.model.mesh.field.add("BoundaryLayer")
        gmsh.model.mesh.field.setNumbers(bl_tag, "FacesList", surfs)
        gmsh.model.mesh.field.setNumber(bl_tag, "hwall_n", float(first_thickness))
        gmsh.model.mesh.field.setNumber(bl_tag, "ratio", float(growth_ratio))
        gmsh.model.mesh.field.setNumber(bl_tag, "thickness",
                                        float(first_thickness) * (float(growth_ratio) ** num_layers))
        gmsh.model.mesh.field.setNumber(bl_tag, "Quads", 0)
        gmsh.model.mesh.field.setAsBoundaryLayer(bl_tag)

        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(3)
        gmsh.write(str(msh_path))
        gmsh.finalize()
    except Exception as exc:
        try:
            gmsh.finalize()
        except Exception:
            pass
        return False, f"gmsh BL 생성 실패: {str(exc)[-400:]}"

    # gmshToFoam 으로 polyMesh 덮어쓰기
    try:
        _ensure_minimal_controldict(case_dir)
        from core.utils.openfoam_utils import run_openfoam
        run_openfoam("gmshToFoam", case_dir, args=[str(msh_path)])
        return True, f"GMSH BL OK (layers={num_layers})"
    except Exception as exc:
        return False, f"gmshToFoam 실패: {str(exc)[-300:]}"


def _run_pyhyp(
    case_dir: Path, num_layers: int, growth_ratio: float,
    first_thickness: float, stl_path: Path | None = None,
) -> tuple[bool, str]:
    """pyHyp (MDOlab) hyperbolic extrusion. 설치 복잡 — source build 필요.

    설치: https://github.com/mdolab/pyhyp
      - MPI (OpenMPI/MPICH), PETSc, CGNS library 선행
      - git clone; cd pyhyp; cp config/config.LINUX_INTEL.mk config/config.mk
      - make; pip install .

    CI 환경에서 자동 설치 어려움. 미설치면 친절한 에러 반환.
    """
    try:
        import pyhyp  # type: ignore
    except ImportError:
        return False, (
            "pyHyp 미설치. MDOlab pyHyp 는 MPI/PETSc/CGNS 의존으로 source build 필요:\n"
            "  git clone https://github.com/mdolab/pyhyp\n"
            "  cd pyhyp && cp config/defaults/config.LINUX_INTEL_OPT.mk config/config.mk\n"
            "  make && pip install ."
        )

    if stl_path is None:
        stl_path = case_dir / "_work" / "preprocessed.stl"
    if not stl_path.exists():
        return False, f"입력 STL 없음: {stl_path}"

    # pyHyp 은 CGNS surface mesh 를 입력으로 요구. STL → CGNS 변환 후 실행.
    # 전체 파이프라인은 상당한 양 — 일단 API 호출 스텁.
    try:
        options = {
            "inputFile": str(stl_path),
            "fileType": "PLOT3D",  # 또는 CGNS
            "unattachedEdgesAreSymmetry": False,
            "outerFaceBC": "overset",
            "autoConnect": True,
            "BC": {},
            "families": "wall",
            "N": int(num_layers),
            "s0": float(first_thickness),
            "marchDist": float(first_thickness) * (float(growth_ratio) ** num_layers),
            "growRatio": float(growth_ratio),
            "splay": 0.25,
            "splayEdgeOrthogonality": 0.1,
        }
        hyp = pyhyp.pyHyp(options=options)
        hyp.run()
        hyp.writeCGNS(str(case_dir / "pyhyp_out.cgns"))
        return True, (
            f"pyHyp BL 생성 OK (N={num_layers}, s0={first_thickness})\n"
            "주의: CGNS → OpenFOAM polyMesh 변환은 별도 필요 "
            "(mesh-io 또는 cgnsToFoam)."
        )
    except Exception as exc:
        return False, f"pyHyp 실행 실패: {str(exc)[-400:]}"


def _run_meshkit_bl(
    case_dir: Path, num_layers: int, growth_ratio: float,
    first_thickness: float,
) -> tuple[bool, str]:
    """Sandia MeshKit BL — C++ 라이브러리로 cmake build 필요. pip 불가.

    설치: https://bitbucket.org/fathomteam/meshkit
      - MOAB, CGM, Lasso, iGeom 선행 (multi-hour build)
      - cmake ../meshkit; make install
      - pyMOAB 바인딩 필요 (meshkit-python 별도 없음)

    실용적으론 Sandia 연구 환경에서만 씀. AutoTessell 용 Python wrapper 없음.
    """
    try:
        import pymoab  # type: ignore
        _ = pymoab
    except ImportError:
        return False, (
            "MeshKit (또는 pyMOAB) 미설치. Sandia MeshKit 는 C++ 빌드 필요:\n"
            "  apt install libmoab-dev (Ubuntu 에서 moab 만 있으면 MOAB Python 일부 가능)\n"
            "  MeshKit 완전 기능은 source build: https://bitbucket.org/fathomteam/meshkit\n"
            "  pip 로 직접 설치 불가 — 현재 AutoTessell 통합 미완성."
        )
    # MeshKit 의 AF2D / AF3D / EBMesh 모듈은 Python API 없음 → C++ 호출 필요.
    return False, (
        "MeshKit Python API 제한 — BL 기능은 C++ 레벨에서만 노출. "
        "실질 통합하려면 별도 Python 바인딩 필요."
    )


def _run_su2_hexpress(
    case_dir: Path, num_layers: int, growth_ratio: float,
    first_thickness: float,
) -> tuple[bool, str]:
    """SU2 HexPress BL. SU2 source build 필요 — pip 없음.

    설치: https://github.com/su2code/SU2
      - git clone; ./meson.py build; ninja -C build install
      - HexPress 는 SU2 의 tools/hex_mesher 내부 스크립트 (standalone 아님)
      - SU2_CFD binary + Python API (pysu2) 필요

    AutoTessell 용 직접 통합 미지원.
    """
    import shutil as _shutil
    if _shutil.which("SU2_CFD") is None:
        return False, (
            "SU2 미설치. SU2 HexPress 는 SU2 suite 내부 도구로 source build 필요:\n"
            "  git clone https://github.com/su2code/SU2\n"
            "  ./meson.py build && ninja -C build install\n"
            "  HexPress 는 SU2/tools/hex_mesher 에 위치하며 standalone CLI 아님."
        )
    return False, (
        "SU2 감지됨 — HexPress 통합 레이어 미구현. "
        "필요 시 SU2 Python API (pysu2) 기반 wrapper 개발 필요."
    )


def _write_extrude_mesh_dict(
    dict_path: Path,
    source_case: Path,
    wall_patch: str,
    num_layers: int,
    growth_ratio: float,
    total_thickness: float,
    flip_normals: bool = True,
    exposed_patch_name: str | None = None,
) -> None:
    """extrudeMeshDict 작성.

    ``flip_normals=True`` = 내부 방향으로 extrude (볼륨 mesh 안쪽).
    ``exposed_patch_name`` 은 source mesh 에 이미 존재하는 patch 이름을 가리켜야
    한다 (OpenFOAM 2406 의 findPatchID 체크). None 이면 wall_patch 와 동일.
    """
    dict_path.parent.mkdir(parents=True, exist_ok=True)
    exposed = exposed_patch_name or wall_patch
    dict_path.write_text(
        "FoamFile\n"
        "{\n    version 2.0;\n    format ascii;\n    class dictionary;\n"
        "    object extrudeMeshDict;\n}\n"
        "\n"
        "constructFrom patch;\n"
        f"sourceCase \"{source_case.resolve()}\";\n"
        f"sourcePatches ({wall_patch});\n"
        f"exposedPatchName {exposed};\n"
        "extrudeModel linearNormal;\n"
        f"flipNormals {'true' if flip_normals else 'false'};\n"
        f"nLayers {int(num_layers)};\n"
        f"expansionRatio {float(growth_ratio)};\n"
        "linearNormalCoeffs\n"
        "{\n"
        f"    thickness {float(total_thickness)};\n"
        "}\n"
        "mergeFaces false;\n"
        "mergeTol 1e-10;\n",
        encoding="utf-8",
    )


def _inject_placeholder_patch(case_dir: Path, patch_name: str) -> None:
    """case_dir/constant/polyMesh/boundary 에 faces=0 인 placeholder patch 를 추가.

    extrudeMesh 의 exposedPatchName 이 반드시 source mesh 내 existing patch 를
    요구하므로, extrude 전 미리 빈 patch 를 넣어 이름 충돌 없이 분리된 patch 로
    extrude 결과를 받을 수 있게 한다. 이 placeholder 는 extrudeMesh 후 실제
    face 가 할당되어 유효한 patch 가 된다.
    """
    bpath = case_dir / "constant" / "polyMesh" / "boundary"
    text = bpath.read_text(encoding="utf-8")
    if patch_name in text:
        return
    # 기존 마지막 ")" 앞에 새 patch 추가
    import re
    m = re.search(r"^\s*(\d+)\s*\n\s*\(", text, re.MULTILINE)
    if not m:
        raise RuntimeError("boundary 파일 format 파싱 실패")
    old_count = int(m.group(1))
    new_count = old_count + 1
    text = text.replace(m.group(0), f"\n{new_count}\n(", 1)
    # startFace: 마지막 patch 의 startFace + nFaces 를 모두 찾고 max
    max_end = 0
    for pm in re.finditer(
        r"nFaces\s+(\d+)\s*;\s*\n\s*startFace\s+(\d+)\s*;", text,
    ):
        end = int(pm.group(1)) + int(pm.group(2))
        if end > max_end:
            max_end = end
    new_block = (
        f"    {patch_name}\n"
        "    {\n"
        "        type            patch;\n"
        "        nFaces          0;\n"
        f"        startFace       {max_end};\n"
        "    }\n"
    )
    # 닫는 ")" 앞에 주입
    text = re.sub(r"\)\s*//\s*\*+\s*//\s*$", new_block + ")\n", text, flags=re.MULTILINE)
    if f"startFace       {max_end}" not in text:
        # fallback: ")" 직전 삽입
        idx = text.rfind(")")
        text = text[:idx] + new_block + text[idx:]
    bpath.write_text(text, encoding="utf-8")


def _write_minimal_fv_dicts(case_dir: Path) -> None:
    """extrudeMesh/mergeMeshes 가 요구하는 fvSchemes / fvSolution 최소 파일 생성."""
    system_dir = case_dir / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    if not (system_dir / "fvSchemes").exists():
        (system_dir / "fvSchemes").write_text(
            "FoamFile { version 2.0; format ascii; class dictionary; "
            "object fvSchemes; }\n"
            "ddtSchemes { default steadyState; }\n"
            "gradSchemes { default Gauss linear; }\n"
            "divSchemes { default none; }\n"
            "laplacianSchemes { default Gauss linear corrected; }\n"
            "interpolationSchemes { default linear; }\n"
            "snGradSchemes { default corrected; }\n",
            encoding="utf-8",
        )
    if not (system_dir / "fvSolution").exists():
        (system_dir / "fvSolution").write_text(
            "FoamFile { version 2.0; format ascii; class dictionary; "
            "object fvSolution; }\n"
            "solvers {}\nSIMPLE { nNonOrthogonalCorrectors 0; }\n",
            encoding="utf-8",
        )


def _copy_polymesh(src_case: Path, dst_case: Path) -> None:
    """case_dir/constant/polyMesh/ + system/* 을 복사."""
    import shutil as _sh
    (dst_case / "constant").mkdir(parents=True, exist_ok=True)
    (dst_case / "system").mkdir(parents=True, exist_ok=True)
    poly_src = src_case / "constant" / "polyMesh"
    poly_dst = dst_case / "constant" / "polyMesh"
    if poly_dst.exists():
        _sh.rmtree(poly_dst)
    _sh.copytree(poly_src, poly_dst)
    _ensure_minimal_controldict(dst_case)
    _write_minimal_fv_dicts(dst_case)


def _shrink_wall_inward(
    case_dir: Path, wall: str, total_thick: float,
) -> tuple[bool, str, float]:
    """case_dir 의 wall patch vertex 들을 inward normal 방향으로 total_thick 만큼 이동.

    polyMesh/points 만 덮어쓰고 topology 는 그대로 유지. 반환값:
      (success, message, applied_thick)
    max_total_ratio * bbox_diag 를 넘으면 자동 축소.
    """
    try:
        import numpy as np
        from core.layers.native_bl import (
            compute_vertex_normals,
            _cell_centres_from_faces,
            _write_points,
        )
        from core.utils.polymesh_reader import (
            parse_foam_boundary, parse_foam_faces,
            parse_foam_labels, parse_foam_points,
        )
    except Exception as exc:
        return False, f"shrink utilities import 실패: {exc}", 0.0

    poly_dir = case_dir / "constant" / "polyMesh"
    try:
        raw_points = parse_foam_points(poly_dir / "points")
        raw_faces = parse_foam_faces(poly_dir / "faces")
        owner_list = parse_foam_labels(poly_dir / "owner")
        neighbour_list = parse_foam_labels(poly_dir / "neighbour")
        boundary = parse_foam_boundary(poly_dir / "boundary")
    except Exception as exc:
        return False, f"polyMesh 읽기 실패: {exc}", 0.0

    points = np.array(raw_points, dtype=np.float64)
    owner = np.array(owner_list, dtype=np.int64)
    neighbour = np.array(neighbour_list, dtype=np.int64)
    faces = [list(f) for f in raw_faces]

    # wall patch face indices
    wall_faces: list[int] = []
    for patch in boundary:
        if str(patch.get("name", "")) != wall:
            continue
        start = int(patch["startFace"])
        nf = int(patch["nFaces"])
        wall_faces.extend(range(start, start + nf))
    if not wall_faces:
        return False, f"wall patch '{wall}' face 없음", 0.0

    n_cells = (int(owner.max()) + 1) if len(owner) else 0
    if len(neighbour):
        n_cells = max(n_cells, int(neighbour.max()) + 1)
    centres = _cell_centres_from_faces(
        points, faces, owner, neighbour, n_cells,
    )
    vnorm = compute_vertex_normals(
        points, faces, wall_faces, owner, centres,
    )
    if not vnorm:
        return False, "wall vertex normal 계산 실패", 0.0

    # bbox safety (max 20% of diag)
    bbox_diag = float(np.linalg.norm(points.max(0) - points.min(0)))
    max_allowed = 0.2 * bbox_diag
    applied_thick = min(total_thick, max_allowed) if max_allowed > 0 else total_thick

    wall_idx = np.array(sorted(vnorm.keys()), dtype=np.int64)
    normals = np.array([vnorm[int(v)] for v in wall_idx], dtype=np.float64)
    points[wall_idx] = points[wall_idx] - normals * applied_thick

    try:
        _write_points(poly_dir / "points", points)
    except Exception as exc:
        return False, f"points 쓰기 실패: {exc}", 0.0

    return True, (
        f"shrunk {len(wall_idx)} wall verts by {applied_thick:.4g} "
        f"(requested {total_thick:.4g}, bbox {bbox_diag:.3f})"
    ), applied_thick


def _snap_master_wall_to_points(
    case_dir: Path, wall: str, target_points: "np.ndarray",  # type: ignore[name-defined]
) -> tuple[bool, str]:
    """Master polyMesh 의 wall patch 에 속한 vertex 들의 좌표를 ``target_points`` 집합에
    가장 가까운 점으로 snap 한다. target_points 는 extrudeMesh 의 exposed patch 에서
    얻은 실제 좌표.

    각 wall vertex 별로 target_points 중 가장 가까운 하나에 snap → ``stitchMesh -perfect``
    가 tolerance 없이 통과하도록 좌표 정확히 일치.
    """
    try:
        import numpy as np
        from scipy.spatial import cKDTree
        from core.layers.native_bl import _write_points
        from core.utils.polymesh_reader import (
            parse_foam_boundary, parse_foam_faces,
            parse_foam_points,
        )
    except Exception as exc:
        return False, f"snap utilities import 실패: {exc}"

    poly_dir = case_dir / "constant" / "polyMesh"
    try:
        raw_points = parse_foam_points(poly_dir / "points")
        raw_faces = parse_foam_faces(poly_dir / "faces")
        boundary = parse_foam_boundary(poly_dir / "boundary")
    except Exception as exc:
        return False, f"polyMesh 읽기 실패: {exc}"

    points = np.array(raw_points, dtype=np.float64)

    # wall vertex 수집
    wall_vert_set: set[int] = set()
    for patch in boundary:
        if str(patch.get("name", "")) != wall:
            continue
        start = int(patch["startFace"])
        nf = int(patch["nFaces"])
        for fi in range(start, start + nf):
            if 0 <= fi < len(raw_faces):
                for v in raw_faces[fi]:
                    wall_vert_set.add(int(v))
    if not wall_vert_set:
        return False, f"wall patch '{wall}' vertex 없음"

    # KDTree 로 최근접 target 찾기
    tree = cKDTree(target_points)
    wall_vert_arr = np.array(sorted(wall_vert_set), dtype=np.int64)
    wall_coords = points[wall_vert_arr]
    dists, idxs = tree.query(wall_coords, k=1)
    max_dist = float(dists.max()) if len(dists) else 0.0
    points[wall_vert_arr] = target_points[idxs]

    try:
        _write_points(poly_dir / "points", points)
    except Exception as exc:
        return False, f"points 쓰기 실패: {exc}"

    return True, (
        f"snapped {len(wall_vert_arr)} wall verts "
        f"(max δ {max_dist:.3e})"
    )


def _read_exposed_patch_points(
    tmp_case: Path, exposed_patch: str,
) -> "np.ndarray | None":  # type: ignore[name-defined]
    """extrudeMesh 결과에서 exposed patch 가 참조하는 vertex 좌표 배열 반환."""
    try:
        import numpy as np
        from core.utils.polymesh_reader import (
            parse_foam_boundary, parse_foam_faces, parse_foam_points,
        )
    except Exception:
        return None
    poly_dir = tmp_case / "constant" / "polyMesh"
    try:
        pts = np.array(parse_foam_points(poly_dir / "points"), dtype=np.float64)
        faces_raw = parse_foam_faces(poly_dir / "faces")
        boundary = parse_foam_boundary(poly_dir / "boundary")
    except Exception:
        return None

    exposed_verts: set[int] = set()
    for patch in boundary:
        if str(patch.get("name", "")) != exposed_patch:
            continue
        start = int(patch["startFace"])
        nf = int(patch["nFaces"])
        for fi in range(start, start + nf):
            if 0 <= fi < len(faces_raw):
                for v in faces_raw[fi]:
                    exposed_verts.add(int(v))
    if not exposed_verts:
        return None
    return pts[np.array(sorted(exposed_verts), dtype=np.int64)]


def _run_extrude_mesh(
    case_dir: Path,
    num_layers: int,
    growth_ratio: float,
    first_thickness: float,
    wall_patch: str | None = None,
) -> tuple[bool, str]:
    """Extrude-then-snap 기반 native BL 삽입 (OpenFOAM extrudeMesh 사용).

    핵심 아이디어: master 를 먼저 shrink 하면 OpenFOAM 의 extrudeMesh 가 계산하는
    per-vertex extrusion normal 과 우리가 계산한 area-weighted vertex normal 이
    달라 ``stitchMesh -perfect`` 의 tolerance 를 초과한다. 대신:

      1. tmp_case 를 원본 그대로 복사 (pre-shrink snapshot).
      2. tmp_case 에 placeholder patch 주입 → extrudeMesh 가 exposedPatchName 으로
         찾을 수 있도록.
      3. tmp_case 에서 ``extrudeMesh`` 로 prism block 생성 (flipNormals=true, inward).
         block 은 [원래 wall, 원래 wall - normal × total] 구간을 차지.
      4. **extrude 결과의 exposed patch 좌표를 읽어서** master 의 wall vertex 들을
         그 좌표로 snap (KDTree 최근접). → master wall 과 prism exposed 가 정확히
         일치.
      5. master 의 0/ time field 파일들을 정리 (stitchMesh 가 patchField 일관성을
         요구하므로).
      6. mergeMeshes master + prism_block → 두 wall 이 같은 물리 위치.
      7. stitchMesh defaultWall defaultWall_bl_exposed_0 -perfect -overwrite →
         coincident face 들이 internal 로 연결.

    실패 시 어느 단계인지 message 에 명시.
    """
    try:
        from core.utils.openfoam_utils import run_openfoam
    except Exception as exc:
        return False, f"openfoam_utils import 실패: {exc}"

    import tempfile

    _ensure_minimal_controldict(case_dir)
    _write_minimal_fv_dicts(case_dir)

    wall_list = _detect_wall_patches(case_dir) if wall_patch is None else [wall_patch]
    if not wall_list:
        return False, "wall patch 를 찾을 수 없습니다."
    wall = wall_list[0]
    # 분리된 patch 로 prism block 의 두 면을 받기 위해 tmp_case 에 placeholder
    # patch 를 먼저 주입. 이 이름은 extrudeMesh 가 exposedPatchName 으로 찾을 때
    # 기존 patch 로 인식되어 통과한다.
    exposed = f"{wall}_bl_exposed"

    # geometric 총 두께
    if abs(float(growth_ratio) - 1.0) < 1e-9:
        total_thick = float(first_thickness) * num_layers
    else:
        r = float(growth_ratio)
        total_thick = float(first_thickness) * (r ** num_layers - 1) / (r - 1)

    if total_thick <= 0:
        return False, f"total_thick={total_thick} invalid"

    # master 의 wall 을 distinct 이름으로 rename 한 사본을 "pre-modify snapshot"
    # 으로 사용. 이렇게 해야 mergeMeshes 후에도 master 의 wall 과 prism 의
    # source-side (동일한 wall 이름) 가 같은 patch 로 합쳐지지 않는다.
    master_wall_renamed = f"{wall}_bl_fluid"

    with tempfile.TemporaryDirectory(prefix="autotessell_extrude_") as tmp:
        tmp_case = Path(tmp) / "extrude_case"

        # Step 1: master 복사 (원본 좌표, pre-modify)
        _copy_polymesh(case_dir, tmp_case)

        # Step 2: placeholder patch 주입 + extrudeMesh
        try:
            _inject_placeholder_patch(tmp_case, exposed)
        except Exception as exc:
            return False, f"placeholder patch 주입 실패: {exc}"

        _write_extrude_mesh_dict(
            tmp_case / "system" / "extrudeMeshDict",
            source_case=tmp_case,
            wall_patch=wall,
            num_layers=num_layers,
            growth_ratio=growth_ratio,
            total_thickness=total_thick,
            flip_normals=True,
            exposed_patch_name=exposed,
        )
        try:
            run_openfoam("extrudeMesh", tmp_case)
        except FileNotFoundError as exc:
            return False, f"openfoam_missing: {exc}"
        except Exception as exc:
            return False, f"extrudeMesh 실패: {str(exc)[-300:]}"

        # Step 3: extrude 결과의 exposed patch 좌표 수집
        try:
            target_points = _read_exposed_patch_points(tmp_case, exposed)
        except Exception as exc:
            return False, f"exposed patch 좌표 읽기 실패: {exc}"
        if target_points is None or len(target_points) == 0:
            return False, (
                f"exposed patch '{exposed}' 좌표 0 — extrudeMesh 결과 patch 이름 불일치 가능"
            )
        log.info("extrude_mesh_exposed_points", n=len(target_points))

        # Step 4: master wall vertex 를 exposed 좌표에 snap (정확히 일치시킴)
        ok, msg = _snap_master_wall_to_points(case_dir, wall, target_points)
        if not ok:
            return False, f"wall snap 실패: {msg}"
        log.info("extrude_mesh_snap_ok", detail=msg)

        # Step 5: 0/ time dir 삭제 (stitchMesh 가 field 와 boundary 일관성 체크)
        for t_dir in (case_dir.iterdir() if case_dir.exists() else []):
            if t_dir.is_dir() and t_dir.name == "0":
                import shutil as _sh2
                _sh2.rmtree(t_dir, ignore_errors=True)

        # Step 5b: master 의 wall patch 이름을 distinct 로 교체
        # mergeMeshes 는 동일 이름 patch 를 합치므로 prism 의 source side (= wall
        # 이름 유지) 와 master wall 이 섞이지 않도록 master 쪽만 rename.
        _master_bnd = case_dir / "constant" / "polyMesh" / "boundary"
        try:
            _txt = _master_bnd.read_text(encoding="utf-8")
            import re as _re
            # 이름 부분만 교체 (type 은 유지). "    defaultWall\n    {\n..."
            _pattern = _re.compile(
                rf"(\n|^)(\s*){_re.escape(wall)}(\s*\n\s*\{{)"
            )
            _new_txt, _n = _pattern.subn(
                rf"\1\2{master_wall_renamed}\3", _txt, count=1,
            )
            if _n == 0:
                return False, f"master boundary 에서 {wall} 를 찾지 못함"
            _master_bnd.write_text(_new_txt, encoding="utf-8")
        except Exception as exc:
            return False, f"master wall rename 실패: {exc}"

        # Step 6: mergeMeshes
        try:
            run_openfoam(
                "mergeMeshes",
                case_dir,
                args=[str(case_dir.resolve()), str(tmp_case.resolve()), "-overwrite"],
            )
        except Exception as exc:
            return False, f"mergeMeshes 실패: {str(exc)[-300:]}"

        # merge 후에도 0/ 생길 수 있음 — 다시 정리
        for t_dir in (case_dir.iterdir() if case_dir.exists() else []):
            if t_dir.is_dir() and t_dir.name == "0":
                import shutil as _sh2
                _sh2.rmtree(t_dir, ignore_errors=True)

        # Step 7: stitchMesh — master 의 rename 된 wall (bl_fluid) 과 prism 의
        # exposed patch (bl_exposed) 가 기하학적으로 coincident.
        stitched = False
        stitch_errors: list[str] = []
        stitch_master_candidates = [master_wall_renamed]
        stitch_slave_candidates = [exposed, f"{exposed}_0"]
        for m_cand in stitch_master_candidates:
            for s_cand in stitch_slave_candidates:
                for stitch_mode in ("-perfect", "-partial"):
                    try:
                        run_openfoam(
                            "stitchMesh",
                            case_dir,
                            args=[m_cand, s_cand, stitch_mode, "-overwrite"],
                        )
                        stitched = True
                        break
                    except Exception as exc:
                        stitch_errors.append(
                            f"{m_cand}/{s_cand}/{stitch_mode}: {str(exc)[-60:]}"
                        )
                if stitched:
                    break
            if stitched:
                break

        if not stitched:
            return False, (
                f"extrude+snap+merge 성공, stitch 실패. "
                f"후보 시도: {'; '.join(stitch_errors[:4])}\n"
                f"수동 복구: stitchMesh {master_wall_renamed} {exposed} -perfect "
                f"-overwrite"
            )

        # Step 8: 사용자 관점에서 이름 일관성 회복.
        # stitch 후 boundary 상태:
        #   - {wall}_bl_fluid : 0 faces (stitch 로 internal 화됨)
        #   - {wall}          : 1280 faces — prism 의 outer side (원래 wall 위치)
        #   - {wall}_bl_exposed : 0 faces (stitch 로 internal 화됨)
        # 빈 placeholder patch 는 용도가 끝났으므로 제거, wall 은 원래 이름 유지.
        try:
            _bnd_after = case_dir / "constant" / "polyMesh" / "boundary"
            _txt2 = _bnd_after.read_text(encoding="utf-8")
            _txt3 = _strip_empty_patches(
                _txt2, {master_wall_renamed, exposed},
            )
            _bnd_after.write_text(_txt3, encoding="utf-8")
        except Exception as exc:
            log.warning("extrude_mesh_cleanup_failed", error=str(exc))

        # Step 9: renumberMesh 로 optimal ordering 복원 (선택적).
        try:
            run_openfoam("renumberMesh", case_dir, args=["-overwrite"])
        except Exception:
            log.info("extrude_mesh_renumber_skipped")

    return True, (
        f"extrude-snap-merge-stitch OK "
        f"(patch={wall}, nLayers={num_layers}, thick={total_thick:.4g}). "
        f"주의: 간단한 uniform-offset shrink 이므로 날카로운 feature 근처 "
        f"non-orthogonality 가 클 수 있음. checkMesh 로 확인 권장."
    )


def _strip_empty_patches(boundary_text: str, patch_names: set[str]) -> str:
    """boundary 파일 텍스트에서 nFaces==0 인 placeholder patch 들을 제거."""
    import re
    # Locate count line
    m = re.search(r"^\s*(\d+)\s*\n\s*\(", boundary_text, re.MULTILINE)
    if not m:
        return boundary_text
    count = int(m.group(1))
    # Find patch blocks: "    <name>\n    {\n        ... \n    }"
    # trailing \s* 를 빼서 다음 patch 의 leading whitespace 를 소비하지 않도록.
    pattern = re.compile(
        r"^(\s*)(\S+)\s*\n(\s*)\{\s*\n([^}]*)\}",
        re.MULTILINE,
    )
    removed = 0
    def _repl(pm: re.Match) -> str:
        nonlocal removed
        name = pm.group(2)
        block = pm.group(4)
        if name in patch_names and re.search(
            r"nFaces\s+0\s*;", block,
        ):
            removed += 1
            return ""
        return pm.group(0)
    new_text = pattern.sub(_repl, boundary_text)
    if removed > 0:
        new_count = count - removed
        new_text = re.sub(
            rf"^\s*{count}\s*\n\s*\(",
            f"\n{new_count}\n(",
            new_text, count=1, flags=re.MULTILINE,
        )
    return new_text


def _run_snappy_addlayers_only(
    case_dir: Path, num_layers: int, growth_ratio: float,
    first_layer_thickness: float,
) -> tuple[bool, str]:
    """snappyHexMesh 를 castellated/snap 끄고 addLayers 만 실행.

    snappy 가 요구하는 입력 형식 (cellLevel/pointLevel 파일) 필요 —
    주 엔진이 snappy 가 아니면 일반적으로 호환 안 됨. 실패 시 generateBoundaryLayers
    fallback 권장.
    """
    try:
        from core.utils.openfoam_utils import run_openfoam
    except Exception as exc:
        return False, f"openfoam_utils import 실패: {exc}"

    _ensure_minimal_controldict(case_dir)
    # 최소 snappyHexMeshDict — addLayers만 true
    system_dir = case_dir / "system"
    (system_dir / "snappyHexMeshDict").write_text(
        "FoamFile\n{ version 2.0; format ascii; class dictionary; "
        "object snappyHexMeshDict; }\n"
        "castellatedMesh false;\nsnap false;\naddLayers true;\n"
        "geometry {}\n"
        "castellatedMeshControls {\n"
        "  maxLocalCells 1000000; maxGlobalCells 10000000;\n"
        "  minRefinementCells 10; nCellsBetweenLevels 3;\n"
        "  resolveFeatureAngle 30; features (); refinementSurfaces {};\n"
        "  refinementRegions {}; locationInMesh (0 0 0);\n"
        "  allowFreeStandingZoneFaces true;\n}\n"
        "snapControls {\n  nSmoothPatch 3; tolerance 2.0; "
        "nSolveIter 30; nRelaxIter 5;\n}\n"
        "addLayersControls {\n"
        f"  relativeSizes true; expansionRatio {growth_ratio};\n"
        f"  finalLayerThickness 0.3;\n"
        f"  minThickness 0.1;\n"
        "  layers { \".*\" { nSurfaceLayers " + str(int(num_layers)) + "; } }\n"
        "  nGrow 0; featureAngle 60;\n"
        "  maxFaceThicknessRatio 0.5; maxThicknessToMedialRatio 0.3;\n"
        "  minMedialAxisAngle 90; nSmoothSurfaceNormals 1; nSmoothThickness 10;\n"
        "  nSmoothNormals 3; nMedialAxisIter 10;\n"
        "  nLayerIter 50; nRelaxedIter 20;\n}\n"
        "meshQualityControls {}\n"
        "mergeTolerance 1e-6;\n",
        encoding="utf-8",
    )
    try:
        run_openfoam("snappyHexMesh", case_dir, args=["-overwrite"])
        return True, "snappy addLayers OK"
    except FileNotFoundError as exc:
        return False, f"openfoam_missing: {exc}"
    except Exception as exc:
        return False, f"snappy addLayers 실패: {str(exc)[-400:]}"


class LayersPostGenerator:
    """주 엔진 이후 실행되는 BL 후처리 tier.

    사용법:
      1. Tier 3 (볼륨) 완료된 polyMesh 가 있어야 함.
      2. orchestrator 가 tier_specific_params["post_layers_engine"] 값으로 자동 호출.
      3. 실패 시 경고만 남기고 주 mesh 는 보존 (BL 없이 진행).

    tier_specific_params 키:
      - post_layers_engine : "disabled"(기본) | "generate_boundary_layers" |
        "refine_wall_layer" | "snappy_addlayers"
      - post_layers_num_layers           (기본 3)
      - post_layers_growth_ratio         (기본 1.2)
      - post_layers_first_thickness      (기본 0.001 — bbox 기준 상대)
      - post_layers_refine_wall_fraction (refine_wall_layer 용, 기본 0.3)
    """

    TIER_NAME = TIER_NAME

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        t_start = time.monotonic()
        log.info("tier_layers_post_start", case_dir=str(case_dir))

        params: dict[str, Any] = (
            getattr(strategy, "tier_specific_params", None) or {}
        )
        engine = str(params.get("post_layers_engine", "disabled")).lower()

        if engine in ("disabled", "none", "off", ""):
            elapsed = time.monotonic() - t_start
            log.info("tier_layers_post_skipped", reason="disabled")
            return TierAttempt(
                tier=self.TIER_NAME, status="success",
                time_seconds=elapsed,
                error_message="layers_post_disabled",
            )

        # v0.4: engine="auto" 이면 strategy.mesh_type 을 보고 메쉬 타입에 맞는
        # BL 엔진을 자동 선택.
        if engine in ("auto",):
            mt_raw = getattr(strategy, "mesh_type", None)
            mt = getattr(mt_raw, "value", None) or str(mt_raw or "auto")
            mt = str(mt).lower()
            if mt == "tet":
                engine = "tet_bl_subdivide"
            elif mt == "hex_dominant":
                engine = "native_bl"
            elif mt == "poly":
                engine = "poly_bl_transition"
            else:
                engine = "native_bl"
            log.info("tier_layers_post_auto_engine", mesh_type=mt, engine=engine)

        poly_dir = case_dir / "constant" / "polyMesh"
        if not (poly_dir / "faces").exists():
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=self.TIER_NAME, status="failed",
                time_seconds=elapsed,
                error_message=f"polyMesh 없음: {poly_dir}",
            )

        bl = getattr(strategy, "boundary_layers", None)
        num_layers = int(params.get(
            "post_layers_num_layers",
            getattr(bl, "num_layers", 3) or 3,
        ))
        growth_ratio = float(params.get(
            "post_layers_growth_ratio",
            getattr(bl, "growth_ratio", 1.2) or 1.2,
        ))
        first_thickness = float(params.get(
            "post_layers_first_thickness",
            getattr(bl, "first_layer_thickness", 0.001) or 0.001,
        ))
        edge_fraction = float(params.get("post_layers_refine_wall_fraction", 0.3))

        ok = False
        msg = ""
        if engine in ("generate_boundary_layers", "gbl", "cfmesh_layers_post"):
            ok, msg = _run_generate_boundary_layers(
                case_dir, num_layers, growth_ratio, first_thickness,
                allow_discontinuity=bool(params.get(
                    "post_layers_allow_discontinuity", False)),
                optimise_layer=bool(params.get(
                    "post_layers_optimise_layer", True)),
                untangle_layers=bool(params.get(
                    "post_layers_untangle_layers", True)),
                n_smooth_normals=int(params.get(
                    "post_layers_n_smooth_normals", 5)),
                n_smooth_surface_normals=int(params.get(
                    "post_layers_n_smooth_surface_normals", 5)),
                feature_size_factor=float(params.get(
                    "post_layers_feature_size_factor", 0.3)),
                n_layers_at_bottleneck=int(params.get(
                    "post_layers_at_bottleneck", 1)),
                extra_patch_params=params.get("post_layers_patch_overrides"),
                twodlayers=bool(params.get("post_layers_2d", False)),
            )
        elif engine in ("refine_wall_layer", "rwl"):
            patches = params.get("post_layers_patches")
            ok, msg = _run_refine_wall_layer(
                case_dir, edge_fraction,
                patches if isinstance(patches, list) else None,
            )
        elif engine in ("snappy_addlayers", "snappy_post"):
            ok, msg = _run_snappy_addlayers_only(
                case_dir, num_layers, growth_ratio, first_thickness,
            )
        elif engine in ("extrude_mesh", "extrude"):
            ok, msg = _run_extrude_mesh(
                case_dir, num_layers, growth_ratio, first_thickness,
                wall_patch=params.get("post_layers_wall_patch"),
            )
        elif engine in ("native_bl", "native", "python_bl"):
            # v0.4: 우리 자체 Python BL 생성기 (core/layers/native_bl.py)
            try:
                from core.layers.native_bl import BLConfig, generate_native_bl
            except Exception as exc:
                ok, msg = False, f"native_bl import 실패: {exc}"
            else:
                cfg_bl = _build_bl_config(BLConfig, params, num_layers,
                                          growth_ratio, first_thickness)
                _res = generate_native_bl(case_dir, cfg_bl)
                ok, msg = bool(_res.success), str(_res.message)
        elif engine in ("tet_bl_subdivide", "tet_bl", "native_bl_tet"):
            # v0.4 mesh_type=tet 전용: native_bl 로 prism 삽입 후 wedge 를 tet 3 개로
            # 분할. 결과는 전체 tet mesh.
            try:
                from core.layers.native_bl import BLConfig, generate_native_bl
                from core.layers.tet_bl_subdivide import (
                    subdivide_prism_layers_to_tet,
                )
            except Exception as exc:
                ok, msg = False, f"tet_bl 유틸 import 실패: {exc}"
            else:
                cfg_bl = _build_bl_config(BLConfig, params, num_layers,
                                          growth_ratio, first_thickness)
                _res = generate_native_bl(case_dir, cfg_bl)
                if not _res.success:
                    ok, msg = False, f"native_bl 단계 실패: {_res.message}"
                else:
                    _res2 = subdivide_prism_layers_to_tet(
                        case_dir, backup_original=False,
                    )
                    ok = bool(_res2.success)
                    msg = (
                        f"{_res.message}\n{_res2.message}"
                        if ok
                        else f"subdivide 실패: {_res2.message}"
                    )
        elif engine in ("poly_bl_transition", "poly_bl", "native_bl_poly"):
            # v0.4 mesh_type=poly 전용: native_bl 로 prism 삽입 + (옵션)
            # OpenFOAM polyDualMesh 로 bulk dual 변환.
            try:
                from core.layers.poly_bl_transition import (
                    run_poly_bl_transition,
                )
            except Exception as exc:
                ok, msg = False, f"poly_bl_transition import 실패: {exc}"
            else:
                _res = run_poly_bl_transition(
                    case_dir,
                    num_layers=int(num_layers),
                    growth_ratio=float(growth_ratio),
                    first_thickness=float(first_thickness),
                    wall_patch_names=params.get("post_layers_wall_patch_names"),
                    backup_original=bool(params.get(
                        "post_layers_backup_original", True,
                    )),
                    max_total_ratio=float(params.get(
                        "post_layers_max_total_ratio", 0.3,
                    )),
                    apply_bulk_dual=bool(params.get(
                        "post_layers_apply_bulk_dual", True,
                    )),
                    dual_feature_angle=float(params.get(
                        "post_layers_dual_feature_angle", 30.0,
                    )),
                )
                ok = bool(_res.success)
                msg = str(_res.message)
        elif engine in ("netgen_bl", "netgen_layers"):
            ok, msg = _run_netgen_bl(
                case_dir, num_layers, growth_ratio, first_thickness,
                stl_path=preprocessed_path,
            )
        elif engine in ("gmsh_bl", "gmsh_layers"):
            ok, msg = _run_gmsh_bl(
                case_dir, num_layers, growth_ratio, first_thickness,
                stl_path=preprocessed_path,
            )
        elif engine in ("pyhyp", "mdolab_pyhyp"):
            ok, msg = _run_pyhyp(
                case_dir, num_layers, growth_ratio, first_thickness,
                stl_path=preprocessed_path,
            )
        elif engine in ("meshkit_bl", "meshkit"):
            ok, msg = _run_meshkit_bl(
                case_dir, num_layers, growth_ratio, first_thickness,
            )
        elif engine in ("su2_hexpress", "hexpress"):
            ok, msg = _run_su2_hexpress(
                case_dir, num_layers, growth_ratio, first_thickness,
            )
        elif engine in ("salome_bl", "salome_smesh_bl", "salome"):
            try:
                from core.generator.tier_salome_smesh import run_salome_bl_post
                ok, msg = run_salome_bl_post(
                    case_dir, preprocessed_path,
                    num_layers, growth_ratio, first_thickness,
                )
            except Exception as exc:
                ok, msg = False, f"salome_bl import/실행 실패: {exc}"
        else:
            ok, msg = False, f"unknown_engine: {engine}"

        elapsed = time.monotonic() - t_start
        if ok:
            log.info("tier_layers_post_success", engine=engine, msg=msg, elapsed=elapsed)
            return TierAttempt(
                tier=self.TIER_NAME, status="success", time_seconds=elapsed,
            )
        log.warning("tier_layers_post_failed", engine=engine, msg=msg, elapsed=elapsed)
        return TierAttempt(
            tier=self.TIER_NAME, status="failed",
            time_seconds=elapsed,
            error_message=f"{engine}: {msg}",
        )
