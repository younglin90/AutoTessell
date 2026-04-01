# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Auto-Tessell Desktop.

Bundles the FastAPI WebSocket server + core meshing pipeline into a single executable.
Usage:
    pyinstaller auto_tessell.spec
    # Output: dist/auto-tessell/auto-tessell.exe (or auto-tessell on Linux)
"""

import sys
from pathlib import Path

block_cipher = None

# Collect hidden imports for mesh libraries
hidden_imports = [
    # Core
    "core",
    "core.analyzer",
    "core.analyzer.file_reader",
    "core.analyzer.geometry_analyzer",
    "core.preprocessor",
    "core.preprocessor.pipeline",
    "core.preprocessor.repair",
    "core.preprocessor.remesh",
    "core.preprocessor.converter",
    "core.strategist",
    "core.strategist.tier_selector",
    "core.strategist.param_optimizer",
    "core.strategist.strategy_planner",
    "core.generator",
    "core.generator.pipeline",
    "core.generator.polymesh_writer",
    "core.generator.tier0_core",
    "core.generator.tier05_netgen",
    "core.generator.tier1_snappy",
    "core.generator.tier15_cfmesh",
    "core.generator.tier2_tetwild",
    "core.generator.openfoam_writer",
    "core.evaluator",
    "core.evaluator.quality_checker",
    "core.evaluator.native_checker",
    "core.evaluator.metrics",
    "core.evaluator.report",
    "core.evaluator.fidelity",
    "core.pipeline",
    "core.pipeline.orchestrator",
    "core.utils",
    "core.utils.logging",
    "core.utils.openfoam_utils",
    "core.utils.polymesh_reader",
    "core.schemas",
    "desktop",
    "desktop.server",
    "cli",
    "cli.main",
    # Third-party
    "trimesh",
    "meshio",
    "pyvista",
    "pymeshfix",
    "pyacvd",
    "numpy",
    "scipy",
    "pydantic",
    "structlog",
    "click",
    "rich",
    "fastapi",
    "uvicorn",
    "starlette",
    "websockets",
]

# Optional: add these if installed
try:
    import pytetwild
    hidden_imports.append("pytetwild")
except ImportError:
    pass

try:
    import netgen
    hidden_imports.extend(["netgen", "netgen.meshing", "netgen.stl", "netgen.occ"])
except ImportError:
    pass

try:
    import cadquery
    hidden_imports.append("cadquery")
except ImportError:
    pass

try:
    import gmsh
    hidden_imports.append("gmsh")
except ImportError:
    pass

a = Analysis(
    ["desktop/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=[
        # Include benchmark STLs for testing
        ("tests/benchmarks/sphere.stl", "tests/benchmarks"),
        ("tests/benchmarks/box.step", "tests/benchmarks"),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy optional deps unless needed
        "torch",
        "meshgpt_pytorch",
        "open3d",
        "matplotlib",
        "IPython",
        "notebook",
        "tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="auto-tessell",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Console app (server mode)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="auto-tessell",
)
