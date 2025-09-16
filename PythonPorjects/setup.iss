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
    DestDir: "{tmp}\PhotomeshInstalls"; Flags: recursesubdirs createallsubdirs
; --- Reality Mesh installers ---
Source: "C:\Users\tifte\Documents\GitHub\VBS4Project\PythonPorjects\installs\RealityMesh\*"; \
    DestDir: "{tmp}\RealityMeshInstalls"; Flags: recursesubdirs createallsubdirs

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
  SharedRootPage: TInputDirWizardPage;
  SharedRoot: string;

function IsDriveLetterOnly(Path: string): Boolean;
begin
  // True when like "D:\" or "M:\" etc.
  Result := (Length(Path) >= 3) and (Path[2] = ':') and (Path[3] = '\') and (Pos('\', Copy(Path, 4, MaxInt)) = 0);
end;

function DriveLetterOf(Path: string): string;
begin
  if (Length(Path) >= 2) and (Path[2] = ':') then Result := Copy(Path, 1, 2)
  else Result := '';
end;

procedure ForceLayoutUnder(Root: string);
var
  Base, P: string;
begin
  // Build: <Root>\SharedMeshDrive\...
  Base := AddBackslash(Root) + 'SharedMeshDrive';
  ForceDirectories(Base);

  P := Base + '\WorkingFuser';        ForceDirectories(P);
  P := Base + '\Projects';            ForceDirectories(P);
  P := Base + '\RealityMeshInstall';  ForceDirectories(P);
  P := Base + '\UnprocessedPhotos';   ForceDirectories(P);
  P := Base + '\RealityMeshOutput';   ForceDirectories(P);
end;

procedure SeedConfigIni(AppDir, Root: string);
var
  Ini: string;
  Base, IsUNC, Letter, Mode: string;
begin
  Ini  := AppDir + '\config.ini';
  Base := AddBackslash(Root) + 'SharedMeshDrive';

  // Decide preferred mode (DRIVE vs UNC) for your app
  if (Copy(Root, 1, 2) = '\\') then begin
    Mode := 'UNC';
    Letter := '';
  end
  else begin
    Mode := 'DRIVE';
    Letter := DriveLetterOf(Root);
    if Letter = '' then Letter := 'D:'; // fallback
  end;

  // --- [Offline] section expected by your toolkit ---
  SetIniString('Offline', 'enabled', 'True', Ini);
  // Keep host name empty — user sets once in Settings; app syncs it everywhere. :contentReference[oaicite:3]{index=3}
  // SetIniString('Offline', 'host_name', ExpandConstant('{computername}'), Ini);
  SetIniString('Offline', 'host_ip', '', Ini);
  SetIniString('Offline', 'share_name', 'SharedMeshDrive', Ini);
  SetIniString('Offline', 'local_data_root', Base, Ini);
  SetIniString('Offline', 'working_fuser_subdir', 'WorkingFuser', Ini);
  SetIniString('Offline', 'use_ip_unc', 'False', Ini);

  // --- [SharedDrive] section used by your UI and mapping helpers ---
  SetIniString('SharedDrive', 'preferred_mode', Mode, Ini);
  if Letter <> '' then SetIniString('SharedDrive', 'drive_letter', Letter, Ini);
  SetIniString('SharedDrive', 'auto_map_on_save', 'True', Ini);

  // --- [General] Reality Mesh install root so the app can find the .lnk locally ---
  // Your app now validates by searching for "Reality Mesh to VBS4.lnk" under this folder. :contentReference[oaicite:4]{index=4}
  SetIniString('General', 'reality_mesh_local_root', Base + '\RealityMeshInstall', Ini);

  // Optional: template points to UNC with tokenized host; your app defaults to this anyway. :contentReference[oaicite:5]{index=5}
  // SetIniString('General', 'reality_mesh_to_vbs4', '\\{host}\SharedMeshDrive\RealityMeshInstall\Reality Mesh to VBS4.lnk', Ini);
end;

procedure RunAllInstallers(Dir: string);
var
  FindRec: TFindRec;
  FilePath, Params: string;
  ResultCode: Integer;
begin
  // Install all MSIs first (quiet)
  if FindFirst(Dir + '\*.msi', FindRec) then
  try
    repeat
      if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) = 0 then begin
        FilePath := Dir + '\' + FindRec.Name;
        Params := '/i "' + FilePath + '" /qn /norestart ALLUSERS=1';
        Log('Installing MSI: ' + FilePath);
        if not Exec(ExpandConstant('{sys}\msiexec.exe'), Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
          Log(Format('Failed to start MSI %s (code %d)', [FilePath, ResultCode]));
      end;
    until not FindNext(FindRec);
  finally
    FindClose(FindRec);
  end;

  // Then EXEs (quiet defaults). If a vendor needs special switches, add here.
  if FindFirst(Dir + '\*.exe', FindRec) then
  try
    repeat
      if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) = 0 then begin
        FilePath := Dir + '\' + FindRec.Name;

        // Sensible default: /quiet /norestart (fallback to /verysilent if needed)
        Params := '/quiet /norestart';
        Log('Installing EXE: ' + FilePath);
        if not Exec(FilePath, Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
          Log(Format('Failed to start EXE %s (code %d)', [FilePath, ResultCode]));
      end;
    until not FindNext(FindRec);
  finally
    FindClose(FindRec);
  end;
end;

procedure InitializeWizard;
begin
  // Ask for root once (local drive or mapped share). Keep it simple for soldiers.
  SharedRootPage := CreateInputDirPage(
    wpSelectDir,
    'Choose Shared Drive Root',
    'Where should the shared structure be created?',
    'Pick a local drive or mapped letter (e.g., D:\ or M:\). ' +
    'The installer will create "SharedMeshDrive" and the required subfolders.',
    False, ''
  );
  SharedRootPage.Add('Root drive or folder:');
  // Default to D:\
  SharedRootPage.Values[0] := 'D:\';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  if CurPageID = SharedRootPage.ID then begin
    SharedRoot := Trim(SharedRootPage.Values[0]);
    if SharedRoot = '' then begin
      MsgBox('Please choose a drive or folder.', mbError, MB_OK);
      Result := False;
      exit;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  PDir: string;
begin
  if CurStep = ssInstall then begin
    // 1) Build the folder tree
    ForceLayoutUnder(SharedRoot);

    // 2) Seed your app’s config so the first run is “zero-setup”
    SeedConfigIni(ExpandConstant('{app}'), SharedRoot);

    // 3) Run third-party installers we embedded
    // --- Photomesh (Wizard, TerraExplorer, etc.) ---
    RunAllInstallers(ExpandConstant('{tmp}\PhotomeshInstalls'));
    // --- RealityMesh (Core, TerraTools, etc.) ---
    RunAllInstallers(ExpandConstant('{tmp}\RealityMeshInstalls'));
  end;
end;
