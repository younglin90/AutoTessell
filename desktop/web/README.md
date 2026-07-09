# Auto-Tessell — Web GUI

A browser version of the Qt desktop GUI. Same 5-agent pipeline, same
`mesh_type` (tet / hex_dominant / poly) × quality flow, in any modern browser.

## Run

```bash
# from the repo root
./start_web_gui.sh            # Linux / WSL / macOS  (start_web_gui.bat on Windows)
# …or directly:
python -m desktop.server      # then open http://localhost:9720/
```

Open **http://localhost:9720/** in a browser.

## How it works

```
 Browser (desktop/web/)                FastAPI server (desktop/server.py)
 ┌────────────────────┐   POST /upload   ┌────────────────────────────┐
 │ index.html         │ ───────────────▶ │ /upload    → job_id        │
 │ app.js  (controller)│                  │ /jobs/{id}/surface  (STL)  │
 │ viewer.js (WebGL)  │ ◀─ WS /ws/mesh ─▶ │ /ws/mesh/{id}              │
 │ styles.css         │                  │   → orchestrator.run(...)  │
 └────────────────────┘   GET /…/mesh    │ /jobs/{id}/mesh   (JSON)   │
        ▲ Three-less WebGL │ ◀─────────── │ /jobs/{id}/download/…zip   │
        └─ jet colormap    │              └────────────────────────────┘
```

- **No build step, no Node.js, no external JS libraries.** The 3D viewer
  (`viewer.js`) is a hand-written WebGL renderer (orbit/zoom/pan, flat shading,
  wireframe, jet quality colormap) — consistent with the project policy of not
  depending on third-party libraries. It parses both binary and ASCII STL for
  the surface preview and renders polyMesh boundary faces for the result.
- The server drives the **same `orchestrator.run()`** entry point the Qt GUI
  uses, so `mesh_type`-specific boundary layers / post-processing match the
  desktop output. A thread→WebSocket bridge streams live progress + logs.
- The same `AUTO_TESSELL_*` defaults (`desktop/default_env.py`) are applied, so
  a mesh built from the browser matches the Windows GUI bit-for-bit.

## Features

| Area        | Web GUI |
|-------------|---------|
| Input       | Drag-drop / click upload (STL, OBJ, PLY, OFF, 3MF, STEP, IGES, BREP, MSH) with upload progress; STEP/IGES get a server-tessellated preview |
| Mesh type   | auto / tet / hex_dominant / poly |
| Quality     | draft / standard / fine |
| Engine      | auto + native_tet/hex/poly + reference tiers |
| Params      | max cells, BL layers, element/base cell size, retries + advanced (engines, flags, dry-run) |
| 3D viewer   | surface ↔ result toggle, orbit/zoom/pan (+touch), wireframe, colormap (solid/patch/aspect/skewness/**non-ortho** from the server) |
| Live status | progress bar, filterable log console, KPI overlay (verdict/tier/cells/non-ortho/skewness) |
| Cancel      | **Stop** cancels the running pipeline cooperatively (server aborts at its next step) |
| Output      | `polyMesh.zip` + **multi-format export** (VTU/VTK/Fluent/CGNS/SU2/Nastran/Tecplot/STL/OBJ/PLY) |

## Notes

- The viewer's **aspect** / **skewness** colormaps are computed per boundary
  triangle on the client (face-local metrics). The **non-ortho** colormap uses
  real per-boundary-face values computed by the server
  (`GET /jobs/{id}/mesh?quality=1`, reusing the NativeMeshChecker geometry), so
  it lines up with the KPI overlay's max non-ortho.
- Multi-format export (`GET /jobs/{id}/export?format=…`) reuses
  `core/utils/mesh_exporter.py`; it needs `meshio` installed. STEP/IGES preview
  needs one of OCP / cadquery / gmsh — without them, upload still works and the
  surface preview is simply unavailable until the mesh is generated.
- A **FAIL** verdict still loads the generated mesh into the viewer and enables
  download, so you can inspect why a mesh missed the quality gate — same as the
  desktop GUI.
- **Stop** closes the WebSocket; a meshing stage already running in the worker
  thread may finish in the background before the job is dropped.
