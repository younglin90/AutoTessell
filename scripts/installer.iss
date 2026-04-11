; Auto-Tessell Installer (Inno Setup)
#define MyAppName "Auto-Tessell"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Younglin"
#define MyAppExeName "auto-tessell-gui.exe"
#define MyAppServerExe "auto-tessell-server.exe"

[Setup]
AppId={{D3F4B5E6-A7C8-4D9E-B1A2-C3D4E5F6G7H8}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=..\dist
OutputBaseFilename=Auto-Tessell-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; GUI files
Source: "..\dist\gui\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Backend files (Server)
Source: "..\dist\server\*"; DestDir: "{app}\server"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Option to launch the app after setup completes
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
