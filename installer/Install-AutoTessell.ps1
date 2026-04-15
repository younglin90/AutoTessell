<#
.SYNOPSIS
    AutoTessell Windows 자동 설치 스크립트

.DESCRIPTION
    AutoTessell과 모든 의존성을 자동으로 설치합니다.
    - Python 3.12 (Miniconda)
    - 전체 Python 패키지 (trimesh, pyvista, PySide6, netgen 등)
    - 외부 메쉬 도구 (mmg3d.exe, HOHQMesh.exe, libjigsaw.dll)
    - ESI OpenFOAM for Windows 설치 안내

.PARAMETER InstallDir
    설치 대상 디렉터리. 기본값: $env:LOCALAPPDATA\AutoTessell

.PARAMETER SkipBinaries
    외부 바이너리(mmg3d 등) 다운로드 건너뜀

.PARAMETER NoShortcut
    바탕화면/시작메뉴 바로가기 생성 건너뜀

.EXAMPLE
    # 기본 설치
    .\Install-AutoTessell.ps1

    # 사용자 지정 경로
    .\Install-AutoTessell.ps1 -InstallDir "D:\AutoTessell"

.NOTES
    Windows 10 2004 (빌드 19041) 이상 필요
    인터넷 연결 필요 (패키지 다운로드)
    관리자 권한 불필요 (사용자 디렉터리에 설치)
#>

[CmdletBinding()]
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\AutoTessell",
    [switch]$SkipBinaries,
    [switch]$NoShortcut
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest 속도 향상

# ─────────────────────────────────────────────────────────────────────────────
# 유틸리티 함수
# ─────────────────────────────────────────────────────────────────────────────

function Write-Step {
    param([string]$Msg, [string]$Color = "Cyan")
    Write-Host "`n[$([datetime]::Now.ToString('HH:mm:ss'))] $Msg" -ForegroundColor $Color
}

function Write-OK   { param([string]$Msg) Write-Host "  OK  $Msg" -ForegroundColor Green }
function Write-Warn { param([string]$Msg) Write-Host "  !!  $Msg" -ForegroundColor Yellow }
function Write-Fail { param([string]$Msg) Write-Host "  XX  $Msg" -ForegroundColor Red }

function Get-FileFromWeb {
    param([string]$Url, [string]$Dest, [string]$Label)
    Write-Host "  다운로드: $Label ..." -NoNewline
    try {
        Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing
        Write-Host " 완료" -ForegroundColor Green
    } catch {
        Write-Host " 실패" -ForegroundColor Red
        throw "다운로드 실패: $Url`n$_"
    }
}

function Extract-ZipMember {
    param([string]$ZipPath, [string]$MemberPattern, [string]$Dest)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $entry = $zip.Entries | Where-Object { $_.FullName -like "*$MemberPattern" } | Select-Object -First 1
        if ($null -eq $entry) { throw "ZIP 내 '$MemberPattern' 없음" }
        $stream = $entry.Open()
        $file = [System.IO.File]::Create($Dest)
        $stream.CopyTo($file)
        $file.Close(); $stream.Close()
    } finally {
        $zip.Dispose()
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# 1. 사전 요구사항 확인
# ─────────────────────────────────────────────────────────────────────────────

Write-Step "AutoTessell 설치 시작" "White"
Write-Host "  설치 경로: $InstallDir"

# Windows 버전 확인 (10 2004+ 필요)
$winVer = [System.Environment]::OSVersion.Version
if ($winVer.Build -lt 19041) {
    throw "Windows 10 버전 2004 (빌드 19041) 이상이 필요합니다. 현재: 빌드 $($winVer.Build)"
}
Write-OK "Windows 버전: $($winVer.Major).$($winVer.Minor) 빌드 $($winVer.Build)"

# AutoTessell 소스 위치 확인 (스크립트 위치 기준)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$SourceRoot = Split-Path -Parent $ScriptDir  # installer/ 의 상위 = 프로젝트 루트
if (-not (Test-Path "$SourceRoot\core\pipeline")) {
    throw "AutoTessell 소스를 찾을 수 없습니다.`n경로: $SourceRoot`nInstall-AutoTessell.ps1을 AutoTessell 소스의 installer\ 폴더에서 실행하세요."
}
Write-OK "소스 경로: $SourceRoot"

# 설치 디렉터리 생성
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
$BinDir = "$InstallDir\bin"
New-Item -ItemType Directory -Path $BinDir -Force | Out-Null

# ─────────────────────────────────────────────────────────────────────────────
# 2. Miniconda 설치
# ─────────────────────────────────────────────────────────────────────────────

Write-Step "Python 환경 설치 (Miniconda)"

$CondaDir = "$InstallDir\conda"
$CondaExe = "$CondaDir\Scripts\conda.exe"
$PythonExe = "$CondaDir\envs\autotessell\python.exe"

if (Test-Path $CondaExe) {
    Write-OK "Miniconda 이미 설치됨: $CondaDir"
} else {
    $MinicondaUrl = "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"
    $MinicondaInstaller = "$env:TEMP\Miniconda3-installer.exe"
    Get-FileFromWeb -Url $MinicondaUrl -Dest $MinicondaInstaller -Label "Miniconda3"

    Write-Host "  Miniconda 설치 중 (조용히)..."
    $proc = Start-Process -FilePath $MinicondaInstaller `
        -ArgumentList "/S /D=$CondaDir" `
        -Wait -PassThru -NoNewWindow
    if ($proc.ExitCode -ne 0) { throw "Miniconda 설치 실패 (ExitCode=$($proc.ExitCode))" }
    Remove-Item $MinicondaInstaller -Force
    Write-OK "Miniconda 설치 완료"
}

# ─────────────────────────────────────────────────────────────────────────────
# 3. conda 환경 생성
# ─────────────────────────────────────────────────────────────────────────────

Write-Step "AutoTessell conda 환경 생성"

if (Test-Path $PythonExe) {
    Write-OK "conda 환경 이미 존재: autotessell"
} else {
    Write-Host "  conda env create (시간이 걸립니다 — 수 분 소요)..."
    $envYml = "$ScriptDir\..\installer\environment.yml"
    if (-not (Test-Path $envYml)) { $envYml = "$SourceRoot\installer\environment.yml" }

    $proc = Start-Process -FilePath $CondaExe `
        -ArgumentList "env create -f `"$envYml`" -n autotessell --yes" `
        -Wait -PassThru -NoNewWindow
    if ($proc.ExitCode -ne 0) { throw "conda 환경 생성 실패" }
    Write-OK "conda 환경 생성 완료"
}

# ─────────────────────────────────────────────────────────────────────────────
# 4. pip 패키지 추가 설치
# ─────────────────────────────────────────────────────────────────────────────

Write-Step "추가 Python 패키지 설치 (pip)"

$pipPackages = @(
    "pytetwild", "wildmeshing", "pyacvd", "pymeshlab",
    "jigsawpy", "pyvoro-mm", "cadquery", "laspy",
    "xxhash", "fast-simplification", "classy-blocks"
)
$proc = Start-Process -FilePath $PythonExe `
    -ArgumentList "-m pip install --no-warn-script-location $($pipPackages -join ' ')" `
    -Wait -PassThru -NoNewWindow
if ($proc.ExitCode -ne 0) {
    Write-Warn "일부 pip 패키지 설치 실패 (계속 진행)"
} else {
    Write-OK "pip 패키지 설치 완료"
}

# ─────────────────────────────────────────────────────────────────────────────
# 5. AutoTessell 소스 설치
# ─────────────────────────────────────────────────────────────────────────────

Write-Step "AutoTessell 코어 설치"

$proc = Start-Process -FilePath $PythonExe `
    -ArgumentList "-m pip install -e `"$SourceRoot`" --no-warn-script-location" `
    -Wait -PassThru -NoNewWindow
if ($proc.ExitCode -ne 0) { throw "AutoTessell 설치 실패" }
Write-OK "AutoTessell 설치 완료"

# ─────────────────────────────────────────────────────────────────────────────
# 6. 외부 바이너리 다운로드 (mmg3d, HOHQMesh, libjigsaw)
# ─────────────────────────────────────────────────────────────────────────────

if (-not $SkipBinaries) {
    Write-Step "외부 메쉬 도구 다운로드"

    # mmg3d.exe
    $mmgTarget = "$BinDir\mmg3d.exe"
    if (-not (Test-Path $mmgTarget)) {
        try {
            $mmgZip = "$env:TEMP\mmg_windows.zip"
            Get-FileFromWeb `
                -Url "https://github.com/MmgTools/mmg/releases/download/v5.7.3/mmg_windows_release.zip" `
                -Dest $mmgZip -Label "mmg3d.exe"
            Extract-ZipMember -ZipPath $mmgZip -MemberPattern "mmg3d_O3.exe" -Dest $mmgTarget
            Remove-Item $mmgZip -Force
            Write-OK "mmg3d.exe 설치 완료"
        } catch {
            Write-Warn "mmg3d.exe 다운로드 실패: $_"
        }
    } else { Write-OK "mmg3d.exe 이미 존재" }

    # HOHQMesh.exe
    $hohqTarget = "$BinDir\HOHQMesh.exe"
    if (-not (Test-Path $hohqTarget)) {
        try {
            $hohqZip = "$env:TEMP\HOHQMesh_windows.zip"
            Get-FileFromWeb `
                -Url "https://github.com/trixi-framework/HOHQMesh/releases/download/v1.5.1/HOHQMesh-v1.5.1-Windows.zip" `
                -Dest $hohqZip -Label "HOHQMesh.exe"
            Extract-ZipMember -ZipPath $hohqZip -MemberPattern "HOHQMesh.exe" -Dest $hohqTarget
            Remove-Item $hohqZip -Force
            Write-OK "HOHQMesh.exe 설치 완료"
        } catch {
            Write-Warn "HOHQMesh.exe 다운로드 실패: $_"
        }
    } else { Write-OK "HOHQMesh.exe 이미 존재" }

    # libjigsaw.dll → jigsawpy _lib/
    try {
        $jigsawPkg = & $PythonExe -c "import jigsawpy; print(jigsawpy.__file__)" 2>$null
        if ($jigsawPkg) {
            $libDir = Join-Path (Split-Path $jigsawPkg) "_lib"
            New-Item -ItemType Directory -Path $libDir -Force | Out-Null
            $dllTarget = "$libDir\libjigsaw.dll"
            if (-not (Test-Path $dllTarget)) {
                $jigsawZip = "$env:TEMP\jigsaw_windows.zip"
                Get-FileFromWeb `
                    -Url "https://github.com/dengwirda/jigsaw/releases/download/v0.9.14/jigsaw-v0.9.14-Windows.zip" `
                    -Dest $jigsawZip -Label "libjigsaw.dll"
                Extract-ZipMember -ZipPath $jigsawZip -MemberPattern "libjigsaw.dll" -Dest $dllTarget
                Copy-Item $dllTarget "$BinDir\libjigsaw.dll" -Force
                Remove-Item $jigsawZip -Force
                Write-OK "libjigsaw.dll 설치 완료"
            } else { Write-OK "libjigsaw.dll 이미 존재" }
        }
    } catch {
        Write-Warn "libjigsaw.dll 설치 실패: $_"
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# 7. 런처 생성
# ─────────────────────────────────────────────────────────────────────────────

Write-Step "런처 생성"

$launcherBat = "$InstallDir\AutoTessell.bat"
@"
@echo off
REM AutoTessell GUI 런처
cd /d "$SourceRoot"
"$PythonExe" -m desktop.qt_main %*
"@ | Set-Content -Path $launcherBat -Encoding UTF8
Write-OK "런처: $launcherBat"

# CLI 런처
$cliBat = "$InstallDir\autotessell-cli.bat"
@"
@echo off
REM AutoTessell CLI
cd /d "$SourceRoot"
"$PythonExe" -m cli.main %*
"@ | Set-Content -Path $cliBat -Encoding UTF8
Write-OK "CLI 런처: $cliBat"

# ─────────────────────────────────────────────────────────────────────────────
# 8. 바탕화면 / 시작 메뉴 바로가기
# ─────────────────────────────────────────────────────────────────────────────

if (-not $NoShortcut) {
    Write-Step "바로가기 생성"

    $WshShell = New-Object -ComObject WScript.Shell

    # 바탕화면
    $desktopLnk = "$env:USERPROFILE\Desktop\AutoTessell.lnk"
    $lnk = $WshShell.CreateShortcut($desktopLnk)
    $lnk.TargetPath = $launcherBat
    $lnk.WorkingDirectory = $SourceRoot
    $lnk.Description = "AutoTessell — CAD/Mesh to OpenFOAM polyMesh"
    $lnk.Save()
    Write-OK "바탕화면 바로가기: $desktopLnk"

    # 시작 메뉴
    $startMenuDir = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\AutoTessell"
    New-Item -ItemType Directory -Path $startMenuDir -Force | Out-Null
    $startLnk = "$startMenuDir\AutoTessell.lnk"
    $lnk2 = $WshShell.CreateShortcut($startLnk)
    $lnk2.TargetPath = $launcherBat
    $lnk2.WorkingDirectory = $SourceRoot
    $lnk2.Description = "AutoTessell GUI"
    $lnk2.Save()
    Write-OK "시작 메뉴: $startLnk"
}

# ─────────────────────────────────────────────────────────────────────────────
# 9. OpenFOAM 감지 및 안내
# ─────────────────────────────────────────────────────────────────────────────

Write-Step "OpenFOAM 감지"

$esiPaths = @(
    "$env:PROGRAMFILES\OpenFOAM",
    "C:\OpenFOAM"
)
$esiFound = $false
foreach ($base in $esiPaths) {
    if (Test-Path $base) {
        Get-ChildItem $base -Directory | Sort-Object Name -Descending | ForEach-Object {
            $bashrc = Join-Path $_.FullName "etc\bashrc"
            $bash   = Join-Path $_.FullName "msys64\usr\bin\bash.exe"
            if ((Test-Path $bashrc) -and (Test-Path $bash)) {
                Write-OK "ESI OpenFOAM 발견: $($_.FullName)"
                Write-OK "snappyHexMesh / cfMesh Tier 사용 가능"
                $esiFound = $true
            }
        }
    }
}

if (-not $esiFound) {
    Write-Warn "OpenFOAM 미설치 — snappy/cfmesh Tier 비활성"
    Write-Host @"

  ┌──────────────────────────────────────────────────────────────────┐
  │  snappyHexMesh / cfMesh를 사용하려면 OpenFOAM이 필요합니다.      │
  │                                                                  │
  │  ESI OpenFOAM for Windows (권장):                                │
  │    https://openfoam.com/download/windows                        │
  │                                                                  │
  │  OpenFOAM 없이도 14개 이상의 메쉬 엔진을 바로 사용할 수 있습니다. │
  └──────────────────────────────────────────────────────────────────┘
"@
}

# ─────────────────────────────────────────────────────────────────────────────
# 10. 설치 완료
# ─────────────────────────────────────────────────────────────────────────────

Write-Step "설치 완료!" "Green"
Write-Host @"

  AutoTessell이 설치되었습니다.

  GUI 실행 방법:
    바탕화면의 'AutoTessell' 아이콘 더블클릭
    또는: $launcherBat

  CLI 실행 방법:
    $cliBat run input.stl -o ./case --quality draft

  설치 경로: $InstallDir
  소스 경로: $SourceRoot
  Python:    $PythonExe

"@ -ForegroundColor Green

# GUI 바로 실행 여부 묻기
$launch = Read-Host "지금 AutoTessell GUI를 실행할까요? (y/N)"
if ($launch -match "^[Yy]") {
    Start-Process -FilePath $launcherBat -NoNewWindow
}
