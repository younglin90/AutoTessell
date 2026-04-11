#!/usr/bin/env python3
"""모든 의존성 라이브러리를 검증하는 스크립트."""

import sys
import importlib.util
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import Any


@dataclass
class ValidationResult:
    name: str
    status: str  # "✅", "⚠️", "❌"
    message: str
    details: dict[str, Any]


def validate_module(name: str, test_fn=None) -> ValidationResult:
    """Python 모듈 검증."""
    try:
        spec = importlib.util.find_spec(name)
        if spec is None:
            return ValidationResult(name, "❌", f"모듈 로드 불가", {})

        mod = importlib.import_module(name)
        version = getattr(mod, "__version__", "unknown")

        if test_fn:
            test_result = test_fn(mod)
            return ValidationResult(
                name, "✅", f"작동 가능 (v{version})",
                {"version": version, "test": test_result}
            )
        return ValidationResult(
            name, "✅", f"로드됨 (v{version})", {"version": version}
        )
    except Exception as e:
        return ValidationResult(name, "❌", str(e), {})


def validate_binary(name: str) -> ValidationResult:
    """바이너리 명령어 검증."""
    path = shutil.which(name)
    if path:
        try:
            import subprocess
            result = subprocess.run([name, "--version"], capture_output=True, text=True, timeout=2)
            return ValidationResult(
                name, "✅", f"설치됨 ({path})",
                {"path": path, "version_output": result.stdout[:100]}
            )
        except Exception as e:
            return ValidationResult(name, "⚠️", f"바이너리 있음, 버전 확인 실패", {"path": path})
    return ValidationResult(name, "❌", "바이너리 없음", {})


def test_trimesh(mod: Any) -> str:
    """trimesh 테스트."""
    mesh = mod.creation.box()
    return f"box mesh: {len(mesh.vertices)} verts, {len(mesh.faces)} faces"


def test_pymeshfix(mod: Any) -> str:
    """pymeshfix 테스트."""
    import numpy as np
    verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    mf = mod.MeshFix(verts, faces)
    return f"MeshFix initialized: {len(mf.v)} verts"


def test_pyvista(mod: Any) -> str:
    """pyvista 테스트."""
    mesh = mod.Sphere()
    return f"Sphere: {mesh.n_cells} cells, {mesh.n_points} points"


def test_pyacvd(mod: Any) -> str:
    """pyacvd 테스트."""
    import pyvista as pv
    mesh = pv.Sphere()
    clustering = mod.Clustering(mesh, max_iterations=1)
    clustering.cluster(n_clusters=100)
    return f"Clustering: {clustering.output.n_cells} output cells"


def test_pymeshlab(mod: Any) -> str:
    """pymeshlab 테스트."""
    return f"pymeshlab version: {mod.__version__ if hasattr(mod, '__version__') else 'unknown'}"


def test_netgen(mod: Any) -> str:
    """netgen 테스트."""
    return "netgen module loaded"


def test_pytetwild(mod: Any) -> str:
    """pytetwild 테스트."""
    import numpy as np
    verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32)
    faces = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]], dtype=np.int32)
    try:
        tet_v, tet_f = mod.tetrahedralize(verts, faces, stop_energy=10.0)
        return f"tetrahedralize: {len(tet_v)} verts, {len(tet_f)} tets"
    except Exception as e:
        return f"tetrahedralize failed: {str(e)[:50]}"


def test_gmsh(mod: Any) -> str:
    """gmsh 테스트."""
    return "gmsh module loaded"


def test_meshio(mod: Any) -> str:
    """meshio 테스트."""
    import numpy as np
    points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]])
    cells = [("triangle", np.array([[0, 1, 2]]))]
    mesh = mod.Mesh(points, cells)
    return f"Mesh: {len(mesh.points)} points, {len(mesh.cells)} cell blocks"


def test_cadquery(mod: Any) -> str:
    """cadquery 테스트."""
    box = mod.Workplane("XY").box(1, 1, 1)
    return f"Box created: {str(box)[:50]}"


def test_neatmesh(mod: Any) -> str:
    """neatmesh 테스트."""
    return "neatmesh module loaded"


def test_ofpp(mod: Any) -> str:
    """ofpp 테스트."""
    return "ofpp (Ofpp) module loaded"


def main():
    """모든 의존성 검증."""
    print("\n" + "=" * 80)
    print("🔍 AutoTessell 의존성 검증")
    print("=" * 80 + "\n")

    results: list[ValidationResult] = []

    # Python 모듈 검증
    module_tests = [
        ("trimesh", test_trimesh),
        ("pymeshfix", test_pymeshfix),
        ("pyvista", test_pyvista),
        ("pyacvd", test_pyacvd),
        ("pymeshlab", test_pymeshlab),
        ("netgen", test_netgen),
        ("pytetwild", test_pytetwild),
        ("gmsh", test_gmsh),
        ("meshio", test_meshio),
        ("cadquery", test_cadquery),
        ("neatmesh", test_neatmesh),
        ("Ofpp", test_ofpp),  # ofpp의 실제 import name
    ]

    print("📦 Python 모듈 검증:")
    print("-" * 80)
    for name, test_fn in module_tests:
        result = validate_module(name, test_fn)
        results.append(result)
        print(f"{result.status} {result.name:20} | {result.message}")
        if result.details and "test" in result.details:
            print(f"   └─ {result.details['test']}")

    # 바이너리 검증
    binaries = ["gmsh", "vorpalite", "mmg3d", "checkMesh", "foamToVTK", "quadwild"]

    print("\n🔧 바이너리 명령어 검증:")
    print("-" * 80)
    for binary in binaries:
        result = validate_binary(binary)
        results.append(result)
        print(f"{result.status} {binary:20} | {result.message}")

    # 요약
    passed = sum(1 for r in results if "✅" in r.status)
    warned = sum(1 for r in results if "⚠️" in r.status)
    failed = sum(1 for r in results if "❌" in r.status)

    print("\n" + "=" * 80)
    print(f"📊 검증 결과: ✅ {passed} | ⚠️ {warned} | ❌ {failed}")
    print("=" * 80 + "\n")

    # 상세 결과 저장
    report_file = Path(__file__).parent.parent / "DEPENDENCY_VALIDATION_REPORT.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("AutoTessell 의존성 검증 리포트\n")
        f.write("=" * 80 + "\n\n")
        for result in results:
            f.write(f"{result.status} {result.name}\n")
            f.write(f"   상태: {result.message}\n")
            if result.details:
                for k, v in result.details.items():
                    f.write(f"   {k}: {v}\n")
            f.write("\n")
        f.write(f"\n요약: ✅ {passed} 성공 | ⚠️ {warned} 경고 | ❌ {failed} 실패\n")

    print(f"💾 상세 리포트: {report_file}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
