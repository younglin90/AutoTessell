@echo off
REM Start the Auto-Tessell Web GUI on Windows.
REM The SPA (desktop\web\) is served by the FastAPI server at the root URL.
setlocal
cd /d "%~dp0"
if "%AUTOTESSELL_PORT%"=="" set AUTOTESSELL_PORT=9720

echo === Auto-Tessell Web GUI ===
echo Serving at: http://localhost:%AUTOTESSELL_PORT%/
echo Press Ctrl+C to stop.
echo.

start "" "http://localhost:%AUTOTESSELL_PORT%/"
python -m desktop.server --port %AUTOTESSELL_PORT%
