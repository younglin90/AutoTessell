@echo off
setlocal enabledelayedexpansion

echo [1/4] Installing Python dependencies...
pip install -r backend/requirements.txt
pip install pyinstaller

echo [2/4] Building Python Backend (Server)...
pyinstaller auto_tessell.spec --noconfirm

echo [3/4] Exporting Godot GUI (Windows Desktop)...
:: Godot 4.3 executable path (User might need to adjust this)
set GODOT_EXE="C:\Program Files\Godot\Godot_v4.3-stable_win64.exe"
if not exist %GODOT_EXE% (
    echo [ERROR] Godot 4.3 not found at %GODOT_EXE%
    echo Please install Godot 4.3 or update the path in this script.
    exit /b 1
)

mkdir dist\gui
%GODOT_EXE% --headless --path godot/ --export-release "Windows Desktop" ..\dist\gui\auto-tessell-gui.exe

echo [4/4] Creating Installer (Inno Setup)...
:: Inno Setup Compiler path
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    echo [ERROR] Inno Setup 6 not found. Please install it to create the setup file.
    exit /b 1
)

%ISCC% scripts/installer.iss

echo ======================================================
echo BUILD COMPLETE!
echo Setup file is located in: dist\Auto-Tessell-Setup.exe
echo ======================================================
pause
