; AutoTessell Windows Inno Setup 스크립트
; 빌드: Inno Setup 6 (https://jrsoftware.org/isinfo.php)
; 명령: ISCC.exe AutoTessell_Setup.iss
;
; 전제 조건:
;   - Miniconda Windows 인스톨러 (assets/Miniconda3-latest-Windows-x86_64.exe)
;     wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe -O assets/Miniconda3-latest-Windows-x86_64.exe
;   - AutoTessell 소스 코드 (상위 디렉터리)

#define AppName "AutoTessell"
#define AppVersion "0.4.0-beta49"
#define AppPublisher "AutoTessell"
#define AppURL "https://github.com/autotessell/autotessell"
#define AppExeName "AutoTessell.bat"
#define CondaEnvName "autotessell"

[Setup]
AppId={{7F2A1C3E-4B89-4D2A-9E6F-1A3C5D7E9F2B}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=..\LICENSE
OutputDir=dist
OutputBaseFilename=AutoTessell-{#AppVersion}-Setup
SetupIconFile=assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
MinVersion=10.0.19041     ; Windows 10 2004+ (WSL2 지원)
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startmenuicon"; Description: "시작 메뉴에 추가"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; AutoTessell 소스
Source: "..\*"; DestDir: "{app}\src"; Flags: ignoreversion recursesubdirs createallsubdirs; \
  Excludes: "*.pyc,__pycache__,*.egg-info,.git,.venv,dist,build,*.stl,*.vtk,*.vtu,AlgoHex,Feature-Preserving*,HOHQMesh,VoroCrust,pdmt,voro,bin\*.so"

; Miniconda 인스톨러 (assets/ 에 미리 다운로드 필요)
Source: "assets\Miniconda3-latest-Windows-x86_64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

; conda environment.yml
Source: "environment.yml"; DestDir: "{app}"

; post_install 스크립트
Source: "scripts\*"; DestDir: "{app}\installer\scripts"; Flags: ignoreversion recursesubdirs

; 런처 배치 파일
Source: "assets\launch_gui.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\launch_gui.bat"; \
  IconFilename: "{app}\installer\assets\icon.ico"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\launch_gui.bat"; \
  Tasks: desktopicon; IconFilename: "{app}\installer\assets\icon.ico"

[Run]
; 1. Miniconda 설치 (조용히)
Filename: "{tmp}\Miniconda3-latest-Windows-x86_64.exe"; \
  Parameters: "/S /D={app}\conda"; \
  StatusMsg: "Miniconda 설치 중..."; Flags: waituntilterminated

; 2. conda 환경 생성 (environment.yml 기반)
Filename: "{app}\conda\Scripts\conda.exe"; \
  Parameters: "env create -f ""{app}\environment.yml"" -n {#CondaEnvName} --yes"; \
  StatusMsg: "Python 환경 구성 중 (시간이 걸릴 수 있습니다)..."; \
  Flags: waituntilterminated

; 3. AutoTessell 소스 설치
Filename: "{app}\conda\envs\{#CondaEnvName}\python.exe"; \
  Parameters: "-m pip install -e ""{app}\src"" --no-warn-script-location"; \
  StatusMsg: "AutoTessell 설치 중..."; Flags: waituntilterminated

; 4. 외부 바이너리 다운로드 (mmg3d.exe, HOHQMesh.exe, libjigsaw.dll)
Filename: "{app}\conda\envs\{#CondaEnvName}\python.exe"; \
  Parameters: """{app}\installer\scripts\download_binaries.py"""; \
  StatusMsg: "외부 도구 다운로드 중..."; Flags: waituntilterminated

; 5. OpenFOAM 감지 및 안내
Filename: "{app}\conda\envs\{#CondaEnvName}\python.exe"; \
  Parameters: """{app}\installer\scripts\check_openfoam.py"""; \
  StatusMsg: "OpenFOAM 확인 중..."; Flags: waituntilterminated

; 6. 설치 완료 후 GUI 실행 옵션
Filename: "{app}\launch_gui.bat"; \
  Description: "AutoTessell 실행"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\conda\envs\{#CondaEnvName}"

[Code]
// Windows 10 2004+ 버전 체크 (WSL2 지원 여부)
function InitializeSetup(): Boolean;
var
  WinVer: TWindowsVersion;
begin
  GetWindowsVersionEx(WinVer);
  Result := True;

  if (WinVer.Major < 10) or
     ((WinVer.Major = 10) and (WinVer.Build < 19041)) then
  begin
    MsgBox(
      'AutoTessell은 Windows 10 버전 2004 이상이 필요합니다.' + #13#10 +
      '현재 버전: ' + IntToStr(WinVer.Major) + '.' +
      IntToStr(WinVer.Minor) + ' (빌드 ' + IntToStr(WinVer.Build) + ')' + #13#10#13#10 +
      'Windows Update를 통해 시스템을 업데이트하세요.',
      'AutoTessell 설치',
      MB_ICONWARNING or MB_OK
    );
    Result := False;
  end;
end;

// 디스크 공간 확인 (최소 10 GB)
function NextButtonClick(CurPageID: Integer): Boolean;
var
  FreeMB: Cardinal;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    FreeMB := GetSpaceOnDisk(ExtractFileDrive(WizardForm.DirEdit.Text), True);
    if FreeMB < 10240 then  // 10 GB
    begin
      if MsgBox(
        Format(
          '선택한 드라이브의 여유 공간이 부족합니다.' + #13#10 +
          '현재 여유 공간: %d MB' + #13#10 +
          '권장 여유 공간: 10,240 MB (10 GB)' + #13#10#13#10 +
          '계속 진행하시겠습니까?',
          [FreeMB]
        ),
        '디스크 공간 경고',
        MB_ICONWARNING or MB_YESNO
      ) = IDNO then
        Result := False;
    end;
  end;
end;
