; Indic TTS Studio installer. Build with:  ISCC.exe installer\installer.iss
; Per-user install (no admin). Models are already compressed, so we use disk spanning:
; output is Setup.exe + Setup-1.bin, Setup-2.bin ... which must stay in the same folder.

#define AppName "Indic TTS Studio"
#define AppVersion "1.0.0"

[Setup]
AppId={{B6F3C1A2-5D7E-4A91-9C3B-7E1F0A2D4C58}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Indic TTS Studio
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=IndicTTSStudio-Setup
Compression=lzma2/fast
SolidCompression=no
DiskSpanning=yes
DiskSliceSize=2000000000
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
WizardStyle=modern
UninstallDisplayName={#AppName}

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "offline"; Description: "Start in &offline mode (blocks all network access to model hubs)"; GroupDescription: "Options:"; Flags: unchecked

[Files]
Source: "stage\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "main.py"; WorkingDir: "{app}\app"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "main.py"; WorkingDir: "{app}\app"; Tasks: desktopicon
Name: "{group}\{#AppName} (with console, for troubleshooting)"; Filename: "{app}\run.bat"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "main.py"; WorkingDir: "{app}\app"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('offline') then
    SaveStringToFile(ExpandConstant('{app}\app\models\.offline'), '', False);
end;

[UninstallDelete]
Type: filesandordirs; Name: "{app}\app\__pycache__"
Type: filesandordirs; Name: "{app}\python\Lib\site-packages\__pycache__"
