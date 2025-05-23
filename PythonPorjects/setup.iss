; ————————————————————————————————————————————————————————————————————
;  STE Mission Planning Toolkit Installer
; ————————————————————————————————————————————————————————————————————

[Setup]
AppName=STE Mission Planning Toolkit
AppVersion=1.0
DefaultDirName={pf}\STE Toolkit
DefaultGroupName=STE Toolkit
DisableProgramGroupPage=yes
Compression=lzma
SolidCompression=yes
OutputBaseFilename=STE_Toolkit_Setup

[Files]
; install every file and folder under your build dir
Source: "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\dist\custom_launcher\*"; \
    DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\STE Mission Planning Toolkit"; Filename: "{app}\custom_launcher.exe"
Name: "{userdesktop}\STE Mission Planning Toolkit"; Filename: "{app}\custom_launcher.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a &desktop icon"; Flags: unchecked

[Run]
Filename: "{app}\custom_launcher.exe"; Description: "Launch STE Mission Planning Toolkit now"; Flags: nowait postinstall skipifsilent
