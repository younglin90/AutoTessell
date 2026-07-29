---
type: development
status: active
updated: 2026-07-26
stability: implemented
source_paths: [pyproject.toml, auto_tessell_core/CMakeLists.txt, auto_tessell_core/build_extensions.sh]
tags: [build, dependencies, cpp, python]
---

# 빌드와 의존성

## Python package

`pyproject.toml`은 Python 3.12+, Click/Rich/Pydantic/Structlog, NumPy/SciPy, compatibility용 trimesh/meshio/PyVista를 선언한다. Optional group은 legacy preprocessing, CAD, Netgen, desktop, PyTetWild, AI, evaluator, generator, OpenFOAM case, 추가 preprocessing 도구를 제공한다. Entry point는 `auto-tessell`, `auto-tessell-qt`다.

## Native code

`auto_tessell_core/CMakeLists.txt`의 project baseline은 C++17이고 일부 native metric/topology/snap/hex-quality target은 C++23을 요구한다. Pybind11 target에는 다음이 있다.

- native metric과 polyMesh topology
- native snap candidate와 hex quality
- optional RobustHex/cinolib
- source가 있으면 vendored fTetWild/cfMesh binding
- working-tree의 native tet predicate/qopt와 surface-padding 추가

Bundled Shewchuk library는 별도로 첫 import 때 `ctypes`용 shared library를 만들며 FMA contraction을 끈다.

Native-first는 AutoTessell이 제품 계약을 소유하고 외부 parsing/meshing을 점진적으로 대체한다는 뜻이다. 현재는 dependency-free가 아니다. SciPy Delaunay, trimesh-compatible object, meshio export, OpenFOAM binary, reference engine 경계가 남아 있다.

빌드는 플랫폼에 민감하다. WSL과 Windows Python은 package와 compiled extension을 공유하지 않으므로 의도한 interpreter를 명시해야 한다.
