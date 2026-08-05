@echo off
setlocal enabledelayedexpansion

echo [1/3] Installing Python dependencies...
pip install -r products/web/api/requirements.txt
pip install pyinstaller

echo [2/3] Building Python Backend (Server)...
pyinstaller auto_tessell.spec --noconfirm

echo [3/3] Creating Installer (Inno Setup)...
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
