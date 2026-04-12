# AutoTessell Qt Desktop GUI

Production-ready Qt (PySide6) desktop application for autonomous CAD/mesh → OpenFOAM polyMesh generation.

## Quick Start

### Installation

```bash
# Ensure PySide6 is installed
pip install PySide6>=6.0

# From the AutoTessell root directory:
python3 desktop/qt_main.py
```

### Supported Platforms

- **Linux (WSL2)**: Full support ✅
- **Windows Native**: Partial support ⚠️ (OpenFOAM evaluation unavailable)
- **macOS**: Untested (theoretically supported)

## Features

### Input/Output Management
- **File Selection**: Browse and select STL, STEP, IGES, OBJ, PLY, OFF, 3MF, BREP files
- **Drag-Drop**: Drag STL/CAD files directly onto the drop zone
- **Output Directory**: Configure output folder for generated polyMesh
- **Open Results**: One-click folder access to generated meshes

### Mesh Generation Controls
- **Quality Levels**: Draft, Standard, Fine
- **Tier Selection**: auto (default), core, netgen, snappy, cfmesh, tetwild
- **Max Iterations**: 1-10 (fallback chain depth)
- **Dry-Run**: Test pipeline without mesh generation
- **Clear Parameters**: Reset all settings to defaults

### Parameter Fine-Tuning

#### Surface Remesh (L2)
- `element_size`: Global cell size override (default: auto)
- `max_cells`: Total cell count limit (default: none)

#### TetWild (Draft)
- `epsilon`: Robustness parameter (small=conservative, default: auto)
- `edge_length`: Edge length target (default: auto)
- `max_iterations`: Optimization iterations (default: 80)

#### Netgen (Standard)
- `grading`: Mesh grading ratio (0.3=aggressive, default)
- `curvaturesafety`: Curvature factor (default: 2.0)
- `max_h`: Maximum element size (default: auto)
- `min_h`: Minimum element size (default: auto)

#### snappyHexMesh (Fine)
- `snap_tolerance`: Surface snapping tolerance (default: auto)
- `snap_iterations`: Snapping iterations (default: auto)
- `castellated_level`: Refinement levels (e.g., "2,3")
- `max_local_cells`: Local cell limit (default: 1M)
- `max_global_cells`: Global cell limit (default: 10M)

#### MMG (Fine)
- `hmin`: Minimum edge length
- `hmax`: Maximum edge length
- `hgrad`: Size gradation ratio
- `hausd`: Hausdorff distance

### Progress & Results

- **Real-time Progress Bar**: 0-100% mesh generation progress
- **Status Display**: "Running X%" → "PASS" or "FAIL"
- **Execution Time**: Total time displayed on completion
- **Log Output**: Detailed pipeline log with timestamps
- **Error Messages**: Clear error reporting on failure

### Help System

- **Parameter Help**: Click "i" button next to any parameter
- **Tooltip Descriptions**: Hover over controls for quick info
- **Metadata Display**: View parameter type, default, and usage notes

## Architecture

### Components

```
desktop/
├── qt_main.py                 # Entry point
├── qt_app/
│   ├── main_window.py        # 804-line main window (Qt UI)
│   └── pipeline_worker.py    # QThread worker for mesh generation
├── server.py                  # FastAPI backend (optional)
└── __main__.py               # Python -m support
```

### Data Flow

```
User Input
    ↓
[Qt UI] main_window.py
    ↓
[Worker] PipelineWorker (QThread)
    ↓
[Backend] core.pipeline.orchestrator
    ↓
[Result] ✅ polyMesh or ❌ Error Message
```

### Threading Model

- **Main Thread**: Qt GUI event loop, user interactions
- **Worker Thread**: Pipeline execution (non-blocking UI)
- **Signals**: Progress updates, completion, error reporting

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+O | Open input file |
| Ctrl+S | Select output directory |
| Ctrl+R / Enter | Run pipeline |
| Ctrl+L | Clear log |
| Ctrl+Q | Quit application |

## Configuration

### Environment Variables

```bash
# Set OpenFOAM root (if using native evaluation)
export OPENFOAM_ROOT=/opt/openfoam2406

# Set temporary directory for large meshes
export TMPDIR=/fast/ssd/tmp

# Enable debug logging
export LOGLEVEL=DEBUG

# Set maximum parallel jobs
export OMP_NUM_THREADS=8
```

### Preferences (Future)

Currently, preferences are set via UI. Persistent settings are stored in:

```
~/.config/auto-tessell/preferences.json
```

(Not yet implemented in v0.3.1, coming in v0.4)

## Workflow Examples

### Example 1: Quick Mesh Generation (Draft)

1. Launch: `python3 desktop/qt_main.py`
2. Drag STL file onto drop zone
3. Select Quality: **Draft**
4. Click **파이프라인 실행**
5. Wait ~5 seconds
6. Click **결과 폴더 열기**

### Example 2: Fine Quality with Custom Parameters

1. Launch: `python3 desktop/qt_main.py`
2. Click "입력 파일 선택" → choose STEP file
3. Click "출력 폴더 선택" → choose output folder
4. Quality: **Fine**
5. Tier: **snappy** (for Hex-dominant)
6. Set parameters:
   - Element Size: `0.005`
   - Snappy Level: `1,2`
   - Max Cells: `5000000`
7. Click **파이프라인 실행**
8. Monitor progress bar
9. Results appear in log when done

### Example 3: Batch Testing (Dry-Run)

1. Setup same as Example 2
2. Check **Dry-run** checkbox
3. Click **파이프라인 실행**
4. Pipeline runs validation without actual mesh generation
5. Review parameters and errors in log
6. Uncheck and re-run for actual generation

## Troubleshooting

### "파이프라인 실행" Button Stays Disabled

**Cause**: Input file or output directory not set

**Fix**: Use file dialogs to select both paths, or drag STL file

### Progress Hangs at 50%

**Cause**: Long mesh generation for complex shapes

**Fix**: Wait longer (can be 30+ minutes for Fine quality)

### "FAIL" Status with Cryptic Error

**Cause**: Usually shape too complex or timeout

**Fix**:
1. Try Draft quality first
2. Enable `surface_remesh` for problematic meshes
3. Increase `max_iterations` to 5-10
4. Set `--element_size` to larger value

### GUI Doesn't Launch

**Cause**: PySide6 not installed or display server issue (WSL)

**Fix**:
```bash
# Install PySide6
pip install PySide6

# For WSL, use X11 forwarding
export DISPLAY=:0
python3 desktop/qt_main.py
```

## Performance Notes

### Typical Execution Times (Draft Quality)

| Mesh Size | Execution Time | Notes |
|-----------|----------------|-------|
| Small (<1k faces) | 3-5s | Instant |
| Medium (1k-100k) | 5-30s | Depends on complexity |
| Large (>100k) | 30-120s | May timeout |

### Memory Usage

- **Small meshes**: ~100-200 MB
- **Medium meshes**: ~500 MB - 1 GB
- **Large meshes**: ~1-2 GB

### Optimization Tips

1. **Increase cell size** if generation times are long
2. **Use Draft quality** for testing/validation
3. **Enable dry-run** to verify settings before long runs
4. **Increase max iterations** (1→5) only if needed

## Known Limitations

### Current Version (v0.3.1)

- ⚠️ **No 3D Mesh Viewer**: Results folder opens in file explorer
- ⚠️ **No Persistent Settings**: Preferences reset on app restart
- ⚠️ **Limited CAD Support**: STEP/IGES via cadquery fallback
- ⚠️ **Windows Native**: OpenFOAM evaluation not available

### Planned for v0.4+

- ✅ 3D mesh visualization with PyVista
- ✅ Persistent settings/preferences
- ✅ Batch processing multiple files
- ✅ Advanced visualization (wireframe, cut sections)
- ✅ Real-time progress graphs
- ✅ Integration with external solvers (SimpleFoam, etc.)

## Development Notes

### Code Organization

- **main_window.py**: 804 lines
  - UI construction in `_build()`
  - File/path handling
  - Parameter management
  - Result display and error handling

- **pipeline_worker.py**: 182 lines
  - QThread-based worker
  - Signal-based progress reporting
  - Exception handling with fallback

- **qt_main.py**: 57 lines
  - Application entry point
  - QApplication setup
  - Window initialization and display

### Testing

```bash
# Unit tests for pipeline worker
python3 -m pytest tests/test_pipeline.py::test_*worker* -v

# Manual GUI test (requires display)
python3 desktop/qt_main.py

# Headless validation
python3 << 'EOF'
from desktop.qt_app.main_window import AutoTessellWindow
window = AutoTessellWindow()
window.set_input_path("tests/benchmarks/cylinder.stl")
print("✅ GUI initialized successfully")
EOF
```

### Contributing

1. Follow PEP 8 / Black formatting
2. Add type hints (`from typing import ...`)
3. Update `PARAM_HELP` dict for new parameters
4. Test with `pytest tests/`
5. Document new features in this README

## License

Same as AutoTessell (LGPL-2.1+, see root LICENSE)

## Support

For issues, feature requests, or contributions:

1. Check known issues above
2. Enable debug logging: `export LOGLEVEL=DEBUG`
3. Collect logs from bottom panel
4. Report issue with OS, Python version, and logs

---

**Status**: ✅ Production Ready (MVP v0.3.1)  
**Last Updated**: 2026-04-11  
**Maintainer**: Claude Code (Haiku 4.5)
