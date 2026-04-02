; Auto-Tessell Windows Installer (Inno Setup 6)
;
; Godot GUI (.exe) + Python Backend (.exe) 통합 설치
; 사용자는 AutoTessell.exe 더블클릭만 하면 됨

[Setup]
SourceDir=..
AppName=Auto-Tessell
AppVersion=0.1.0
AppPublisher=Auto-Tessell
AppPublisherURL=https://github.com/younglin90/auto-tessell
DefaultDirName={autopf}\Auto-Tessell
DefaultGroupName=Auto-Tessell
OutputDir=dist\installer
OutputBaseFilename=AutoTessell-0.1.0-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayName=Auto-Tessell
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Godot GUI (메인 실행 파일)
Source: "dist\godot\AutoTessell.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\godot\AutoTessell.pck"; DestDir: "{app}"; Flags: ignoreversion

; Python backend (Godot가 자동 실행)
Source: "dist\auto-tessell\*"; DestDir: "{app}\backend"; Flags: ignoreversion recursesubdirs

; Sample files
Source: "tests\benchmarks\sphere.stl"; DestDir: "{app}\samples"
Source: "tests\benchmarks\box.step"; DestDir: "{app}\samples"
Source: "tests\benchmarks\naca0012.stl"; DestDir: "{app}\samples"

; README
Source: "README.md"; DestDir: "{app}"; Flags: isreadme

[Icons]
Name: "{group}\Auto-Tessell"; Filename: "{app}\AutoTessell.exe"; Comment: "Auto-Tessell 메쉬 생성 도구"
Name: "{group}\Uninstall Auto-Tessell"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Auto-Tessell"; Filename: "{app}\AutoTessell.exe"; Comment: "Auto-Tessell 메쉬 생성 도구"

[Run]
Filename: "{app}\AutoTessell.exe"; Description: "Auto-Tessell 실행"; Flags: postinstall nowait skipifsilent shellexec

[UninstallRun]
Filename: "taskkill"; Parameters: "/IM AutoTessell.exe /F"; Flags: runhidden; RunOnceId: "KillGodot"
Filename: "taskkill"; Parameters: "/IM auto-tessell.exe /F"; Flags: runhidden; RunOnceId: "KillBackend"
