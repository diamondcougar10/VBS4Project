[Setup]
AppName=STE Mission Planning Toolkit
AppVersion=1.0
DefaultDirName={pf}\STE Toolkit
DefaultGroupName=STE Toolkit
DisableProgramGroupPage=yes
Compression=lzma
SolidCompression=yes
OutputBaseFilename=STE_Toolkit_Setup
SetupIconFile=icon.ico

; ─── Require administrator privileges ───────────────────────────────────────
PrivilegesRequired=admin

[Files]
Source: "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\dist\STE_Toolkit\*"; \
    DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"
Name: "{userdesktop}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a &desktop icon"; Flags: checked
Name: firewall;    Description: "Allow STE Toolkit through Windows Firewall"; Flags: checked


[Run]
// Launch main app (no elevation needed here; installer already ran elevated)
Filename: "{app}\STE_Toolkit.exe"; Description: "Launch STE Mission Planning Toolkit now"; Flags: nowait postinstall skipifsilent

// Firewall exception (only if user checked “Allow STE Toolkit through Windows Firewall”)
Filename: "netsh"; \
  Parameters: "advfirewall firewall add rule name=""STE Toolkit"" dir=in action=allow program=""{app}\STE_Toolkit.exe"" enable=yes"; \
  Flags: runhidden; Tasks: firewall


