; ===================== STE Mission Planning Toolkit Installer =====================
; Three modes:
;  - First-Time Setup (Host): create SharedMeshDrive, share via SMB, seed config by IP,
;    (optionally) map M:, and run PhotoMesh + RealityMesh installers.
;  - First-Time Setup (User): regular install; DO NOT create share or drive; DO NOT seed host;
;    leave host name/IP blank so the Toolkit UI can point to the Host later.
;  - Update/Repair: do not touch layout/shares; just replace EXE and repair config.
; All helper shells run hidden. Config seed writes to {app}\config.ini.
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

[Files]
; 1) Your application (PyInstaller dist)
Source: "dist\STE_Toolkit\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

; 2) Third-party installers — always stage; runtime decides whether to run
Source: "installs\Photomesh\*";  DestDir: "{tmp}\PhotomeshInstalls";  Flags: recursesubdirs createallsubdirs
Source: "installs\RealityMesh\*"; DestDir: "{tmp}\RealityMeshInstalls"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"
Name: "{userdesktop}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: checkedonce
Name: "firewall";    Description: "Allow STE Toolkit through Windows Firewall"; GroupDescription: "Windows Firewall:"; Flags: checkedonce

[Run]
; Launch Toolkit when finished
Filename: "{app}\STE_Toolkit.exe"; Description: "Launch STE Mission Planning Toolkit now"; Flags: nowait postinstall skipifsilent
; Optional firewall rule
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""STE Toolkit"" dir=in action=allow program=""{app}\STE_Toolkit.exe"" enable=yes"; Flags: runhidden; Tasks: firewall

[Registry]
; Always run as admin (compat layer)
Root: HKLM64; Subkey: "SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"; ValueType: string; ValueName: "{app}\STE_Toolkit.exe"; ValueData: "~ RUNASADMIN"; Flags: uninsdeletevalue uninsdeletekeyifempty

[Code]
const
  SHARE_NAME   = 'SharedMeshDrive';
  RM_LINK_NAME = 'Reality Mesh to VBS4.lnk';

type
  TInstallMode = (imHost, imUser, imUpdate);

var
  ModePage: TInputOptionWizardPage;
  SharedRootPage: TInputDirWizardPage;
  ModeDesc: TNewStaticText;
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

function TrimTrailingSlash(Path: string): string;
begin
  Result := Path;
  while (Result <> '') and (Result[Length(Result)] = '\') do begin
    if (Length(Result) = 3) and (Result[2] = ':') then Break;
    SetLength(Result, Length(Result) - 1);
  end;
end;

function BuildShareBase(const Root: string): string;
var
  Normalized: string;
  StartPos: Integer;
begin
  Normalized := Trim(TrimTrailingSlash(Root));
  if Normalized = '' then
    Normalized := 'D:\';
  StartPos := Length(Normalized) - Length(SHARE_NAME) + 1;
  if (StartPos >= 1) and
     (CompareText(Copy(Normalized, StartPos, Length(SHARE_NAME)), SHARE_NAME) = 0) and
     ((StartPos = 1) or (Normalized[StartPos - 1] = '\')) then
    Result := Normalized
  else
    Result := AddBackslash(Normalized) + SHARE_NAME;
end;

function ForceLayoutUnder(Root: string): string;
var
  Base, P: string;
begin
  Base := BuildShareBase(Root);
  ForceDirectories(Base);
  P := AddBackslash(Base) + 'WorkingFuser';        ForceDirectories(P);
  P := AddBackslash(Base) + 'Projects';            ForceDirectories(P);
  P := AddBackslash(Base) + 'RealityMeshInstall';  ForceDirectories(P);
  P := AddBackslash(Base) + 'UnprocessedPhotos';   ForceDirectories(P);
  P := AddBackslash(Base) + 'RealityMeshOutput';   ForceDirectories(P);
  Result := Base;
end;

procedure EnsureSmbShare(const ShareName, LocalPath: string);
var
  RC: Integer;
  Cmd: string;
  Ran: Boolean;
begin
  if LocalPath = '' then
    Exit;

  { 1) Try PowerShell silently }
  Cmd :=
    '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ' +
    '"$ErrorActionPreference=''Stop''; ' +
    'if (-not (Get-SmbShare -Name ''' + ShareName + ''' -ErrorAction SilentlyContinue)) { ' +
    '  New-SmbShare -Name ''' + ShareName + ''' -Path ''' + LocalPath + ''' -FullAccess ''Everyone'' | Out-Null ' +
    '}"';
  Ran := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
              Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC);
  if Ran and (RC = 0) then begin
    Log(Format('SMB share ensured (PowerShell): %s -> %s', [ShareName, LocalPath]));
    Exit;
  end;

  { 2) Fallback to net share (cmd) silently }
  Cmd := '/C "net share ' + ShareName + '=""' + LocalPath + '"" /GRANT:Everyone,FULL"';
  Ran := Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC);
  if Ran and (RC = 0) then
    Log(Format('SMB share ensured (net share): %s -> %s', [ShareName, LocalPath]))
  else
    Log(Format('SMB share creation skipped or failed (rc=%d) for %s', [RC, LocalPath]));
end;
function GetPrimaryIPv4(): string;
var
  PS, TmpFile: string;
  RC: Integer;
  S: AnsiString;  // ← must be AnsiString for LoadStringFromFile
begin
  Result := '';
  TmpFile := ExpandConstant('{tmp}\host_ip.txt');

  PS :=
    '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ' +
    '"$ip = (Get-NetIPAddress -AddressFamily IPv4 | ' +
    '  Where-Object { $_.IPAddress -notmatch ''^169\.254\.'' -and $_.IPAddress -ne ''127.0.0.1'' } | ' +
    '  Sort-Object -Property InterfaceMetric | Select-Object -First 1 -ExpandProperty IPAddress); ' +
    'Set-Content -Path ''' + TmpFile + ''' -Value $ip -NoNewline -Encoding ASCII"';   // force ASCII

  if Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), PS, '', SW_HIDE, ewWaitUntilTerminated, RC) then
  begin
    if (RC = 0) and LoadStringFromFile(TmpFile, S) then
      Result := Trim(string(S)); // cast AnsiString → string
  end;

  DeleteFile(TmpFile);
end;

function SeedConfigIni_Host(AppDir, Root: string): string;
var
  Ini, Base, HostName, HostIP: string;
begin
  Ini      := AddBackslash(AppDir) + 'config.ini';
  Base     := ForceLayoutUnder(Root);
  HostName := ExpandConstant('{computername}');
  HostIP   := GetPrimaryIPv4();

  EnsureSmbShare(SHARE_NAME, Base);

  SetIniString('Offline', 'enabled', 'True',          Ini);
  SetIniString('Offline', 'host_name', HostName,      Ini);
  SetIniString('Offline', 'host_ip',   HostIP,        Ini);
  SetIniString('Offline', 'share_name',SHARE_NAME,    Ini);
  SetIniString('Offline', 'local_data_root', Base,    Ini);
  SetIniString('Offline', 'working_fuser_subdir','WorkingFuser', Ini);
  SetIniString('Offline', 'working_fuser_host', HostName, Ini);
  SetIniString('Offline', 'use_ip_unc', 'True',       Ini);  { use \\<IP>\share }

  SetIniString('SharedDrive', 'preferred_mode', 'UNC', Ini); { default to UNC/IP }
  SetIniString('SharedDrive', 'drive_letter',   'M:',  Ini);
  SetIniString('SharedDrive', 'auto_map_on_save','True', Ini);

  SetIniString('General', 'first_run_done', 'True', Ini);
  SetIniString('General', 'first_run_mode', 'HOST', Ini);
  SetIniString('General', 'reality_mesh_local_root', AddBackslash(Base) + 'RealityMeshInstall', Ini);

  if GetIniString('General', 'reality_mesh_to_vbs4', '', Ini) = '' then
    SetIniString('General', 'reality_mesh_to_vbs4', '\\{host}\SharedMeshDrive\RealityMeshInstall\' + RM_LINK_NAME, Ini);

  SetIniString('Fusers', 'desired_count', '3',        Ini);
  SetIniString('Fusers', 'host_count',    '1',        Ini);
  SetIniString('Fusers', 'fuser_computer','True',     Ini);
  SetIniString('Fusers', 'working_folder_host', HostName, Ini);

  Result := Base;
end;

procedure SeedConfigIni_User(AppDir: string);
var
  Ini: string;
begin
  Ini := AddBackslash(AppDir) + 'config.ini';
  SetIniString('Offline', 'enabled', 'True',          Ini);
  SetIniString('Offline', 'host_name',  '',           Ini);   { blank on user PCs }
  SetIniString('Offline', 'host_ip',    '',           Ini);   { will be set in UI }
  SetIniString('Offline', 'share_name', SHARE_NAME,   Ini);
  SetIniString('Offline', 'local_data_root', '',      Ini);   { no local layout }
  SetIniString('Offline', 'working_fuser_subdir','WorkingFuser', Ini);
  SetIniString('Offline', 'use_ip_unc', 'True',       Ini);

  SetIniString('SharedDrive', 'preferred_mode', 'UNC', Ini);
  SetIniString('SharedDrive', 'drive_letter',   'M:',  Ini);
  SetIniString('SharedDrive', 'auto_map_on_save','True', Ini);

  SetIniString('General', 'first_run_done', 'True', Ini);
  SetIniString('General', 'first_run_mode', 'USER', Ini);

  SetIniString('Fusers', 'desired_count', '0',        Ini);
  SetIniString('Fusers', 'host_count',    '1',        Ini);
  SetIniString('Fusers', 'fuser_computer','False',    Ini);
end;

function HasShareRealityMesh(const Base: string): Boolean;
var
  Rec: TFindRec;
  Found: Boolean;
begin
  Result := False;
  Found := False;
  if FindFirst(AddBackslash(Base) + 'RealityMeshInstall\*', Rec) then
  try
    repeat
      if (CompareText(Rec.Name, RM_LINK_NAME) = 0) then begin
        Found := True;
        Break;
      end;
    until not FindNext(Rec);
  finally
    FindClose(Rec);
  end;
  Result := Found;
end;

function TryExecHidden(const Exe, Args: string): Boolean;
var
  RC: Integer;
begin
  Result := Exec(Exe, Args, '', SW_HIDE, ewWaitUntilTerminated, RC);
  if Result then
    Log(Format('Ran %s (%s) -> rc=%d', [Exe, Args, RC]))
  else
    Log(Format('Failed launching %s (%s)', [Exe, Args]));
end;

procedure RunAllInstallers(const Dir, TargetDir: string);
var
  FindRec: TFindRec;
  FilePath, Params: string;
begin
  if not DirExists(Dir) then begin
    Log('Installer payload missing: ' + Dir);
    Exit;
  end;

  if (TargetDir <> '') and (not DirExists(TargetDir)) then
    ForceDirectories(TargetDir);

  { MSI payloads }
  if FindFirst(Dir + '\*.msi', FindRec) then
  try
    repeat
      if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) = 0 then begin
        FilePath := Dir + '\' + FindRec.Name;
        Params   := '/i "' + FilePath + '" /qn /norestart ALLUSERS=1';
        if TargetDir <> '' then
          Params := Params + ' TARGETDIR="' + TargetDir + '"';
        TryExecHidden(ExpandConstant('{sys}\msiexec.exe'), Params);
      end;
    until not FindNext(FindRec);
  finally
    FindClose(FindRec);
  end;

  { EXE payloads — try silent switches; add INSTALLDIR when supported }
  if FindFirst(Dir + '\*.exe', FindRec) then
  try
    repeat
      if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) = 0 then begin
        FilePath := Dir + '\' + FindRec.Name;
        if TargetDir <> '' then begin
          if not TryExecHidden(FilePath, '/quiet /norestart INSTALLDIR="' + TargetDir + '"') then
            if not TryExecHidden(FilePath, '/verysilent /norestart INSTALLDIR="' + TargetDir + '"') then
              if not TryExecHidden(FilePath, '/S') then
                TryExecHidden(FilePath, '/s');
        end else begin
          if not TryExecHidden(FilePath, '/quiet /norestart') then
            if not TryExecHidden(FilePath, '/verysilent /norestart') then
              if not TryExecHidden(FilePath, '/S') then
                TryExecHidden(FilePath, '/s');
        end;
      end;
    until not FindNext(FindRec);
  finally
    FindClose(FindRec);
  end;
end;

function SelectedMode(): TInstallMode;
begin
  if ModePage.SelectedValueIndex = 0 then
    Result := imHost
  else if ModePage.SelectedValueIndex = 1 then
    Result := imUser
  else
    Result := imUpdate;
end;
procedure RefreshModeDescription;
var
  S: string;
begin
  case SelectedMode() of
    imHost:
      S := 'HOST: Creates "SharedMeshDrive" on a local drive, shares it over the LAN (\\<IP>\SharedMeshDrive), ' +
           'seeds config with your PC name and IP, and installs PhotoMesh + Reality Mesh payloads into the shared structure.';
    imUser:
      S := 'USER: Regular install without creating a shared drive. Does not map or share anything. ' +
           'Host/IP is left blank in settings so you can point to the Host later.';
    imUpdate:
      S := 'UPDATE/REPAIR: Replaces the Toolkit binaries and repairs config. No sharing, drive layout, or third-party installs.';
  end;
  ModeDesc.Caption := S;
end;

procedure ModeRadioClicked(Sender: TObject);
begin
  RefreshModeDescription;
end;
procedure InitializeWizard;
var
  i: Integer;  // <-- locals must be declared here
begin
  ModePage := CreateInputOptionPage(
    wpWelcome,
    'Choose Setup Mode',
    'Pick how this installer should configure your system.',
    'Select one option below.',
    False, False
  );
  ModePage.Add('First-Time Setup (Host)');
  ModePage.Add('First-Time Setup (User)');
  ModePage.Add('Update/Repair');
  ModePage.Values[0] := True;

  ModeDesc := TNewStaticText.Create(WizardForm);
  ModeDesc.Parent := ModePage.Surface;
  ModeDesc.AutoSize := False;
  ModeDesc.Left := 0;
  ModeDesc.Top := ModePage.SurfaceHeight - ScaleY(60);
  ModeDesc.Width := ModePage.SurfaceWidth;
  ModeDesc.Height := ScaleY(56);
  ModeDesc.WordWrap := True;

  RefreshModeDescription;  // set initial text

  // Wire all radios on the page to our click handler
  for i := 0 to ModePage.Surface.ControlCount - 1 do
    if ModePage.Surface.Controls[i] is TNewRadioButton then
      TNewRadioButton(ModePage.Surface.Controls[i]).OnClick := @ModeRadioClicked;

  // Create the "Shared drive root" page (needed by ShouldSkipPage / NextButtonClick)
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
    Result := SelectedMode() <> imHost;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Candidate: string;
begin
  Result := True;
  if Assigned(SharedRootPage) and (CurPageID = SharedRootPage.ID) then begin
    Candidate := Trim(SharedRootPage.Values[0]);
    if Candidate = '' then begin
      MsgBox('Please choose a drive or folder.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    SharedRoot := Candidate;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  AppDir, Base, RMTarget, HostRoot, Cmd, Ip: string;
  NeedPhotoMesh, NeedRealityMesh: Boolean;
  RC: Integer;
begin
  if CurStep = ssInstall then begin
    AppDir := ExpandConstant('{app}');
    HostRoot := '';

    case SelectedMode() of
      imHost:
      begin
        if SharedRoot <> '' then
          HostRoot := SharedRoot
        else
          HostRoot := 'D:\';
        Base := SeedConfigIni_Host(AppDir, HostRoot);

        NeedPhotoMesh   := not HasPhotoMeshWizard();
        NeedRealityMesh := not HasShareRealityMesh(Base);

        if NeedPhotoMesh then begin
          Log('PhotoMesh Wizard not detected; running Photomesh installers.');
          RunAllInstallers(ExpandConstant('{tmp}\PhotomeshInstalls'), '');
        end else
          Log('PhotoMesh Wizard present; skipping Photomesh installers.');

        if NeedRealityMesh then begin
          Log('Reality Mesh not found under share; running RealityMesh installers.');
          RunAllInstallers(ExpandConstant('{tmp}\RealityMeshInstalls'), AddBackslash(Base) + 'RealityMeshInstall');
        end else
          Log('Reality Mesh found under share; skipping RealityMesh installers.');

        { Map M: to \\<this-IP>\SharedMeshDrive silently (optional) }
        Ip := GetPrimaryIPv4();
        if Ip <> '' then begin
          Cmd := '/C "net use M: \\' + Ip + '\\' + SHARE_NAME + ' /persistent:yes"';
          Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC);
        end;
      end;

      imUser:
      begin
        SeedConfigIni_User(AppDir);
      end;

      imUpdate:
      begin
        { No layout/shares; leave config in place. }
      end;
    end;

    if SelectedMode() = imHost then begin
      if HostRoot = '' then
        HostRoot := 'D:\';
      RMTarget := AddBackslash(BuildShareBase(HostRoot)) + 'RealityMeshInstall\' + RM_LINK_NAME;
      { No-op if existing; created by the installers or present already. }
    end;
  end;
end;

procedure CurInstallFinished;
var
  RC: Integer;
begin
  { Wizard config hardening / OBJ-only flips happen here, silently }
  if FileExists(ExpandConstant('{app}\update_photomesh_config.exe')) then
    Exec(ExpandConstant('{app}\update_photomesh_config.exe'), '', '{app}', SW_HIDE, ewWaitUntilTerminated, RC);
end;
