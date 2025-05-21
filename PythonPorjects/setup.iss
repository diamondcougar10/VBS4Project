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
; ─── the single EXE ────────────────────────────────────────────────────────
Source: "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\dist\custom_launcher\custom_launcher.exe"; \
    DestDir: "{app}"; Flags: ignoreversion

; ─── now your “logos” live under the “_internal” folder ───────────────────
Source: "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\dist\custom_launcher\_internal\logos\*"; \
    DestDir: "{app}\logos"; Flags: recursesubdirs createallsubdirs

; ─── Autolaunch_Batchfiles ────────────────────────────────────────────────
Source: "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\dist\custom_launcher\_internal\Autolaunch_Batchfiles\*"; \
    DestDir: "{app}\Autolaunch_Batchfiles"; Flags: recursesubdirs createallsubdirs

; ─── PDF_EN ────────────────────────────────────────────────────────────────
Source: "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\dist\custom_launcher\_internal\PDF_EN\*"; \
    DestDir: "{app}\PDF_EN"; Flags: recursesubdirs createallsubdirs

; ─── BVI_Documentation ────────────────────────────────────────────────────
Source: "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\dist\custom_launcher\_internal\BVI_Documentation\*"; \
    DestDir: "{app}\BVI_Documentation"; Flags: recursesubdirs createallsubdirs

; ─── Help_Tutorials ───────────────────────────────────────────────────────
Source: "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\dist\custom_launcher\_internal\Help_Tutorials\*"; \
    DestDir: "{app}\Help_Tutorials"; Flags: recursesubdirs createallsubdirs

; ─── loose files ──────────────────────────────────────────────────────────
Source: "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\dist\custom_launcher\_internal\config.ini"; \
    DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\dist\custom_launcher\_internal\20240206_101613_026.jpg"; \
    DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\STE Mission Planning Toolkit"; Filename: "{app}\custom_launcher.exe"
Name: "{userdesktop}\STE Mission Planning Toolkit"; Filename: "{app}\custom_launcher.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\custom_launcher.exe"; Description: "Launch STE Mission Planning Toolkit now"; Flags: nowait postinstall skipifsilent
