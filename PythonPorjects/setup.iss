; ===================== STE Mission Planning Toolkit Installer =====================
; -- Production-friendly: creates SharedMeshDrive layout and runs third-party installs
; ================================================================================
#define AppName "STE Mission Planning Toolkit"
#define AppVersion "1.0"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={pf}\STE Toolkit
DefaultGroupName=STE Toolkit
DisableProgramGroupPage=yes
Compression=lzma
SolidCompression=yes
OutputBaseFilename=STE_Toolkit_Setup
SetupIconFile=icon.ico
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

; --- Allow larger embedded payloads (optional but recommended) ---
; If you embed large installers, consider these (uncomment if needed):
; SignedUninstaller=yes
; SignedUninstallerDir={tmp}

[Files]
; 1) Your application (PyInstaller dist)
Source: "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\dist\STE_Toolkit\*"; \
    DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

; 2) Third-party installers (EMBED THEM so setup runs offline)
;    Copy your repo's folders into the project before compiling.
;    They will be extracted to {tmp} and removed after install.
; --- Photomesh installers ---
Source: "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\installs\Photomesh\*"; \
    DestDir: "{tmp}\PhotomeshInstalls"; Flags: recursesubdirs createallsubdirs; Check: ShouldRunPrereqs
; --- Reality Mesh installers ---
Source: "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\installs\RealityMesh\*"; \
    DestDir: "{tmp}\RealityMeshInstalls"; Flags: recursesubdirs createallsubdirs; Check: ShouldRunPrereqs

[Icons]
Name: "{group}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"
Name: "{userdesktop}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a &desktop icon"; Flags: unchecked
Name: firewall;    Description: "Allow STE Toolkit through Windows Firewall"; Flags: unchecked

[Run]
; Launch your toolkit when finished (optional)
Filename: "{app}\STE_Toolkit.exe"; Description: "Launch STE Mission Planning Toolkit now"; \
  Flags: nowait postinstall skipifsilent

; Open inbound firewall rule for the EXE (optional)
Filename: "netsh"; \
  Parameters: "advfirewall firewall add rule name=""STE Toolkit"" dir=in action=allow program=""{app}\STE_Toolkit.exe"" enable=yes"; \
  Flags: runhidden; Tasks: firewall

[Registry]
; Force “Run as Administrator” compatibility flag for the app EXE
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"; \
ValueType: string; ValueName: "{app}\STE_Toolkit.exe"; ValueData: "~ RUNASADMIN"; \
Flags: uninsdeletevalue uninsdeletekeyifempty

[Code]
var
  ModePage: TInputOptionWizardPage;
  SharedRootPage: TInputDirWizardPage;
  SharedRoot: string;

function FileExists2(const P: string): Boolean;
begin
  Result := (P <> '') and FileExists(P);
end;

function HasPhotoMeshWizard(): Boolean;
begin
  Result :=
    FileExists2(ExpandConstant('{pf}\Skyline\PhotoMesh\Tools\PhotomeshWizard\PhotoMeshWizard.exe')) or
    FileExists2(ExpandConstant('{pf}\Skyline\PhotoMeshWizard\PhotoMeshWizard.exe')) or
    FileExists2(ExpandConstant('{pf32}\Skyline\PhotoMesh\Tools\PhotomeshWizard\PhotoMeshWizard.exe'));
end;

function ForceLayoutUnder(Root: string): string;
var
  Base, P: string;
begin
  Base := AddBackslash(Root) + 'SharedMeshDrive';
  ForceDirectories(Base);
  P := Base + '\WorkingFuser';        ForceDirectories(P);
  P := Base + '\Projects';            ForceDirectories(P);
  P := Base + '\RealityMeshInstall';  ForceDirectories(P);
  P := Base + '\UnprocessedPhotos';   ForceDirectories(P);
  P := Base + '\RealityMeshOutput';   ForceDirectories(P);
  Result := Base;
end;

procedure EnsureSmbShare(ShareName, LocalPath: string);
var
  RC: Integer;
  Cmd, EscShare, EscPath: string;
begin
  EscShare := ShareName;
  EscPath := LocalPath;
  StringChangeEx(EscShare, '''', '''''', True);
  StringChangeEx(EscPath, '''', '''''', True);
  Cmd :=
    '-NoProfile -ExecutionPolicy Bypass -Command ' +
    '"$ErrorActionPreference=''Stop''; ' +
    'if (-not (Get-SmbShare -Name ''' + EscShare + ''' -ErrorAction SilentlyContinue)) { ' +
    '  New-SmbShare -Name ''' + EscShare + ''' -Path ''' + EscPath + ''' -FullAccess ''Everyone'' | Out-Null ' +
    '}; ' +
    'Get-NetFirewallRule -DisplayGroup ''File and Printer Sharing'' | ' +
    '  Where-Object {$_.Profile -like ''*Private*''} | Enable-NetFirewallRule | Out-Null"';

  Exec(
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    Cmd,
    '', SW_HIDE, ewWaitUntilTerminated, RC);
end;

procedure SeedConfigIni(AppDir, ShareRoot: string);
var
  Ini, Base: string;
begin
  Ini  := AppDir + '\config.ini';
  Base := ForceLayoutUnder(ShareRoot);
  EnsureSmbShare('SharedMeshDrive', Base);

  SetIniString('Offline', 'enabled', 'True', Ini);
  SetIniString('Offline', 'host_name', ExpandConstant('{computername}'), Ini);
  SetIniString('Offline', 'host_ip', '', Ini);
  SetIniString('Offline', 'share_name', 'SharedMeshDrive', Ini);
  SetIniString('Offline', 'local_data_root', Base, Ini);
  SetIniString('Offline', 'working_fuser_subdir', 'WorkingFuser', Ini);
  SetIniString('Offline', 'use_ip_unc', 'False', Ini);

  SetIniString('SharedDrive', 'preferred_mode', 'DRIVE', Ini);
  SetIniString('SharedDrive', 'drive_letter', 'D:', Ini);
  SetIniString('SharedDrive', 'auto_map_on_save', 'True', Ini);

  SetIniString('General', 'first_run_done', 'True', Ini);
  SetIniString('General', 'reality_mesh_local_root', Base + '\RealityMeshInstall', Ini);

  SetIniString('Fusers', 'desired_count', '3', Ini);
  SetIniString('Fusers', 'host_count', '1', Ini);
end;

function ShouldRunPrereqs: Boolean;
begin
  Result := Assigned(ModePage) and ModePage.Values[0] and (not HasPhotoMeshWizard());
end;

procedure RunAllInstallers(Dir: string);
var
  FindRec: TFindRec;
  FilePath, Params: string;
  RC: Integer;
begin
  if FindFirst(Dir + '\*.msi', FindRec) then
  try
    repeat
      if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) = 0 then begin
        FilePath := Dir + '\' + FindRec.Name;
        Params := '/i "' + FilePath + '" /qn /norestart ALLUSERS=1';
        Exec(ExpandConstant('{sys}\msiexec.exe'), Params, '', SW_HIDE, ewWaitUntilTerminated, RC);
      end;
    until not FindNext(FindRec);
  finally
    FindClose(FindRec);
  end;

  if FindFirst(Dir + '\*.exe', FindRec) then
  try
    repeat
      if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) = 0 then begin
        FilePath := Dir + '\' + FindRec.Name;
        Params := '/quiet /norestart';
        Exec(FilePath, Params, '', SW_HIDE, ewWaitUntilTerminated, RC);
      end;
    until not FindNext(FindRec);
  finally
    FindClose(FindRec);
  end;
end;

procedure InitializeWizard;
begin
  ModePage := CreateInputOptionWizardPage(
    wpWelcome,
    'Choose Setup Mode',
    'Pick how this installer should configure your system.',
    'First-Time Setup will create the shared folder structure and install prerequisites.'
  );
  ModePage.Add('First-Time Setup');
  ModePage.Add('Update/Repair');
  ModePage.Values[0] := True;

  SharedRootPage := CreateInputDirPage(
    ModePage.ID,
    'Choose Shared Drive Root',
    'The installer will create "SharedMeshDrive" under this location.',
    'Pick a drive letter or folder, e.g., D:\',
    False, ''
  );
  SharedRootPage.Add('Root drive or folder:');
  SharedRootPage.Values[0] := 'D:\';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if Assigned(SharedRootPage) and (PageID = SharedRootPage.ID) then
    Result := Assigned(ModePage) and (not ModePage.Values[0]);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if Assigned(SharedRootPage) and (CurPageID = SharedRootPage.ID) then begin
    SharedRoot := Trim(SharedRootPage.Values[0]);
    if SharedRoot = '' then begin
      MsgBox('Please choose a drive or folder.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then begin
    if Assigned(ModePage) and ModePage.Values[0] then begin
      if SharedRoot = '' then
        SharedRoot := SharedRootPage.Values[0];
      SeedConfigIni(ExpandConstant('{app}'), SharedRoot);
      RunAllInstallers(ExpandConstant('{tmp}\PhotomeshInstalls'));
      RunAllInstallers(ExpandConstant('{tmp}\RealityMeshInstalls'));
    end;
  end;
end;

procedure CurInstallFinished;
var
  RC: Integer;
begin
  if FileExists(ExpandConstant('{app}\update_photomesh_config.exe')) then
    Exec(ExpandConstant('{app}\update_photomesh_config.exe'), '', '{app}', SW_HIDE, ewWaitUntilTerminated, RC);
end;
