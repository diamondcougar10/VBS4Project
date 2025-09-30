; ===================== STE Mission Planning Toolkit Installer =====================
; Modes:
;  Host    – Creates "SharedMeshDrive", shares via SMB, seeds config by IP, optional M: map,
;            and runs PhotoMesh + RealityMesh installers if needed.
;  User    – Regular install, does not create share or drive, does not seed host/IP.
;  Update  – No layout/shares; just replace EXE and repair config.
; ================================================================================

#define AppName "STE Mission Planning Toolkit"
#define AppVersion "1.1"

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
; 1) Toolkit (PyInstaller dist)
Source: "dist\STE_Toolkit\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

; 2) Third-party installers (always staged; runtime decides to run or skip)
Source: "installs\Photomesh\*";  DestDir: "{tmp}\PhotomeshInstalls";  Flags: recursesubdirs createallsubdirs
Source: "installs\RealityMesh\*"; DestDir: "{tmp}\RealityMeshInstalls"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"
Name: "{userdesktop}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: checkedonce
Name: "firewall";    Description: "Allow STE Toolkit through Windows Firewall"; GroupDescription: "Windows Firewall:"; Flags: checkedonce

[Run]
Filename: "{app}\STE_Toolkit.exe"; \
    Parameters: "--fast-start --config ""{app}\config.ini"""; \
    Description: "Launch STE Mission Planning Toolkit now"; \
    Flags: nowait postinstall skipifsilent
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""STE Toolkit"" dir=in action=allow program=""{app}\STE_Toolkit.exe"" enable=yes"; Flags: runhidden; Tasks: firewall

[Registry]
Root: HKLM64; Subkey: "SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"; ValueType: string; ValueName: "{app}\STE_Toolkit.exe"; ValueData: "~ RUNASADMIN"; Flags: uninsdeletevalue uninsdeletekeyifempty

[Code]
const
  SHARE_NAME   = 'SharedMeshDrive';
  RM_LINK_NAME = 'Reality Mesh to VBS4.lnk';
  BEACON_FILE  = 'HostInfo.ini';

type
  TInstallMode = (imHost, imUser, imUpdate);

var
  { Custom mode page with visible radios (no GroupBox needed) }
  ModePage:  TWizardPage;
  ModeIntro: TNewStaticText;
  RBHost:    TNewRadioButton;
  RBUser:    TNewRadioButton;
  RBUpdate:  TNewRadioButton;
  ModeDesc:  TNewStaticText;

  SharedRootPage: TInputDirWizardPage;
  SharedRoot:     string;

function FileExists2(const P: string): Boolean;
begin
  Result := (P <> '') and FileExists(P);
end;

function IfThen(Cond: Boolean; const A, B: string): string;
begin 
  if Cond then Result := A else Result := B; 
end;

function WriteHostBeacon(const LocalBase, HostIP, HostName: string): Boolean;
var
  BeaconPath, Body, TS: string;
begin
  Result := False;
  if LocalBase = '' then Exit;

  BeaconPath := AddBackslash(LocalBase) + BEACON_FILE;
  TS := GetDateTimeString('yyyy-mm-dd hh:nn:ss', #0, #0);
  Body :=
    '[Host]' + #13#10 +
    'ip='   + HostIP   + #13#10 +
    'name=' + HostName + #13#10 +
    'share=' + SHARE_NAME + #13#10 +
    'timestamp=' + TS + #13#10;

  Result := SaveStringToFile(BeaconPath, Body, False);
end;

function TryReadBeaconIni(const FilePath: string; var OutIP, OutName: string): Boolean;
begin
  OutIP   := GetIniString('Host', 'ip',   '', FilePath);
  OutName := GetIniString('Host', 'name', '', FilePath);
  Result := (OutIP <> '');
end;

function DiscoverHostViaBeacon(var OutIP, OutName: string): Boolean;
var
  PS, OutIni, TmpPS: string;
  RC: Integer;
begin
  Result := False;
  OutIP := ''; OutName := '';

  OutIni := ExpandConstant('{tmp}\HostInfo_found.ini');
  DeleteFile(OutIni);

  { A compact PowerShell script that:
      1) gets active neighbors (Get-NetNeighbor) or arp -a fallback
      2) checks \\<IP>\SharedMeshDrive\HostInfo.ini
      3) copies the first hit to OutIni
    It exits quickly and touches few hosts. }
  PS :=
    '$share = ''' + SHARE_NAME + '''; ' +
    '$beacon = ''' + BEACON_FILE + '''; ' +
    '$out = ''' + OutIni + '''; ' +
    '$ips = @(); ' +
    'try { $ips = (Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue | ' +
    '  Where-Object { $_.IPAddress -notmatch ''^169\.254\.'' -and $_.IPAddress -ne ''127.0.0.1'' } | ' +
    '  Select-Object -ExpandProperty IPAddress) } catch {} ' +
    'if(-not $ips -or $ips.Count -eq 0) { ' +
    '  try { (arp -a) -split "`r?`n" | ForEach-Object { if($_ -match ''(\d{1,3}(?:\.\d{1,3}){3})'') { $ips += $Matches[1] } } } catch {} ' +
    '} ' +
    '$ips = $ips | Select-Object -Unique | Select-Object -First 64; ' +
    'foreach($ip in $ips) { ' +
    '  $p = "\\\\$ip\\$share\\$beacon"; ' +
    '  if (Test-Path -LiteralPath $p) { try { Copy-Item -LiteralPath $p -Destination $out -Force; break } catch {} } ' +
    '}';

  TmpPS := ExpandConstant('{tmp}\discover_beacon.ps1');
  SaveStringToFile(TmpPS, PS, False);

  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
       '-NoProfile -ExecutionPolicy Bypass -File "' + TmpPS + '"',
       '', SW_HIDE, ewWaitUntilTerminated, RC);

  DeleteFile(TmpPS);

  if FileExists(OutIni) then
  begin
    Result := TryReadBeaconIni(OutIni, OutIP, OutName);
    { temp file is small; keep for troubleshooting or delete if you prefer }
    // DeleteFile(OutIni);
  end;
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
  while (Result <> '') and (Result[Length(Result)] = '\') do
  begin
    if (Length(Result) = 3) and (Result[2] = ':') then Break;
    SetLength(Result, Length(Result) - 1);
  end;
end;

function BuildShareBase(const Root: string): string;
var Normalized: string; StartPos: Integer;
begin
  Normalized := Trim(TrimTrailingSlash(Root));
  if Normalized = '' then Normalized := 'D:\';
  StartPos := Length(Normalized) - Length(SHARE_NAME) + 1;
  if (StartPos >= 1) and
     (CompareText(Copy(Normalized, StartPos, Length(SHARE_NAME)), SHARE_NAME) = 0) and
     ((StartPos = 1) or (Normalized[StartPos - 1] = '\')) then
    Result := Normalized
  else
    Result := AddBackslash(Normalized) + SHARE_NAME;
end;

function ForceLayoutUnder(Root: string): string;
var Base, P: string;
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
var RC: Integer; Cmd: string; Ran: Boolean;
begin
  if LocalPath = '' then Exit;

  Cmd :=
    '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ' +
    '"$ErrorActionPreference=''Stop''; ' +
    'if (-not (Get-SmbShare -Name ''' + ShareName + ''' -ErrorAction SilentlyContinue)) { ' +
    '  New-SmbShare -Name ''' + ShareName + ''' -Path ''' + LocalPath + ''' -FullAccess ''Everyone'' | Out-Null ' +
    '}"';
  Ran := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
              Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC);
  if Ran and (RC = 0) then Exit;

  Cmd := '/C "net share ' + ShareName + '=""' + LocalPath + '"" /GRANT:Everyone,FULL"';
  Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC);
end;

function GetPrimaryIPv4(): string;
var PS, TmpFile: string; RC: Integer; S: AnsiString;
begin
  Result := '';
  TmpFile := ExpandConstant('{tmp}\host_ip.txt');

  PS :=
    '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ' +
    '"$ip = (Get-NetIPAddress -AddressFamily IPv4 | ' +
    '  Where-Object { $_.IPAddress -notmatch ''^169\.254\.'' -and $_.IPAddress -ne ''127.0.0.1'' } | ' +
    '  Sort-Object -Property InterfaceMetric | Select-Object -First 1 -ExpandProperty IPAddress); ' +
    'Set-Content -Path ''' + TmpFile + ''' -Value $ip -NoNewline -Encoding ASCII"';

  if Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
          PS, '', SW_HIDE, ewWaitUntilTerminated, RC) then
  begin
    if (RC = 0) and LoadStringFromFile(TmpFile, S) then
      Result := Trim(string(S));
  end;

  DeleteFile(TmpFile);
end;

function SeedConfigIni_Host(AppDir, Root: string): string;
var Ini, BundledIni, Base, HostName, HostIP: string;
begin
  Ini         := AddBackslash(AppDir) + 'config.ini';
  BundledIni  := AddBackslash(AppDir) + '_internal\config.ini';
  Base        := ForceLayoutUnder(Root);
  HostName    := ExpandConstant('{computername}');
  HostIP      := GetPrimaryIPv4();

  { Copy bundled config to main directory first, so we preserve existing settings }
  if FileExists(BundledIni) and not FileExists(Ini) then
    FileCopy(BundledIni, Ini, False);

  EnsureSmbShare(SHARE_NAME, Base);

  SetIniString('Offline', 'enabled', 'True',                  Ini);
  SetIniString('Offline', 'host_name', HostName,              Ini);
  SetIniString('Offline', 'host_ip',   HostIP,                Ini);
  SetIniString('Offline', 'share_name',SHARE_NAME,            Ini);
  SetIniString('Offline', 'local_data_root', Base,            Ini);
  SetIniString('Offline', 'working_fuser_subdir','WorkingFuser', Ini);
  SetIniString('Offline', 'working_fuser_host', HostName,     Ini);
  SetIniString('Offline', 'use_ip_unc', 'True',               Ini);

  SetIniString('SharedDrive', 'preferred_mode', 'UNC',        Ini);
  SetIniString('SharedDrive', 'drive_letter',   'M:',         Ini);
  SetIniString('SharedDrive', 'auto_map_on_save','True',      Ini);

  SetIniString('General', 'first_run_done', 'True',           Ini);
  SetIniString('General', 'first_run_mode', 'HOST',           Ini);
  SetIniString('General', 'reality_mesh_local_root', AddBackslash(Base) + 'RealityMeshInstall', Ini);

  if GetIniString('General', 'reality_mesh_to_vbs4', '', Ini) = '' then
    SetIniString('General', 'reality_mesh_to_vbs4', '\\{host}\SharedMeshDrive\RealityMeshInstall\' + RM_LINK_NAME, Ini);

  SetIniString('Fusers', 'desired_count', '3',                Ini);
  SetIniString('Fusers', 'host_count',    '1',                Ini);
  SetIniString('Fusers', 'fuser_computer','True',             Ini);
  SetIniString('Fusers', 'working_folder_host', HostName,     Ini);

  SetIniString('Network', 'host', HostIP,                     Ini);

  { NEW: drop a tiny beacon on the share so Users can auto-discover us }
  try
    WriteHostBeacon(Base, HostIP, HostName);
  except
    { ignore beacon write failures }
  end;

  Result := Base;
end;

procedure SeedConfigIni_User(AppDir, DiscoveredIP, DiscoveredName: string);
var
  Ini, BundledIni: string;
  UseIP: Boolean;
begin
  Ini        := AddBackslash(AppDir) + 'config.ini';
  BundledIni := AddBackslash(AppDir) + '_internal\config.ini';
  UseIP      := (Trim(DiscoveredIP) <> '');

  { Copy bundled config to main directory first, so we preserve existing settings }
  if FileExists(BundledIni) and not FileExists(Ini) then
    FileCopy(BundledIni, Ini, False);

  SetIniString('Offline', 'enabled', 'True',                Ini);
  SetIniString('Offline', 'host_name',  DiscoveredName,     Ini);
  SetIniString('Offline', 'host_ip',    DiscoveredIP,       Ini);
  SetIniString('Offline', 'share_name', SHARE_NAME,         Ini);
  SetIniString('Offline', 'local_data_root', '',            Ini);
  SetIniString('Offline', 'working_fuser_subdir','WorkingFuser', Ini);
  SetIniString('Offline', 'use_ip_unc', IfThen(UseIP, 'True', 'True'), Ini);

  SetIniString('SharedDrive', 'preferred_mode', 'UNC',  Ini);
  SetIniString('SharedDrive', 'drive_letter',   'M:',   Ini);
  SetIniString('SharedDrive', 'auto_map_on_save','True',Ini);

  SetIniString('General', 'first_run_done', 'True', Ini);
  SetIniString('General', 'first_run_mode', 'USER', Ini);

  SetIniString('Fusers', 'desired_count', '0',     Ini);
  SetIniString('Fusers', 'host_count',    '1',     Ini);
  SetIniString('Fusers', 'fuser_computer','False', Ini);

  if UseIP then
    SetIniString('Network', 'host', DiscoveredIP,  Ini);
end;

function HasShareRealityMesh(const Base: string): Boolean;
var Rec: TFindRec; Found: Boolean;
begin
  Result := False; Found := False;
  if FindFirst(AddBackslash(Base) + 'RealityMeshInstall\*', Rec) then
  try
    repeat
      if (CompareText(Rec.Name, RM_LINK_NAME) = 0) then
      begin Found := True; Break; end;
    until not FindNext(Rec);
  finally
    FindClose(Rec);
  end;
  Result := Found;
end;

function TryExecHidden(const Exe, Args: string): Boolean;
var RC: Integer;
begin
  Result := Exec(Exe, Args, '', SW_HIDE, ewWaitUntilTerminated, RC);
end;

procedure RunAllInstallers(const Dir, TargetDir: string);
var Rec: TFindRec; FilePath, Params: string;
begin
  if not DirExists(Dir) then Exit;
  if (TargetDir <> '') and (not DirExists(TargetDir)) then ForceDirectories(TargetDir);

  if FindFirst(Dir + '\*.msi', Rec) then
  try
    repeat
      if (Rec.Attributes and FILE_ATTRIBUTE_DIRECTORY) = 0 then
      begin
        FilePath := Dir + '\' + Rec.Name;
        Params   := '/i "' + FilePath + '" /qn /norestart ALLUSERS=1';
        if TargetDir <> '' then Params := Params + ' TARGETDIR="' + TargetDir + '"';
        TryExecHidden(ExpandConstant('{sys}\msiexec.exe'), Params);
      end;
    until not FindNext(Rec);
  finally
    FindClose(Rec);
  end;

  if FindFirst(Dir + '\*.exe', Rec) then
  try
    repeat
      if (Rec.Attributes and FILE_ATTRIBUTE_DIRECTORY) = 0 then
      begin
        FilePath := Dir + '\' + Rec.Name;
        if TargetDir <> '' then
        begin
          if not TryExecHidden(FilePath, '/quiet /norestart INSTALLDIR="' + TargetDir + '"') then
            if not TryExecHidden(FilePath, '/verysilent /norestart INSTALLDIR="' + TargetDir + '"') then
              if not TryExecHidden(FilePath, '/S') then
                TryExecHidden(FilePath, '/s');
        end
        else
        begin
          if not TryExecHidden(FilePath, '/quiet /norestart') then
            if not TryExecHidden(FilePath, '/verysilent /norestart') then
              if not TryExecHidden(FilePath, '/S') then
                TryExecHidden(FilePath, '/s');
        end;
      end;
    until not FindNext(Rec);
  finally
    FindClose(Rec);
  end;
end;

function SelectedMode(): TInstallMode;
begin
  if RBHost.Checked then Result := imHost
  else if RBUser.Checked then Result := imUser
  else Result := imUpdate;
end;

procedure RefreshModeDescription;
var S: string;
begin
  case SelectedMode() of
    imHost:
      S := 'HOST: Creates "SharedMeshDrive" on a local drive, shares it over the LAN (\\<IP>\SharedMeshDrive), ' +
           'seeds config with your PC name and IP, creates a discovery beacon for User installs, and installs PhotoMesh + Reality Mesh payloads into the shared structure.';
    imUser:
      S := 'USER: Regular install without creating a shared drive. Automatically discovers and connects to Host if available on the LAN. ' +
           'If no Host is found, Host/IP is left blank in settings so you can set it manually later.';
    imUpdate:
      S := 'UPDATE/REPAIR: Replaces the Toolkit binaries and repairs config. Attempts to auto-discover Host if not already configured. No sharing, drive layout, or third-party installs.';
  end;
  ModeDesc.Caption := S;
end;

procedure ModeRadioClicked(Sender: TObject);
begin
  RefreshModeDescription;
end;

procedure InitializeWizard;
var
  LeftX, TopY, SpY, AvailW: Integer;
begin
  ModePage := CreateCustomPage(
    wpWelcome,
    'Choose Setup Mode',
    'Pick how this installer should configure your system.'
  );

  { Layout }
  LeftX := ScaleX(24);
  TopY  := ScaleY(22);
  SpY   := ScaleY(10);
  AvailW := ModePage.SurfaceWidth - (LeftX * 2);

  ModeIntro := TNewStaticText.Create(WizardForm);
  ModeIntro.Parent   := ModePage.Surface;
  ModeIntro.Left     := LeftX;
  ModeIntro.Top      := TopY;
  ModeIntro.Caption  := 'Select one option below.';

  RBHost := TNewRadioButton.Create(WizardForm);
  RBHost.Parent  := ModePage.Surface;            { radios share the same parent => exclusive }
  RBHost.Left    := LeftX;
  RBHost.Top     := ModeIntro.Top + ModeIntro.Height + SpY + ScaleY(2);
  RBHost.Width   := AvailW;                      { wide to avoid truncation }
  RBHost.Caption := 'Host';
  RBHost.Checked := True;
  RBHost.OnClick := @ModeRadioClicked;

  RBUser := TNewRadioButton.Create(WizardForm);
  RBUser.Parent  := ModePage.Surface;
  RBUser.Left    := LeftX;
  RBUser.Top     := RBHost.Top + RBHost.Height + SpY;
  RBUser.Width   := AvailW;
  RBUser.Caption := 'User';
  RBUser.OnClick := @ModeRadioClicked;

  RBUpdate := TNewRadioButton.Create(WizardForm);
  RBUpdate.Parent  := ModePage.Surface;
  RBUpdate.Left    := LeftX;
  RBUpdate.Top     := RBUser.Top + RBUser.Height + SpY;
  RBUpdate.Width   := AvailW;
  RBUpdate.Caption := 'Update';
  RBUpdate.OnClick := @ModeRadioClicked;

  ModeDesc := TNewStaticText.Create(WizardForm);
  ModeDesc.Parent   := ModePage.Surface;
  ModeDesc.AutoSize := False;
  ModeDesc.Left     := LeftX;
  ModeDesc.Top      := RBUpdate.Top + RBUpdate.Height + SpY + ScaleY(4);
  ModeDesc.Width    := AvailW;
  ModeDesc.Height   := ScaleY(80);
  ModeDesc.WordWrap := True;

  RefreshModeDescription;

  { Host-only page for the shared drive root }
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
    Result := SelectedMode() <> imHost;  { only for Host }
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var Candidate: string;
begin
  Result := True;

  if (CurPageID = ModePage.ID) then
  begin
    if not (RBHost.Checked or RBUser.Checked or RBUpdate.Checked) then
    begin
      MsgBox('Please select one mode (Host, User, or Update).', mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end;

  if Assigned(SharedRootPage) and (CurPageID = SharedRootPage.ID) then
  begin
    Candidate := Trim(SharedRootPage.Values[0]);
    if Candidate = '' then
    begin
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
  DscIP, DscName: string;  { NEW: for host discovery }
  IniPath, BundledIni: string;         { NEW: for update case and config copying }
begin
  if CurStep = ssInstall then
  begin
    AppDir := ExpandConstant('{app}');
    HostRoot := '';

    case SelectedMode() of
      imHost:
      begin
        if SharedRoot <> '' then HostRoot := SharedRoot else HostRoot := 'D:\';
        Base := SeedConfigIni_Host(AppDir, HostRoot);

        NeedPhotoMesh   := not HasPhotoMeshWizard();
        NeedRealityMesh := not HasShareRealityMesh(Base);

        if NeedPhotoMesh then
          RunAllInstallers(ExpandConstant('{tmp}\PhotomeshInstalls'), '')
        else
          Log('PhotoMesh Wizard present; skipping Photomesh installers.');

        if NeedRealityMesh then
          RunAllInstallers(ExpandConstant('{tmp}\RealityMeshInstalls'),
                           AddBackslash(Base) + 'RealityMeshInstall')
        else
          Log('Reality Mesh found under share; skipping RealityMesh installers.');

        Ip := GetPrimaryIPv4();
        if Ip <> '' then
        begin
          Cmd := '/C "net use M: \\' + Ip + '\' + SHARE_NAME + ' /persistent:yes"';
          Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC);
        end;
      end;

      imUser:
      begin
        { NEW: quick auto-discovery of Host beacon }
        DscIP := ''; DscName := '';
        if DiscoverHostViaBeacon(DscIP, DscName) then
          Log(Format('Beacon found: host_ip=%s name=%s', [DscIP, DscName]))
        else
          Log('Beacon not found; leaving host_ip blank');

        SeedConfigIni_User(AppDir, DscIP, DscName);
      end;

      imUpdate:
      begin
        { Keep existing config, but if Offline.host_ip is blank, try to discover }
        IniPath := AddBackslash(AppDir) + 'config.ini';
        
        { Ensure config exists in main directory }
        if not FileExists(IniPath) then
        begin
          BundledIni := AddBackslash(AppDir) + '_internal\config.ini';
          if FileExists(BundledIni) then
            FileCopy(BundledIni, IniPath, False);
        end;
        
        if GetIniString('Offline','host_ip','', IniPath) = '' then
        begin
          DscIP := ''; DscName := '';
          if DiscoverHostViaBeacon(DscIP, DscName) and (DscIP <> '') then
          begin
            SetIniString('Offline','host_ip', DscIP, IniPath);
            if DscName <> '' then
              SetIniString('Offline','host_name', DscName, IniPath);
            SetIniString('Network','host', DscIP, IniPath);
            Log(Format('Update: auto-filled blank host_ip with discovered %s', [DscIP]));
          end;
        end;
        { otherwise leave Update behavior unchanged }
      end;
    end;

    if SelectedMode() = imHost then
    begin
      if HostRoot = '' then HostRoot := 'D:\';
      RMTarget := AddBackslash(BuildShareBase(HostRoot)) + 'RealityMeshInstall\' + RM_LINK_NAME;
      { No-op if already present/created by installers }
    end;
  end;
end;

procedure CurInstallFinished;
var RC: Integer;
begin
  if FileExists(ExpandConstant('{app}\update_photomesh_config.exe')) then
    Exec(ExpandConstant('{app}\update_photomesh_config.exe'), '', '{app}', SW_HIDE, ewWaitUntilTerminated, RC);
end;
