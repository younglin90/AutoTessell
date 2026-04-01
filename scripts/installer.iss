; Auto-Tessell Windows Installer (Inno Setup)
; Prerequisites: PyInstaller build + Godot export completed
;
; Build steps:
;   1. pyinstaller auto_tessell.spec
;   2. Godot export → dist/godot/AutoTessell.exe
;   3. iscc scripts/installer.iss

[Setup]
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
SetupIconFile=godot\assets\icon.ico
UninstallDisplayIcon={app}\AutoTessell.exe
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Files]
; Python backend (PyInstaller output)
Source: "dist\auto-tessell\*"; DestDir: "{app}\backend"; Flags: ignoreversion recursesubdirs

; Godot GUI (exported .exe + .pck)
Source: "dist\godot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

; Benchmark files
Source: "tests\benchmarks\sphere.stl"; DestDir: "{app}\samples"
Source: "tests\benchmarks\box.step"; DestDir: "{app}\samples"

[Icons]
Name: "{group}\Auto-Tessell"; Filename: "{app}\AutoTessell.exe"
Name: "{group}\Uninstall Auto-Tessell"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Auto-Tessell"; Filename: "{app}\AutoTessell.exe"

[Run]
; Start backend server automatically after install
Filename: "{app}\backend\auto-tessell.exe"; Description: "Start Auto-Tessell backend"; Flags: postinstall nowait skipifsilent shellexec

[UninstallRun]
; Stop backend server on uninstall
Filename: "taskkill"; Parameters: "/IM auto-tessell.exe /F"; Flags: runhidden

[Code]
// Auto-start backend with Godot GUI
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Backend will be started by the [Run] section
  end;
end;
