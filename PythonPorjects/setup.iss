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
Source: "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\dist\STE_Toolkit\*"; \
    DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"
Name: "{userdesktop}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a &desktop icon"; Flags: unchecked
Name: firewall;    Description: "Allow STE Toolkit through Windows Firewall"; Flags: unchecked
Name: vc_redist;   Description: "Install Visual C++ Redistributable"; Flags: unchecked

[Run]
// Launch main app
Filename: "{app}\STE_Toolkit.exe"; Description: "Launch STE Mission Planning Toolkit now"; Flags: nowait postinstall skipifsilent

// Firewall exception (only if user checked “Allow STE Toolkit through Windows Firewall”)
Filename: "netsh"; \
  Parameters: "advfirewall firewall add rule name=""STE Toolkit"" dir=in action=allow program=""{app}\STE_Toolkit.exe"" enable=yes"; \
  Flags: runhidden; Tasks: firewall

// VC++ Redistributable installer (only if user checked “Install Visual C++ Redistributable”)
// Make sure you bundle VC_redist.x64.exe under a “redist” folder in your Source.
Filename: "{app}\redist\VC_redist.x64.exe"; \
  Parameters: "/quiet /norestart"; \
  Flags: runhidden waituntilterminated; Tasks: vc_redist
