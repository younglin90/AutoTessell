@echo off
REM AutoTessell 설치 후 실행 스크립트
REM conda constructor가 설치 완료 후 자동으로 실행한다.

setlocal EnableDelayedExpansion

echo [AutoTessell] 추가 패키지 설치 중...

REM conda 환경 내 pip으로 추가 패키지 설치
"%PREFIX%\python.exe" -m pip install --no-warn-script-location ^
    pytetwild ^
    wildmeshing ^
    pyacvd ^
    pymeshlab ^
    jigsawpy ^
    pyvoro-mm ^
    cadquery ^
    laspy ^
    xxhash ^
    fast-simplification ^
    classy_blocks

if %ERRORLEVEL% NEQ 0 (
    echo [AutoTessell] 일부 패키지 설치 실패 (계속 진행)
)

REM AutoTessell 소스 설치
echo [AutoTessell] AutoTessell 코어 설치 중...
"%PREFIX%\python.exe" -m pip install --no-warn-script-location -e "%PREFIX%\AutoTessell"

REM 외부 바이너리 다운로드
echo [AutoTessell] 외부 도구 다운로드 중...
"%PREFIX%\python.exe" "%PREFIX%\AutoTessell\installer\scripts\download_binaries.py"

REM 바로가기 생성
echo [AutoTessell] 바로가기 생성 중...
"%PREFIX%\python.exe" "%PREFIX%\AutoTessell\installer\scripts\create_shortcuts.py"

REM OpenFOAM 감지 및 안내
echo [AutoTessell] OpenFOAM 감지 중...
"%PREFIX%\python.exe" "%PREFIX%\AutoTessell\installer\scripts\check_openfoam.py"

echo [AutoTessell] 설치 완료!
endlocal
