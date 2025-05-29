; ————————————————————————————————————————————————————————————————————
;  STE Mission Planning Toolkit Installer
; ————————————————————————————————————————————————————————————————————

[Setup]
AppName=STE Mission Planning Toolkit
AppVersion=2.0
DefaultDirName={pf}\STE Toolkit
DefaultGroupName=STE Toolkit
DisableProgramGroupPage=yes
Compression=lzma
SolidCompression=yes
OutputBaseFilename=STE_Toolkit_Setup
SetupIconFile=icon.ico

[Files]
; install every file and folder under your build dir
Source: "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\dist\STE_Toolkit\*"; \
    DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"
Name: "{userdesktop}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a &desktop icon"; Flags: unchecked

[Run]
Filename: "{app}\STE_Toolkit.exe"; Description: "Launch STE Mission Planning Toolkit now"; Flags: nowait postinstall skipifsilent
