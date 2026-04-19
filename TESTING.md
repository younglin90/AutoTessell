# AutoTessell Testing Notes

## Qt GUI Tests

The test suite forces `QT_QPA_PLATFORM=offscreen` in `tests/conftest.py` so Qt
widgets can be created in headless environments.

In offscreen mode, tests also force `desktop.qt_app.mesh_viewer.PYVISTAQT_AVAILABLE`
to `False`. PyVistaQt's VTK-backed `QtInteractor` can abort the Python process in
some headless environments, so GUI tests use the static viewer fallback unless a
real display is available.

## Visual Regression Tests

GUI screenshot tests live in `tests/test_gui_visual.py` and are marked
`pytest.mark.visual`.

```bash
python3 -m pytest tests/test_gui_visual.py -q
python3 -m pytest tests/test_qt_app.py tests/test_gui_visual.py -q
python3 -m pytest --skip-visual
```

Baseline images are stored in `tests/fixtures/screenshots/baselines/`.
Actual screenshots are written to `tests/fixtures/screenshots/actual/` and are
ignored by git.
