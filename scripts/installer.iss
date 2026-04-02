; Auto-Tessell Windows Installer (Inno Setup 6)
;
; Build: iscc scripts\installer.iss
; Output: dist\installer\AutoTessell-Setup.exe

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
; Python backend (PyInstaller output)
Source: "dist\auto-tessell\*"; DestDir: "{app}\backend"; Flags: ignoreversion recursesubdirs

; Godot project files (사용자가 Godot로 열 수 있도록)
Source: "godot\project.godot"; DestDir: "{app}\godot"
Source: "godot\scenes\*"; DestDir: "{app}\godot\scenes"; Flags: ignoreversion recursesubdirs
Source: "godot\scripts\*"; DestDir: "{app}\godot\scripts"; Flags: ignoreversion recursesubdirs
Source: "godot\assets\*"; DestDir: "{app}\godot\assets"; Flags: ignoreversion recursesubdirs

; Sample files
Source: "tests\benchmarks\sphere.stl"; DestDir: "{app}\samples"
Source: "tests\benchmarks\box.step"; DestDir: "{app}\samples"
Source: "tests\benchmarks\naca0012.stl"; DestDir: "{app}\samples"

; README
Source: "README.md"; DestDir: "{app}"; Flags: isreadme

[Icons]
Name: "{group}\Auto-Tessell Server"; Filename: "{app}\backend\auto-tessell.exe"; Comment: "Auto-Tessell 메쉬 생성 서버"
Name: "{group}\Uninstall Auto-Tessell"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Auto-Tessell"; Filename: "{app}\backend\auto-tessell.exe"; Comment: "Auto-Tessell 메쉬 생성 서버"

[Run]
Filename: "{app}\backend\auto-tessell.exe"; Description: "Auto-Tessell 서버 시작"; Flags: postinstall nowait skipifsilent shellexec

[UninstallRun]
Filename: "taskkill"; Parameters: "/IM auto-tessell.exe /F"; Flags: runhidden
