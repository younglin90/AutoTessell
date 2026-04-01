# Changelog

## [0.1.0] - 2026-04-01

### Added
- 5-Agent pipeline: Analyzer → Preprocessor → Strategist → Generator ↔ Evaluator
- 2-Phase Progressive meshing: Surface (L1→L2→L3) + Volume (Draft/Standard/Fine)
- QualityLevel system (draft/standard/fine) with differentiated thresholds
- PolyMeshWriter: tet mesh → OpenFOAM polyMesh without external tools
- NativeMeshChecker: OpenFOAM-free mesh quality validation
- Geometry Fidelity: Hausdorff distance-based surface deviation check
- STEP/IGES CAD support via cadquery + gmsh fallback
- CLI: `auto-tessell run input.stl -o ./case --quality draft|standard|fine`
- Rich terminal output with quality report tables
- FastAPI WebSocket server for desktop GUI communication
- Godot 4.3 desktop GUI project (3D mesh viewer, progress tracking)
- OpenFOAM auto-detection (/usr/lib/openfoam/, /opt/, OPENFOAM_DIR)
- Retry strategy with meaningful parameter adjustments on FAIL
- PyInstaller packaging support
- Docker + docker-compose for reproducible builds
- GitHub Actions CI/CD
- 380+ tests (unit + integration + benchmark)

### Supported Input Formats
- Mesh: STL, OBJ, PLY, OFF, 3MF
- CAD: STEP, IGES, BREP
- CFD: Gmsh .msh, VTK/VTU, Fluent .msh, Nastran, Abaqus

### Volume Mesh Engines
- Draft: TetWild (pytetwild) — ~1 second
- Standard: Netgen / cfMesh — ~minutes
- Fine: snappyHexMesh + BL / MMG — ~30 minutes+
