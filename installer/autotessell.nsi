; ============================================================================
; AutoTessell Windows Installer
; NSIS Modern UI 2 기반 클릭 인스톨러
; 빌드: makensis installer/autotessell.nsi
; ============================================================================

Unicode True

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "Sections.nsh"

; ── 기본 설정 ────────────────────────────────────────────────────────────────
!ifndef VERSION
  !define VERSION "0.3.5"
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
!define MUI_WELCOMEPAGE_TEXT "CAD/메쉬 파일을 OpenFOAM polyMesh로 자동 변환하는 AutoTessell을 설치합니다.$\r$\n$\r$\n포함 내용:$\r$\n  • Python 3.12 + 전체 메쉬 라이브러리$\r$\n  • WildMesh, TetWild, Netgen, GMSH 등 17개 메쉬 엔진$\r$\n  • Qt GUI (드래그앤드롭, 실시간 3D 뷰어)$\r$\n  • mmg3d, HOHQMesh, JIGSAW 도구$\r$\n$\r$\n선택 컴포넌트:$\r$\n  • OpenFOAM for Windows (snappy/cfMesh, ~2GB)$\r$\n  • 고급 Hex 메셔 (cinolib/RobustHex, GitHub Releases)$\r$\n$\r$\n인터넷 연결이 필요합니다 (기본 약 3-5 GB 다운로드)."
!define MUI_FINISHPAGE_RUN "$INSTDIR\AutoTessell.bat"
!define MUI_FINISHPAGE_RUN_TEXT "AutoTessell 지금 실행"
!define MUI_FINISHPAGE_SHOWREADME ""
!define MUI_FINISHPAGE_TEXT "AutoTessell이 성공적으로 설치되었습니다.$\r$\n$\r$\n바탕화면의 AutoTessell 아이콘을 클릭하거나$\r$\n시작 메뉴 → AutoTessell로 실행하세요."

; ── 설치 페이지 ───────────────────────────────────────────────────────────────
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${SRCROOT}\LICENSE"
!insertmacro MUI_PAGE_COMPONENTS
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

; ── 섹션 설명 (Components 페이지 툴팁) ────────────────────────────────────────
LangString DESC_SecMain      ${LANG_KOREAN} "AutoTessell 코어 + Python 3.12 + 17개 메쉬 엔진 (필수 — 체크 해제 불가)"
LangString DESC_SecMain      ${LANG_ENGLISH} "AutoTessell core + Python 3.12 + 17 mesh engines (required)"
LangString DESC_SecDesktop   ${LANG_KOREAN} "바탕화면에 AutoTessell 바로가기를 생성합니다."
LangString DESC_SecDesktop   ${LANG_ENGLISH} "Create an AutoTessell shortcut on the Desktop."
LangString DESC_SecStartMenu ${LANG_KOREAN} "시작 메뉴에 AutoTessell 항목을 추가합니다."
LangString DESC_SecStartMenu ${LANG_ENGLISH} "Add AutoTessell to the Windows Start Menu."
LangString DESC_SecOpenFOAM  ${LANG_KOREAN} "ESI OpenFOAM for Windows 설치 (snappyHexMesh / cfMesh 사용 시 필요). 약 2 GB 추가 다운로드. winget 또는 직접 다운로드 방식 지원."
LangString DESC_SecOpenFOAM  ${LANG_ENGLISH} "Install ESI OpenFOAM for Windows (required for snappyHexMesh / cfMesh tiers). ~2 GB extra download. Uses winget or direct download."
LangString DESC_SecHexBins   ${LANG_KOREAN} "cinolib Hex / RobustHex 사전 빌드 .pyd 바이너리를 GitHub Releases에서 다운로드합니다. 인터넷 연결 필요."
LangString DESC_SecHexBins   ${LANG_ENGLISH} "Download pre-built cinolib Hex / RobustHex .pyd binaries from GitHub Releases. Requires internet."

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

    ; ── Step 3: pip 패키지 설치 (Miniconda base 환경에 직접 설치) ──────────
    ;    conda create/env 없이 base Python 사용 — conda solver 실패 회피
    DetailPrint ""
    DetailPrint "=== 메쉬 라이브러리 설치 (pip, 5-15분 소요) ==="

    ; 3-A: 핵심 GUI / 시각화
    DetailPrint "[1/5] GUI 라이브러리 설치 중 (PySide6, PyVista)..."
    nsExec::ExecToLog '"$INSTDIR\conda\python.exe" -m pip install --no-warn-script-location PySide6 pyvista pyvistaqt vtk'
    Pop $0
    ${If} $0 != "0"
        DetailPrint "경고: GUI 라이브러리 일부 실패 (계속 진행)"
    ${Else}
        DetailPrint "GUI 라이브러리 설치 완료"
    ${EndIf}

    ; 3-B: 핵심 메쉬 처리
    DetailPrint "[2/5] 핵심 메쉬 라이브러리 설치 중 (trimesh, meshio, numpy, scipy)..."
    nsExec::ExecToLog '"$INSTDIR\conda\python.exe" -m pip install --no-warn-script-location trimesh meshio numpy scipy shapely rtree pymeshfix gmsh'
    Pop $0
    ${If} $0 != "0"
        DetailPrint "경고: 핵심 메쉬 라이브러리 일부 실패 (계속 진행)"
    ${Else}
        DetailPrint "핵심 메쉬 라이브러리 설치 완료"
    ${EndIf}

    ; 3-C: CLI / 유틸리티
    DetailPrint "[3/5] CLI 유틸리티 설치 중..."
    nsExec::ExecToLog '"$INSTDIR\conda\python.exe" -m pip install --no-warn-script-location click rich pydantic structlog xxhash'
    Pop $0
    ${If} $0 != "0"
        DetailPrint "경고: CLI 유틸리티 일부 실패 (계속 진행)"
    ${Else}
        DetailPrint "CLI 유틸리티 설치 완료"
    ${EndIf}

    ; 3-D: 볼륨 메쉬 엔진
    DetailPrint "[4/5] 메쉬 엔진 설치 중 (TetWild, WildMesh, Netgen 등)..."
    nsExec::ExecToLog '"$INSTDIR\conda\python.exe" -m pip install --no-warn-script-location pytetwild wildmeshing netgen-mesher pyacvd pymeshlab'
    Pop $0
    ${If} $0 != "0"
        DetailPrint "경고: 일부 메쉬 엔진 설치 실패 (계속 진행)"
    ${Else}
        DetailPrint "볼륨 메쉬 엔진 설치 완료"
    ${EndIf}

    ; 3-E: 추가 도구
    DetailPrint "[5/5] 추가 도구 설치 중 (JIGSAW, Voronoi, CAD 등)..."
    nsExec::ExecToLog '"$INSTDIR\conda\python.exe" -m pip install --no-warn-script-location jigsawpy pyvoro-mm cadquery laspy fast-simplification classy-blocks'
    Pop $0
    ${If} $0 != "0"
        DetailPrint "경고: 추가 도구 일부 설치 실패 (계속 진행)"
    ${Else}
        DetailPrint "추가 도구 설치 완료"
    ${EndIf}

    ; ── Step 4: AutoTessell 소스 설치 ───────────────────────────────────────
    DetailPrint ""
    DetailPrint "=== AutoTessell 코어 설치 ==="
    nsExec::ExecToLog '"$INSTDIR\conda\python.exe" -m pip install -e "$INSTDIR\src" --no-warn-script-location'
    Pop $0
    ${If} $0 != "0"
        DetailPrint "경고: AutoTessell 코어 설치 실패 (계속 진행)"
    ${Else}
        DetailPrint "AutoTessell 코어 설치 완료"
    ${EndIf}

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
            FileWrite $R9 "$$p=& '$INSTDIR\conda\python.exe' -c 'import jigsawpy,os; print(os.path.dirname(jigsawpy.__file__))'$\n"
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
    FileWrite $9 '"$INSTDIR\conda\python.exe" -m desktop.qt_main %*$\r$\n'
    FileClose $9

    FileOpen $9 "$INSTDIR\autotessell-cli.bat" w
    FileWrite $9 "@echo off$\r$\n"
    FileWrite $9 "REM AutoTessell CLI$\r$\n"
    FileWrite $9 'cd /d "$INSTDIR\src"$\r$\n'
    FileWrite $9 '"$INSTDIR\conda\python.exe" -m cli.main %*$\r$\n'
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

; ── [선택] OpenFOAM for Windows ───────────────────────────────────────────────
; snappyHexMesh / cfMesh Tier 사용 시 필요. 약 2GB 추가 다운로드.
Section /o "OpenFOAM for Windows (snappy/cfMesh, ~2GB)" SecOpenFOAM
    DetailPrint ""
    DetailPrint "=== OpenFOAM for Windows 설치 ==="
    DetailPrint "참고: ESI OpenFOAM v2412 Windows 패키지 (약 2GB)"

    ; 1차 시도: winget (Windows 10/11 기본 탑재)
    nsExec::ExecToLog 'winget.exe --version'
    Pop $0
    ${If} $0 == "0"
        DetailPrint "winget으로 ESI OpenFOAM 설치 시도 중..."
        nsExec::ExecToLog 'winget.exe install --id ESI.OpenFOAM --accept-source-agreements --accept-package-agreements --silent --scope machine'
        Pop $0
        ${If} $0 == "0"
            DetailPrint "OpenFOAM 설치 완료 (winget)"
            Goto openfoam_done
        ${Else}
            DetailPrint "winget 설치 실패 (ExitCode=$0) — 직접 다운로드 시도..."
        ${EndIf}
    ${Else}
        DetailPrint "winget 미발견 — 직접 다운로드 시도..."
    ${EndIf}

    ; 2차 시도: ESI 직접 다운로드
    !insertmacro DownloadFile \
        "https://dl.openfoam.com/windows/OpenFOAM-v2412-win-x86_64.exe" \
        "$TEMP\OpenFOAM-v2412-win.exe" "OpenFOAM v2412"
    ${If} ${FileExists} "$TEMP\OpenFOAM-v2412-win.exe"
        DetailPrint "OpenFOAM 인스톨러 실행 중 (사용자 승인 필요)..."
        ExecWait '"$TEMP\OpenFOAM-v2412-win.exe" /S' $0
        Delete "$TEMP\OpenFOAM-v2412-win.exe"
        ${If} $0 == "0"
            DetailPrint "OpenFOAM 설치 완료"
        ${Else}
            DetailPrint "OpenFOAM 설치 실패 (ExitCode=$0)"
            MessageBox MB_ICONINFORMATION \
                "OpenFOAM 자동 설치에 실패했습니다.$\r$\n$\r$\n아래 주소에서 수동으로 설치하세요:$\r$\nhttps://develop.openfoam.com/Development/openfoam/-/wikis/precompiled/windows$\r$\n$\r$\n설치 후 AutoTessell의 Fine quality 티어가 활성화됩니다." \
                MB_OK
        ${EndIf}
    ${Else}
        DetailPrint "OpenFOAM 다운로드 실패 — 수동 설치 필요"
        MessageBox MB_ICONINFORMATION \
            "OpenFOAM 다운로드에 실패했습니다.$\r$\n$\r$\n수동 설치 주소:$\r$\nhttps://develop.openfoam.com/Development/openfoam/-/wikis/precompiled/windows$\r$\n$\r$\n또는 winget을 통해:$\r$\n  winget install ESI.OpenFOAM" \
            MB_OK
    ${EndIf}

    openfoam_done:
SectionEnd

; ── [선택] 고급 Hex 메셔 바이너리 (GitHub Releases) ──────────────────────────
; cinolib_hex.pyd / robusthex.pyd 사전 빌드 바이너리.
; 빌드 워크플로: .github/workflows/build_windows_binaries.yml
!define GH_BINS_BASE "https://github.com/younglin90/AutoTessell/releases/download/windows-binaries-latest"

Section /o "고급 Hex 메셔 바이너리 (cinolib/RobustHex)" SecHexBins
    DetailPrint ""
    DetailPrint "=== 고급 Hex 메셔 바이너리 다운로드 (GitHub Releases) ==="
    CreateDirectory "$INSTDIR\bin"

    ; cinolib_hex.pyd — cinolib Hex-dominant mesher (pybind11)
    DetailPrint "[1/2] cinolib_hex.pyd 다운로드..."
    !insertmacro DownloadFile \
        "${GH_BINS_BASE}/cinolib_hex.pyd" \
        "$TEMP\cinolib_hex.pyd" "cinolib_hex.pyd"
    ${If} ${FileExists} "$TEMP\cinolib_hex.pyd"
        ; Python site-packages 경로에 복사 — PS1 방식
        FileOpen $R9 "$TEMP\at_copypyd.ps1" w
        FileWrite $R9 "$$sp=& '$INSTDIR\conda\python.exe' -c 'import sysconfig; print(sysconfig.get_path(""purelib""))'$\n"
        FileWrite $R9 "Copy-Item '$TEMP\cinolib_hex.pyd' (Join-Path $$sp 'cinolib_hex.pyd') -Force$\n"
        FileWrite $R9 "Copy-Item '$TEMP\cinolib_hex.pyd' '$INSTDIR\bin\cinolib_hex.pyd' -Force$\n"
        FileClose $R9
        nsExec::ExecToLog 'powershell.exe -NonInteractive -ExecutionPolicy Bypass -File "$TEMP\at_copypyd.ps1"'
        Pop $0
        Delete "$TEMP\at_copypyd.ps1"
        Delete "$TEMP\cinolib_hex.pyd"
        ${If} $0 == "0"
            DetailPrint "cinolib_hex.pyd 설치 완료"
        ${Else}
            DetailPrint "cinolib_hex.pyd 복사 실패 (ExitCode=$0)"
        ${EndIf}
    ${Else}
        DetailPrint "cinolib_hex.pyd 다운로드 실패 (GitHub Releases에 없거나 네트워크 오류)"
    ${EndIf}

    ; robusthex.pyd — Robust Hex-dominant mesher (pybind11)
    DetailPrint "[2/2] robusthex.pyd 다운로드..."
    !insertmacro DownloadFile \
        "${GH_BINS_BASE}/robusthex.pyd" \
        "$TEMP\robusthex.pyd" "robusthex.pyd"
    ${If} ${FileExists} "$TEMP\robusthex.pyd"
        FileOpen $R9 "$TEMP\at_copypyd2.ps1" w
        FileWrite $R9 "$$sp=& '$INSTDIR\conda\python.exe' -c 'import sysconfig; print(sysconfig.get_path(""purelib""))'$\n"
        FileWrite $R9 "Copy-Item '$TEMP\robusthex.pyd' (Join-Path $$sp 'robusthex.pyd') -Force$\n"
        FileWrite $R9 "Copy-Item '$TEMP\robusthex.pyd' '$INSTDIR\bin\robusthex.pyd' -Force$\n"
        FileClose $R9
        nsExec::ExecToLog 'powershell.exe -NonInteractive -ExecutionPolicy Bypass -File "$TEMP\at_copypyd2.ps1"'
        Pop $0
        Delete "$TEMP\at_copypyd2.ps1"
        Delete "$TEMP\robusthex.pyd"
        ${If} $0 == "0"
            DetailPrint "robusthex.pyd 설치 완료"
        ${Else}
            DetailPrint "robusthex.pyd 복사 실패 (ExitCode=$0)"
        ${EndIf}
    ${Else}
        DetailPrint "robusthex.pyd 다운로드 실패 (GitHub Releases에 없거나 네트워크 오류)"
    ${EndIf}

    DetailPrint "고급 Hex 메셔 바이너리 설치 완료"
SectionEnd

; ── 섹션 설명 함수 (Components 페이지 툴팁) ──────────────────────────────────
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecMain}      $(DESC_SecMain)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop}   $(DESC_SecDesktop)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecStartMenu} $(DESC_SecStartMenu)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecOpenFOAM}  $(DESC_SecOpenFOAM)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecHexBins}   $(DESC_SecHexBins)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ── 초기화 함수 ───────────────────────────────────────────────────────────────
Function .onInit
    ; 이미 설치됐는지 확인
    ReadRegStr $0 HKCU "Software\AutoTessell" "InstallDir"
    ${If} $0 != ""
    ${AndIf} ${FileExists} "$0\conda\python.exe"
        MessageBox MB_YESNO|MB_ICONQUESTION "AutoTessell이 이미 설치되어 있습니다.$\r$\n재설치하시겠습니까?" IDYES +2
        Abort
    ${EndIf}
FunctionEnd

; ── 제거 섹션 ─────────────────────────────────────────────────────────────────
Section "Uninstall"
    ; 바탕화면/시작메뉴 바로가기 삭제
    Delete "$DESKTOP\AutoTessell.lnk"
    RMDir /r "$SMPROGRAMS\AutoTessell"

    ; 파일 및 디렉터리 삭제
    DetailPrint "파일 제거 중..."
    RMDir /r "$INSTDIR\src"
    RMDir /r "$INSTDIR\bin"
    RMDir /r "$INSTDIR\conda"
    Delete "$INSTDIR\AutoTessell.bat"
    Delete "$INSTDIR\autotessell-cli.bat"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir "$INSTDIR"

    ; 레지스트리 정리
    DeleteRegKey HKCU "Software\AutoTessell"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoTessell"

    MessageBox MB_ICONINFORMATION "AutoTessell이 제거되었습니다."
SectionEnd
