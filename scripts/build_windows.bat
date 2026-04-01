@echo off
REM Auto-Tessell Windows Build Script
REM Requires: Python 3.12+, pip install pyinstaller
REM Output: dist/auto-tessell/auto-tessell.exe

echo === Auto-Tessell Windows Build ===

REM Install dependencies
pip install -e ".[desktop,volume,cad,netgen]"
pip install pyinstaller

REM Build
pyinstaller auto_tessell.spec --noconfirm

echo.
echo === Build Complete ===
echo Output: dist\auto-tessell\auto-tessell.exe
echo.
echo To run:
echo   dist\auto-tessell\auto-tessell.exe
echo   (starts WebSocket server on http://localhost:9720)
echo.
echo Then open Godot project: godot\project.godot
pause
