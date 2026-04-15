; ============================================================================
; AutoTessell Windows Installer
; NSIS Modern UI 2 기반 클릭 인스톨러
; 빌드: makensis installer/autotessell.nsi
; ============================================================================

Unicode True

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

; ── 기본 설정 ────────────────────────────────────────────────────────────────
!ifndef VERSION
  !define VERSION "0.3.4"
!endif
!ifndef SRCROOT
  !define SRCROOT ".."
!endif
!ifndef OUTDIR
  !define OUTDIR "dist"
!endif

Name "AutoTessell ${VERSION}"
OutFile "${OUTDIR}\AutoTessell-${VERSION}-Setup.exe"
InstallDir "$LOCALAPPDATA\AutoTessell"
InstallDirRegKey HKCU "Software\AutoTessell" "InstallDir"
RequestExecutionLevel user        ; 관리자 권한 불필요
SetCompressor /SOLID lzma         ; 높은 압축률
BrandingText "AutoTessell ${VERSION}"
ShowInstDetails show

; ── Modern UI 설정 ────────────────────────────────────────────────────────────
!define MUI_ABORTWARNING
!define MUI_ABORTWARNING_TEXT "설치를 중단하시겠습니까?"
!define MUI_WELCOMEPAGE_TITLE "AutoTessell ${VERSION} 설치 마법사"
!define MUI_WELCOMEPAGE_TEXT "CAD/메쉬 파일을 OpenFOAM polyMesh로 자동 변환하는 AutoTessell을 설치합니다.$\r$\n$\r$\n포함 내용:$\r$\n  • Python 3.12 + 전체 메쉬 라이브러리$\r$\n  • WildMesh, TetWild, Netgen, GMSH 등 14개 메쉬 엔진$\r$\n  • Qt GUI (드래그앤드롭, 실시간 3D 뷰어)$\r$\n  • mmg3d, HOHQMesh, JIGSAW 도구$\r$\n$\r$\n인터넷 연결이 필요합니다 (약 3-5 GB 다운로드)."
!define MUI_FINISHPAGE_RUN "$INSTDIR\AutoTessell.bat"
!define MUI_FINISHPAGE_RUN_TEXT "AutoTessell 지금 실행"
!define MUI_FINISHPAGE_SHOWREADME ""
!define MUI_FINISHPAGE_TEXT "AutoTessell이 성공적으로 설치되었습니다.$\r$\n$\r$\n바탕화면의 AutoTessell 아이콘을 클릭하거나$\r$\n시작 메뉴 → AutoTessell로 실행하세요."

; ── 설치 페이지 ───────────────────────────────────────────────────────────────
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${SRCROOT}\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; ── 제거 페이지 ───────────────────────────────────────────────────────────────
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

; ── 언어 ──────────────────────────────────────────────────────────────────────
!insertmacro MUI_LANGUAGE "Korean"
!insertmacro MUI_LANGUAGE "English"

; ── 유틸리티 매크로 ───────────────────────────────────────────────────────────
; curl.exe (Windows 10 내장) 로 파일 다운로드 — 따옴표 이스케이핑 문제 없음
!macro DownloadFile URL DEST LABEL
    DetailPrint "${LABEL} 다운로드 중..."
    nsExec::ExecToLog '"$SYSDIR\curl.exe" -L --retry 3 --retry-delay 5 --ssl-no-revoke --progress-bar -o "${DEST}" "${URL}"'
    Pop $0
    ${If} $0 != "0"
        DetailPrint "${LABEL} 다운로드 실패 (ExitCode=$0)"
    ${Else}
        DetailPrint "${LABEL} 다운로드 완료"
    ${EndIf}
!macroend

; ZIP에서 특정 파일 추출 — 임시 PS1 파일 방식 (따옴표 이스케이핑 없음)
!macro ExtractFromZip ZIP MEMBER DEST LABEL
    DetailPrint "${LABEL} 압축 해제 중..."
    FileOpen $R9 "$TEMP\at_unzip.ps1" w
    FileWrite $R9 "Add-Type -AssemblyName System.IO.Compression.FileSystem$\n"
    FileWrite $R9 "$$z=[System.IO.Compression.ZipFile]::OpenRead('${ZIP}')$\n"
    FileWrite $R9 "$$e=$$z.Entries|Where-Object{$$_.FullName -like '*${MEMBER}'}|Select-Object -First 1$\n"
    FileWrite $R9 "if($$e){$$s=$$e.Open();$$f=[System.IO.File]::Create('${DEST}');$$s.CopyTo($$f);$$f.Close();$$s.Close()}$\n"
    FileWrite $R9 "$$z.Dispose()$\n"
    FileClose $R9
    nsExec::ExecToLog 'powershell.exe -NonInteractive -ExecutionPolicy Bypass -File "$TEMP\at_unzip.ps1"'
    Pop $0
    Delete "$TEMP\at_unzip.ps1"
!macroend

; ============================================================================
; 메인 설치 섹션
; ============================================================================
Section "AutoTessell" SecMain
    SectionIn RO  ; 필수 섹션 (체크 해제 불가)
    SetOutPath "$INSTDIR"

    ; ── Step 1: AutoTessell 소스 파일 추출 ──────────────────────────────────
    DetailPrint "AutoTessell 파일 복사 중..."
    SetOutPath "$INSTDIR\src"
    File /r "${SRCROOT}\installer\staging\src\*"

    SetOutPath "$INSTDIR"
    File "${SRCROOT}\installer\environment.yml"

    ; ── Step 2: Miniconda3 다운로드 및 설치 ─────────────────────────────────
    DetailPrint ""
    DetailPrint "=== Python 환경 설치 ==="

    ${If} ${FileExists} "$INSTDIR\conda\Scripts\conda.exe"
        DetailPrint "Miniconda 이미 설치됨 - 건너뜀"
    ${Else}
        !insertmacro DownloadFile \
            "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe" \
            "$TEMP\Miniconda3-installer.exe" \
            "Miniconda3 (Python 3.12)"

        ${If} ${FileExists} "$TEMP\Miniconda3-installer.exe"
            DetailPrint "Miniconda3 설치 중 (잠시 기다려 주세요)..."
            ExecWait '"$TEMP\Miniconda3-installer.exe" /S /D=$INSTDIR\conda' $0
            Delete "$TEMP\Miniconda3-installer.exe"
            ${If} $0 != "0"
                MessageBox MB_ICONSTOP "Miniconda3 설치 실패.$\nExitCode: $0"
                Abort
            ${EndIf}
            DetailPrint "Miniconda3 설치 완료"
        ${Else}
            MessageBox MB_ICONSTOP "Miniconda3 다운로드 실패.$\n인터넷 연결을 확인하세요."
            Abort
        ${EndIf}
    ${EndIf}

    ; ── Step 3: conda 환경 생성 (Python + pip만) ────────────────────────────
    DetailPrint ""
    DetailPrint "=== Python 3.12 환경 초기화 ==="

    ${If} ${FileExists} "$INSTDIR\conda\envs\autotessell\python.exe"
        DetailPrint "autotessell 환경 이미 존재 - 건너뜀"
    ${Else}
        DetailPrint "Python 3.12 환경 생성 중..."
        nsExec::ExecToLog '"$INSTDIR\conda\Scripts\conda.exe" create -n autotessell python=3.12 pip -c conda-forge --yes --quiet'
        Pop $0
        ${If} $0 != "0"
            MessageBox MB_ICONSTOP "Python 환경 생성 실패 (ExitCode: $0).$\n$\n인터넷 연결을 확인하고 다시 시도해 주세요."
            Abort
        ${EndIf}
        DetailPrint "Python 3.12 환경 생성 완료"
    ${EndIf}

    ; ── Step 4: pip 패키지 설치 (분할 설치 — 실패해도 계속) ─────────────────
    DetailPrint ""
    DetailPrint "=== 메쉬 라이브러리 설치 (pip) ==="

    ; 4-A: 핵심 GUI / 시각화
    DetailPrint "GUI 라이브러리 설치 중 (PySide6, PyVista)..."
    nsExec::ExecToLog '"$INSTDIR\conda\envs\autotessell\python.exe" -m pip install --no-warn-script-location --quiet PySide6 pyvista pyvistaqt vtk'
    Pop $0
    ${If} $0 != "0"
        DetailPrint "경고: GUI 라이브러리 일부 실패 (계속 진행)"
    ${Else}
        DetailPrint "GUI 라이브러리 설치 완료"
    ${EndIf}

    ; 4-B: 핵심 메쉬 처리
    DetailPrint "핵심 메쉬 라이브러리 설치 중 (trimesh, meshio, numpy, scipy)..."
    nsExec::ExecToLog '"$INSTDIR\conda\envs\autotessell\python.exe" -m pip install --no-warn-script-location --quiet trimesh meshio numpy scipy shapely rtree pymeshfix gmsh'
    Pop $0
    ${If} $0 != "0"
        DetailPrint "경고: 핵심 메쉬 라이브러리 일부 실패 (계속 진행)"
    ${Else}
        DetailPrint "핵심 메쉬 라이브러리 설치 완료"
    ${EndIf}

    ; 4-C: CLI / 유틸리티
    DetailPrint "CLI 유틸리티 설치 중..."
    nsExec::ExecToLog '"$INSTDIR\conda\envs\autotessell\python.exe" -m pip install --no-warn-script-location --quiet click rich pydantic structlog xxhash'
    Pop $0
    ${If} $0 != "0"
        DetailPrint "경고: CLI 유틸리티 일부 실패 (계속 진행)"
    ${Else}
        DetailPrint "CLI 유틸리티 설치 완료"
    ${EndIf}

    ; 4-D: 볼륨 메쉬 엔진
    DetailPrint "메쉬 엔진 설치 중 (TetWild, WildMesh, Netgen 등)..."
    nsExec::ExecToLog '"$INSTDIR\conda\envs\autotessell\python.exe" -m pip install --no-warn-script-location --quiet pytetwild wildmeshing netgen-mesher pyacvd pymeshlab'
    Pop $0
    ${If} $0 != "0"
        DetailPrint "경고: 일부 메쉬 엔진 설치 실패 (계속 진행)"
    ${Else}
        DetailPrint "볼륨 메쉬 엔진 설치 완료"
    ${EndIf}

    ; 4-E: 추가 도구
    DetailPrint "추가 도구 설치 중 (JIGSAW, Voronoi, CAD 등)..."
    nsExec::ExecToLog '"$INSTDIR\conda\envs\autotessell\python.exe" -m pip install --no-warn-script-location --quiet jigsawpy pyvoro-mm cadquery laspy fast-simplification classy-blocks'
    Pop $0
    ${If} $0 != "0"
        DetailPrint "경고: 추가 도구 일부 설치 실패 (계속 진행)"
    ${Else}
        DetailPrint "추가 도구 설치 완료"
    ${EndIf}

    ; ── Step 5: AutoTessell 소스 설치 ───────────────────────────────────────
    DetailPrint ""
    DetailPrint "=== AutoTessell 코어 설치 ==="
    ExecWait '"$INSTDIR\conda\envs\autotessell\python.exe" -m pip install \
        -e "$INSTDIR\src" --no-warn-script-location --quiet' $0
    ${If} $0 != "0"
        MessageBox MB_ICONSTOP "AutoTessell 설치 실패 (ExitCode: $0)."
        Abort
    ${EndIf}
    DetailPrint "AutoTessell 코어 설치 완료"

    ; ── Step 6: 외부 바이너리 다운로드 ──────────────────────────────────────
    DetailPrint ""
    DetailPrint "=== 외부 메쉬 도구 다운로드 ==="
    CreateDirectory "$INSTDIR\bin"

    ; mmg3d.exe
    ${If} ${FileExists} "$INSTDIR\bin\mmg3d.exe"
        DetailPrint "mmg3d.exe: 이미 존재"
    ${Else}
        !insertmacro DownloadFile \
            "https://github.com/MmgTools/mmg/releases/download/v5.7.3/mmg_windows_release.zip" \
            "$TEMP\mmg_windows.zip" "mmg3d.exe"
        ${If} ${FileExists} "$TEMP\mmg_windows.zip"
            !insertmacro ExtractFromZip "$TEMP\mmg_windows.zip" "mmg3d_O3.exe" "$INSTDIR\bin\mmg3d.exe" "mmg3d"
            Delete "$TEMP\mmg_windows.zip"
        ${EndIf}
    ${EndIf}

    ; HOHQMesh.exe
    ${If} ${FileExists} "$INSTDIR\bin\HOHQMesh.exe"
        DetailPrint "HOHQMesh.exe: 이미 존재"
    ${Else}
        !insertmacro DownloadFile \
            "https://github.com/trixi-framework/HOHQMesh/releases/download/v1.5.1/HOHQMesh-v1.5.1-Windows.zip" \
            "$TEMP\HOHQMesh_windows.zip" "HOHQMesh.exe"
        ${If} ${FileExists} "$TEMP\HOHQMesh_windows.zip"
            !insertmacro ExtractFromZip "$TEMP\HOHQMesh_windows.zip" "HOHQMesh.exe" "$INSTDIR\bin\HOHQMesh.exe" "HOHQMesh"
            Delete "$TEMP\HOHQMesh_windows.zip"
        ${EndIf}
    ${EndIf}

    ; libjigsaw.dll
    ${If} ${FileExists} "$INSTDIR\bin\libjigsaw.dll"
        DetailPrint "libjigsaw.dll: 이미 존재"
    ${Else}
        !insertmacro DownloadFile \
            "https://github.com/dengwirda/jigsaw/releases/download/v0.9.14/jigsaw-v0.9.14-Windows.zip" \
            "$TEMP\jigsaw_windows.zip" "libjigsaw.dll"
        ${If} ${FileExists} "$TEMP\jigsaw_windows.zip"
            !insertmacro ExtractFromZip "$TEMP\jigsaw_windows.zip" "libjigsaw.dll" "$INSTDIR\bin\libjigsaw.dll" "JIGSAW"
            Delete "$TEMP\jigsaw_windows.zip"
            ; jigsawpy _lib/에도 복사 — 임시 PS1 방식
            FileOpen $R9 "$TEMP\at_jigsawdll.ps1" w
            FileWrite $R9 "$$p=& '$INSTDIR\conda\envs\autotessell\python.exe' -c 'import jigsawpy,os; print(os.path.dirname(jigsawpy.__file__))'$\n"
            FileWrite $R9 "$$d=Join-Path $$p '_lib'$\n"
            FileWrite $R9 "New-Item -ItemType Directory -Path $$d -Force|Out-Null$\n"
            FileWrite $R9 "Copy-Item '$INSTDIR\bin\libjigsaw.dll' (Join-Path $$d 'libjigsaw.dll') -Force$\n"
            FileClose $R9
            nsExec::ExecToLog 'powershell.exe -NonInteractive -ExecutionPolicy Bypass -File "$TEMP\at_jigsawdll.ps1"'
            Pop $0
            Delete "$TEMP\at_jigsawdll.ps1"
        ${EndIf}
    ${EndIf}

    ; ── Step 7: 런처 생성 ────────────────────────────────────────────────────
    DetailPrint ""
    DetailPrint "=== 런처 생성 ==="
    FileOpen $9 "$INSTDIR\AutoTessell.bat" w
    FileWrite $9 "@echo off$\r$\n"
    FileWrite $9 "REM AutoTessell GUI Launcher$\r$\n"
    FileWrite $9 'cd /d "$INSTDIR\src"$\r$\n'
    FileWrite $9 '"$INSTDIR\conda\envs\autotessell\python.exe" -m desktop.qt_main %*$\r$\n'
    FileClose $9

    FileOpen $9 "$INSTDIR\autotessell-cli.bat" w
    FileWrite $9 "@echo off$\r$\n"
    FileWrite $9 "REM AutoTessell CLI$\r$\n"
    FileWrite $9 'cd /d "$INSTDIR\src"$\r$\n'
    FileWrite $9 '"$INSTDIR\conda\envs\autotessell\python.exe" -m cli.main %*$\r$\n'
    FileClose $9

    ; ── Step 8: 레지스트리 등록 ─────────────────────────────────────────────
    WriteRegStr HKCU "Software\AutoTessell" "InstallDir" "$INSTDIR"
    WriteRegStr HKCU "Software\AutoTessell" "Version" "${VERSION}"

    ; 프로그램 추가/제거 등록
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoTessell" \
        "DisplayName" "AutoTessell ${VERSION}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoTessell" \
        "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoTessell" \
        "DisplayVersion" "${VERSION}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoTessell" \
        "Publisher" "AutoTessell"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoTessell" \
        "URLInfoAbout" "https://github.com/autotessell/autotessell"
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoTessell" \
        "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoTessell" \
        "NoRepair" 1

    ; 제거 프로그램
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    DetailPrint ""
    DetailPrint "설치 완료!"
SectionEnd

; ── 바로가기 섹션 ─────────────────────────────────────────────────────────────
Section "바탕화면 바로가기" SecDesktop
    CreateShortCut "$DESKTOP\AutoTessell.lnk" \
        "$INSTDIR\AutoTessell.bat" "" \
        "$INSTDIR\AutoTessell.bat" 0 \
        SW_SHOWNORMAL "" "AutoTessell — CAD/Mesh to polyMesh"
SectionEnd

Section "시작 메뉴" SecStartMenu
    CreateDirectory "$SMPROGRAMS\AutoTessell"
    CreateShortCut "$SMPROGRAMS\AutoTessell\AutoTessell.lnk" \
        "$INSTDIR\AutoTessell.bat" "" \
        "$INSTDIR\AutoTessell.bat" 0
    CreateShortCut "$SMPROGRAMS\AutoTessell\AutoTessell CLI.lnk" \
        "$INSTDIR\autotessell-cli.bat" "" \
        "$INSTDIR\autotessell-cli.bat" 0
    CreateShortCut "$SMPROGRAMS\AutoTessell\제거.lnk" \
        "$INSTDIR\Uninstall.exe"
SectionEnd

; ── 초기화 함수 ───────────────────────────────────────────────────────────────
Function .onInit
    ; 이미 설치됐는지 확인
    ReadRegStr $0 HKCU "Software\AutoTessell" "InstallDir"
    ${If} $0 != ""
    ${AndIf} ${FileExists} "$0\conda\envs\autotessell\python.exe"
        MessageBox MB_YESNO|MB_ICONQUESTION "AutoTessell이 이미 설치되어 있습니다.$\r$\n재설치하시겠습니까?" IDYES +2
        Abort
    ${EndIf}
FunctionEnd

; ── 제거 섹션 ─────────────────────────────────────────────────────────────────
Section "Uninstall"
    ; 바탕화면/시작메뉴 바로가기 삭제
    Delete "$DESKTOP\AutoTessell.lnk"
    RMDir /r "$SMPROGRAMS\AutoTessell"

    ; conda 환경 제거
    ${If} ${FileExists} "$INSTDIR\conda\Scripts\conda.exe"
        DetailPrint "Python 환경 제거 중..."
        ExecWait '"$INSTDIR\conda\Scripts\conda.exe" env remove -n autotessell --yes'
    ${EndIf}

    ; 파일 및 디렉터리 삭제
    RMDir /r "$INSTDIR\src"
    RMDir /r "$INSTDIR\bin"
    RMDir /r "$INSTDIR\conda"
    Delete "$INSTDIR\AutoTessell.bat"
    Delete "$INSTDIR\autotessell-cli.bat"
    Delete "$INSTDIR\environment.yml"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir "$INSTDIR"

    ; 레지스트리 정리
    DeleteRegKey HKCU "Software\AutoTessell"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoTessell"

    MessageBox MB_ICONINFORMATION "AutoTessell이 제거되었습니다."
SectionEnd
