; ===================== STE Mission Planning Toolkit Installer =====================
; Creates the SharedMeshDrive layout, runs prerequisite installers when required,
; and seeds config.ini for a zero-touch first launch.
; ==============================================================================
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
Source: "dist\STE_Toolkit\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "installs\Photomesh\*"; DestDir: "{tmp}\PhotomeshInstalls"; Flags: recursesubdirs createallsubdirs; Check: ShouldRunPrereqs
Source: "installs\RealityMesh\*"; DestDir: "{tmp}\RealityMeshInstalls"; Flags: recursesubdirs createallsubdirs; Check: ShouldRunPrereqs

[Icons]
Name: "{group}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"
Name: "{userdesktop}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a &desktop icon"; Flags: unchecked
Name: firewall;    Description: "Allow STE Toolkit through Windows Firewall"; Flags: unchecked

[Run]
Filename: "{app}\STE_Toolkit.exe"; Description: "Launch STE Mission Planning Toolkit now"; Flags: nowait postinstall skipifsilent
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""STE Toolkit"" dir=in action=allow program=""{app}\STE_Toolkit.exe"" enable=yes"; Flags: runhidden; Tasks: firewall

[Registry]
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"; ValueType: string; ValueName: "{app}\STE_Toolkit.exe"; ValueData: "~ RUNASADMIN"; Flags: uninsdeletevalue uninsdeletekeyifempty

[Code]
const
  SHARE_NAME   = 'SharedMeshDrive';
  RM_LINK_NAME = 'Reality Mesh to VBS4.lnk';

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

function TrimTrailingSlash(Path: string): string;
begin
  Result := Path;
  while (Result <> '') and (Result[Length(Result)] = '\') do begin
    if (Length(Result) = 3) and (Result[2] = ':') then
      Break;
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
  Cmd, EscShare, EscPath: string;
  Ran: Boolean;
begin
  if LocalPath = '' then
    Exit;

  EscShare := ShareName;
  EscPath := LocalPath;
  StringChangeEx(EscShare, '''', '''''', True);
  StringChangeEx(EscPath, '''', '''''', True);

  Cmd :=
    '-NoProfile -ExecutionPolicy Bypass -Command ' +
    '"$ErrorActionPreference=''Stop''; ' +
    'if (-not (Get-SmbShare -Name ''' + EscShare + ''' -ErrorAction SilentlyContinue)) { ' +
    '  New-SmbShare -Name ''' + EscShare + ''' -Path ''' + EscPath + ''' -FullAccess ''Everyone'' | Out-Null ' +
    '}"';
  Ran := Exec(
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    Cmd,
    '', SW_HIDE, ewWaitUntilTerminated, RC);
  if Ran and (RC = 0) then begin
    Log(Format('SMB share ensured via PowerShell (%s -> %s)', [ShareName, LocalPath]));
    Exit;
  end;

  Cmd := '/C "net share ' + ShareName + '="' + LocalPath + '" /GRANT:Everyone,FULL"';
  Ran := Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC);
  if Ran and (RC = 0) then
    Log(Format('SMB share ensured via net share (%s -> %s)', [ShareName, LocalPath]))
  else
    Log(Format('SMB share creation skipped or failed (rc=%d) for %s', [RC, LocalPath]));
end;

function DetermineDriveLetter(const Base, Ini: string): string;
var
  Drive, Existing: string;
begin
  Drive := ExtractFileDrive(Base);
  if (Length(Drive) = 2) and (Drive[2] = ':') then
    Result := UpperCase(Drive)
  else begin
    Existing := GetIniString('SharedDrive', 'drive_letter', '', Ini);
    if Existing <> '' then
      Result := Existing
    else
      Result := 'D:';
  end;
end;

function SeedConfigIni(AppDir, Root: string): string;
var
  Ini, Base, DriveLetter, Template, HostName: string;
begin
  Ini := AddBackslash(AppDir) + 'config.ini';
  Base := ForceLayoutUnder(Root);
  HostName := ExpandConstant('{computername}');
  EnsureSmbShare(SHARE_NAME, Base);

  SetIniString('Offline', 'enabled', 'True', Ini);
  SetIniString('Offline', 'host_name', HostName, Ini);
  SetIniString('Offline', 'host_ip', '', Ini);
  SetIniString('Offline', 'share_name', SHARE_NAME, Ini);
  SetIniString('Offline', 'local_data_root', Base, Ini);
  SetIniString('Offline', 'working_fuser_subdir', 'WorkingFuser', Ini);
  SetIniString('Offline', 'working_fuser_host', HostName, Ini);
  SetIniString('Offline', 'use_ip_unc', 'False', Ini);

  DriveLetter := DetermineDriveLetter(Base, Ini);
  SetIniString('SharedDrive', 'preferred_mode', 'DRIVE', Ini);
  SetIniString('SharedDrive', 'drive_letter', DriveLetter, Ini);
  SetIniString('SharedDrive', 'auto_map_on_save', 'True', Ini);

  SetIniString('General', 'first_run_done', 'True', Ini);
  SetIniString('General', 'reality_mesh_local_root', AddBackslash(Base) + 'RealityMeshInstall', Ini);

  if GetIniString('General', 'reality_mesh_to_vbs4', '', Ini) = '' then begin
    Template := '\\{host}\SharedMeshDrive\RealityMeshInstall\' + RM_LINK_NAME;
    SetIniString('General', 'reality_mesh_to_vbs4', Template, Ini);
  end;

  SetIniString('Fusers', 'desired_count', '3', Ini);
  SetIniString('Fusers', 'host_count', '1', Ini);
  SetIniString('Fusers', 'fuser_computer', 'False', Ini);
  SetIniString('Fusers', 'working_folder_host', HostName, Ini);

  Result := Base;
end;

function SelectedRoot(): string;
begin
  if SharedRoot <> '' then
    Result := SharedRoot
  else if Assigned(SharedRootPage) then
    Result := Trim(SharedRootPage.Values[0])
  else
    Result := '';
  if Result = '' then
    Result := 'D:\';
end;

function GetExistingLocalDataRoot(const AppDir: string): string;
var
  Ini, LocalRoot, RMRoot: string;
begin
  Ini := AddBackslash(AppDir) + 'config.ini';
  LocalRoot := GetIniString('Offline', 'local_data_root', '', Ini);
  if LocalRoot <> '' then begin
    Result := LocalRoot;
    Exit;
  end;

  RMRoot := GetIniString('General', 'reality_mesh_local_root', '', Ini);
  if RMRoot <> '' then
    Result := ExtractFileDir(RMRoot)
  else
    Result := '';
end;

function DetermineShareRoot(const AppDir: string; IsFirstTime: Boolean): string;
begin
  if IsFirstTime then
    Result := SelectedRoot()
  else begin
    Result := GetExistingLocalDataRoot(AppDir);
    if Result = '' then
      Result := SelectedRoot();
  end;
  if Result = '' then
    Result := 'D:\';
end;

function FindRealityMeshLinkInDir(const Root: string; var Found: string): Boolean;
var
  Rec: TFindRec;
  Path: string;
begin
  Result := False;
  Found := '';
  if not DirExists(Root) then
    Exit;

  if FileExists(AddBackslash(Root) + RM_LINK_NAME) then begin
    Found := AddBackslash(Root) + RM_LINK_NAME;
    Result := True;
    Exit;
  end;

  if FindFirst(AddBackslash(Root) + '*', Rec) then
  try
    repeat
      if (Rec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then begin
        if (Rec.Name <> '.') and (Rec.Name <> '..') then begin
          Path := AddBackslash(Root) + Rec.Name;
          if FindRealityMeshLinkInDir(Path, Found) then begin
            Result := True;
            Exit;
          end;
        end;
      end else if CompareText(Rec.Name, RM_LINK_NAME) = 0 then begin
        Found := AddBackslash(Root) + Rec.Name;
        Result := True;
        Exit;
      end;
    until not FindNext(Rec);
  finally
    FindClose(Rec);
  end;
end;

function HasRealityMesh(const Base: string): Boolean;
var
  Found: string;
begin
  Result := False;
  if FindRealityMeshLinkInDir(AddBackslash(Base) + 'RealityMeshInstall', Found) then begin
    Result := True;
    Exit;
  end;
  if FindRealityMeshLinkInDir(AddBackslash(Base) + 'ReailityMeshInstall', Found) then begin
    Result := True;
    Exit;
  end;
  if FindRealityMeshLinkInDir(ExpandConstant('{pf}\Bohemia Interactive Simulations'), Found) then begin
    Result := True;
    Exit;
  end;
  if FindRealityMeshLinkInDir(ExpandConstant('{pf32}\Bohemia Interactive Simulations'), Found) then
    Result := True;
end;

function FindRealityMeshExecutableInDir(const Root: string; var Found: string): Boolean;
var
  Rec: TFindRec;
  Path, LowerName, Ext: string;
begin
  Result := False;
  Found := '';
  if not DirExists(Root) then
    Exit;

  if FindFirst(AddBackslash(Root) + '*', Rec) then
  try
    repeat
      if (Rec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then begin
        if (Rec.Name <> '.') and (Rec.Name <> '..') then begin
          Path := AddBackslash(Root) + Rec.Name;
          if FindRealityMeshExecutableInDir(Path, Found) then begin
            Result := True;
            Exit;
          end;
        end;
      end else begin
        Ext := LowerCase(ExtractFileExt(Rec.Name));
        if Ext = '.exe' then begin
          LowerName := LowerCase(Rec.Name);
          if (Pos('realitymeshtovbs4', LowerName) > 0) or
             (Pos('reality mesh to vbs4', LowerName) > 0) or
             (Pos('realitymesh', LowerName) > 0) then begin
            Found := AddBackslash(Root) + Rec.Name;
            Result := True;
            Exit;
          end;
        end;
      end;
    until not FindNext(Rec);
  finally
    FindClose(Rec);
  end;
end;

procedure CreateShortcutViaPowerShell(const Target, ShortcutPath: string);
var
  RC: Integer;
  Cmd, EscTarget, EscShortcut, EscWorking: string;
begin
  if (Target = '') or (ShortcutPath = '') then
    Exit;

  EscTarget := Target;
  EscShortcut := ShortcutPath;
  EscWorking := ExtractFileDir(Target);

  StringChangeEx(EscTarget, '''', '''''', True);
  StringChangeEx(EscShortcut, '''', '''''', True);
  StringChangeEx(EscWorking, '''', '''''', True);

  Cmd :=
    '-NoProfile -ExecutionPolicy Bypass -Command ' +
    '"$ws = New-Object -ComObject WScript.Shell; ' +
    '$lnk = $ws.CreateShortcut(''' + EscShortcut + '''); ' +
    '$lnk.TargetPath = ''' + EscTarget + '''; ';
  if EscWorking <> '' then
    Cmd := Cmd + '$lnk.WorkingDirectory = ''' + EscWorking + '''; ';
  Cmd := Cmd + '$lnk.Save()"';

  if Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC) then begin
    if RC = 0 then
      Log('Created Reality Mesh shortcut via PowerShell.')
    else
      Log(Format('PowerShell shortcut creation exited with %d', [RC]));
  end else
    Log('Failed to launch PowerShell to create Reality Mesh shortcut.');
end;

procedure EnsureRealityMeshShortcut(const Base: string);
var
  InstallDir, LegacyDir, ShortcutPath, Source, Target: string;
begin
  if Base = '' then
    Exit;

  InstallDir := AddBackslash(Base) + 'RealityMeshInstall';
  LegacyDir := AddBackslash(Base) + 'ReailityMeshInstall';
  ForceDirectories(InstallDir);
  ShortcutPath := InstallDir + '\' + RM_LINK_NAME;

  if FileExists(ShortcutPath) then
    Exit;

  if FindRealityMeshLinkInDir(InstallDir, Source) then begin
    if CompareText(Source, ShortcutPath) <> 0 then
      if not FileCopy(Source, ShortcutPath, False) then
        Log('Failed to copy Reality Mesh shortcut from install directory.');
    Exit;
  end;

  if FindRealityMeshLinkInDir(LegacyDir, Source) then begin
    if FileCopy(Source, ShortcutPath, False) then
      Log('Copied Reality Mesh shortcut from legacy install folder.')
    else
      Log('Failed to copy Reality Mesh shortcut from legacy folder.');
    Exit;
  end;

  if FindRealityMeshLinkInDir(ExpandConstant('{pf}\Bohemia Interactive Simulations'), Source) then begin
    if FileCopy(Source, ShortcutPath, False) then
      Log('Copied Reality Mesh shortcut from Program Files.')
    else
      Log('Failed to copy Reality Mesh shortcut from Program Files.');
    Exit;
  end;

  if FindRealityMeshLinkInDir(ExpandConstant('{pf32}\Bohemia Interactive Simulations'), Source) then begin
    if FileCopy(Source, ShortcutPath, False) then
      Log('Copied Reality Mesh shortcut from Program Files (x86).')
    else
      Log('Failed to copy Reality Mesh shortcut from Program Files (x86).');
    Exit;
  end;

  Target := '';
  if not FindRealityMeshExecutableInDir(InstallDir, Target) then
    if not FindRealityMeshExecutableInDir(LegacyDir, Target) then
      if not FindRealityMeshExecutableInDir(ExpandConstant('{pf}\Bohemia Interactive Simulations'), Target) then
        FindRealityMeshExecutableInDir(ExpandConstant('{pf32}\Bohemia Interactive Simulations'), Target);

  if Target <> '' then
    CreateShortcutViaPowerShell(Target, ShortcutPath)
  else
    Log('Reality Mesh executable not located; shortcut not created.');
end;

procedure RunAllInstallers(const Dir, TargetDir: string);
var
  FindRec: TFindRec;
  FilePath, Params: string;
  RC: Integer;
begin
  if not DirExists(Dir) then begin
    Log('Installer payload missing: ' + Dir);
    Exit;
  end;

  if (TargetDir <> '') and (not DirExists(TargetDir)) then
    ForceDirectories(TargetDir);

  if FindFirst(Dir + '\*.msi', FindRec) then
  try
    repeat
      if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) = 0 then begin
        FilePath := Dir + '\' + FindRec.Name;
        Params := '/i "' + FilePath + '" /qn /norestart ALLUSERS=1';
        if TargetDir <> '' then
          Params := Params + ' TARGETDIR="' + TargetDir + '"';
        if Exec(ExpandConstant('{sys}\msiexec.exe'), Params, '', SW_HIDE, ewWaitUntilTerminated, RC) then
          Log(Format('Ran MSI %s (exit code %d)', [FilePath, RC]))
        else
          Log('Failed to launch msiexec for ' + FilePath);
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
        if TargetDir <> '' then
          Params := Params + ' INSTALLDIR="' + TargetDir + '"';
        if Exec(FilePath, Params, '', SW_HIDE, ewWaitUntilTerminated, RC) then
          Log(Format('Ran EXE %s (exit code %d)', [FilePath, RC]))
        else
          Log('Failed to launch installer ' + FilePath);
      end;
    until not FindNext(FindRec);
  finally
    FindClose(FindRec);
  end;
end;

function ShouldRunPrereqs: Boolean;
var
  Base: string;
begin
  Result := Assigned(ModePage) and ModePage.Values[0];
  if not Result then
    Exit;

  if not HasPhotoMeshWizard() then
    Exit(True);

  Base := BuildShareBase(SelectedRoot());
  Result := not HasRealityMesh(Base);
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
  AppDir, Root, Base, RMTarget: string;
  NeedPhotoMesh, NeedRealityMesh: Boolean;
begin
  if CurStep = ssInstall then begin
    AppDir := ExpandConstant('{app}');
    Root := DetermineShareRoot(AppDir, Assigned(ModePage) and ModePage.Values[0]);
    Base := SeedConfigIni(AppDir, Root);

    if Assigned(ModePage) and ModePage.Values[0] then begin
      NeedPhotoMesh := not HasPhotoMeshWizard();
      if NeedPhotoMesh then begin
        Log('PhotoMesh Wizard not detected; running prerequisite installers.');
        RunAllInstallers(ExpandConstant('{tmp}\PhotomeshInstalls'), '');
      end else
        Log('PhotoMesh Wizard detected; skipping prerequisite installers.');

      NeedRealityMesh := not HasRealityMesh(Base);
      if NeedRealityMesh then begin
        Log('Reality Mesh shortcut not detected; running bundled installers.');
        RMTarget := AddBackslash(Base) + 'RealityMeshInstall';
        RunAllInstallers(ExpandConstant('{tmp}\RealityMeshInstalls'), RMTarget);
      end else
        Log('Reality Mesh installation detected; skipping bundled installers.');
    end;

    EnsureRealityMeshShortcut(Base);
  end;
end;

procedure CurInstallFinished;
var
  RC: Integer;
begin
  if FileExists(ExpandConstant('{app}\update_photomesh_config.exe')) then
    Exec(ExpandConstant('{app}\update_photomesh_config.exe'), '', '{app}', SW_HIDE, ewWaitUntilTerminated, RC);
end;
