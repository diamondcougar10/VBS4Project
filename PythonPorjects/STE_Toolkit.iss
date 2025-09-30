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
    Parameters: "--fast-start"; \
    Description: "Launch STE Mission Planning Toolkit now"; \
    Flags: nowait postinstall skipifsilent
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""STE Toolkit"" dir=in action=allow program=""{app}\STE_Toolkit.exe"" enable=yes"; Flags: runhidden; Tasks: firewall

[Registry]
Root: HKLM64; Subkey: "SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"; ValueType: string; ValueName: "{app}\STE_Toolkit.exe"; ValueData: "~ RUNASADMIN"; Flags: uninsdeletevalue uninsdeletekeyifempty

[Code]
const
  SHARE_NAME   = 'SharedMeshDrive';
  RM_LINK_NAME = 'Reality Mesh to VBS4.lnk';

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
var Ini, Base, HostName, HostIP: string;
begin
  Ini      := AddBackslash(AppDir) + 'config.ini';
  Base     := ForceLayoutUnder(Root);
  HostName := ExpandConstant('{computername}');
  HostIP   := GetPrimaryIPv4();

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

  Result := Base;
end;

procedure SeedConfigIni_User(AppDir: string);
var Ini: string;
begin
  Ini := AddBackslash(AppDir) + 'config.ini';
  SetIniString('Offline', 'enabled', 'True',          Ini);
  SetIniString('Offline', 'host_name',  '',           Ini);
  SetIniString('Offline', 'host_ip',    '',           Ini);
  SetIniString('Offline', 'share_name', 'SharedMeshDrive',   Ini);
  SetIniString('Offline', 'local_data_root', '',      Ini);
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
        SeedConfigIni_User(AppDir);

      imUpdate:
        ; { Leave config/layout as-is }
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
