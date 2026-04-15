@echo off
REM AutoTessell GUI 런처
REM 설치 디렉터리 기준으로 conda 환경 내 python을 찾아 실행한다.

setlocal

set "INSTALL_DIR=%~dp0"
set "PYTHON=%INSTALL_DIR%conda\envs\autotessell\python.exe"

if not exist "%PYTHON%" (
    echo [오류] AutoTessell Python 환경을 찾을 수 없습니다.
    echo 경로: %PYTHON%
    echo AutoTessell을 재설치해 주세요.
    pause
    exit /b 1
)

cd /d "%INSTALL_DIR%src"
"%PYTHON%" -m desktop.qt_main

endlocal
