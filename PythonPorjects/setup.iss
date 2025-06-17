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
PrivilegesRequired=admin

[Files]
Source: "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\dist\STE_Toolkit\*"; \
    DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"
Name: "{userdesktop}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a &desktop icon"; Flags: unchecked
Name: firewall;    Description: "Allow STE Toolkit through Windows Firewall"; Flags: unchecked

[Run]
Filename: "{app}\STE_Toolkit.exe"; Description: "Launch STE Mission Planning Toolkit now"; \
  Flags: nowait postinstall skipifsilent
Filename: "netsh"; \
  Parameters: "advfirewall firewall add rule name=""STE Toolkit"" dir=in action=allow program=""{app}\STE_Toolkit.exe"" enable=yes"; \
  Flags: runhidden; Tasks: firewall

; ─── HERE’S THE NEW BIT ─────────────────────────────────────────────────────
[Registry]
Root: HKLM; \
  Subkey: "SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"; \
  ValueType: string; \
  ValueName: "{app}\STE_Toolkit.exe"; \
  ValueData: "~ RUNASADMIN"; \
  Flags: uninsdeletekeyifempty uninsdeletevalue
