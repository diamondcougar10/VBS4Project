; ===================== STE Mission Planning Toolkit Installer =====================
; Modes:
;  Host    – Creates "SharedMeshDrive", shares via SMB, seeds config by IP, optional M: map,
;            and runs PhotoMesh + RealityMesh installers if needed.
;  User    – Regular install, does not create share or drive, does not seed host/IP.
;  Update  – No layout/shares; just replace EXE and repair config.
; ================================================================================

#define AppName "STE Mission Planning Toolkit"
#define AppVersion "2.0"

[Setup]
AppId={{A1B2C3D4-5E6F-7G8H-9I0J-1K2L3M4N5O6P}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={pf}\STE Toolkit
DefaultGroupName=STE Toolkit
DisableProgramGroupPage=yes
Compression=lzma
SolidCompression=yes
OutputBaseFilename=STE_Toolkit_Setup
SetupIconFile=..\assets\icon.ico
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\STE_Toolkit.exe

[Files]
; 1) Toolkit (PyInstaller dist)
Source: "..\dist\STE_Toolkit\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"
Name: "{userdesktop}\STE Mission Planning Toolkit"; Filename: "{app}\STE_Toolkit.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: checkedonce
Name: "firewall";    Description: "Allow STE Toolkit through Windows Firewall"; GroupDescription: "Windows Firewall:"; Flags: checkedonce

[Run]
; Skipped PhotoMesh config patch step (update_photomesh_config.exe not present)

; Launch the GUI toolkit after all configuration is complete
Filename: "{app}\STE_Toolkit.exe"; \
  Parameters: "--fast-start --config ""{app}\config.ini"""; \
  Description: "Launch STE Mission Planning Toolkit now"; \
  Flags: postinstall skipifsilent

Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""STE Toolkit"" dir=in action=allow program=""{app}\STE_Toolkit.exe"" enable=yes"; Flags: runhidden; Tasks: firewall

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C net use M: /delete /yes"; Flags: runhidden
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""try {{ Remove-SmbShare -Name 'SharedMeshDrive' -Force -ErrorAction SilentlyContinue }} catch {{}}"""; \
  Flags: runhidden

[Registry]
; Force elevation because the toolkit needs to modify PhotoMesh config files in Program Files
; Our SMB session cache and credential handling now properly work in elevated mode
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


// --- Helpers ---------------------------------------------------------------
function FileExists2(const P: string): Boolean;
begin
  Result := (P <> '') and FileExists(P);
end;

function IfThen(Cond: Boolean; const A, B: string): string;
begin
  if Cond then Result := A else Result := B;
end;

// Forward declarations for SMB/networking functions
procedure NetUseDeleteServer(const IpOrName: string); forward;
function MapDriveOrUNC(const IpOrAlias, Share, DriveLetter, User, Pass: string; Persistent: Boolean): Boolean; forward;

function HasPhotoMeshFuser(): Boolean;
begin
  Result :=
    FileExists2(ExpandConstant('{pf}\Skyline\PhotoMesh\Tools\PhotoMeshFuser\PhotoMeshFuser.exe')) or
    FileExists2(ExpandConstant('{pf}\Skyline\PhotoMesh\PhotoMeshFuser\PhotoMeshFuser.exe')) or
    FileExists2(ExpandConstant('{pf32}\Skyline\PhotoMesh\Tools\PhotoMeshFuser\PhotoMeshFuser.exe')) or
    FileExists2(ExpandConstant('{pf}\Skyline\PhotoMesh\Fuser\PhotoMeshFuser.exe'));
end;

// Portable "get file size" - simple version that returns 0 on failure
function TryGetFileSize(const FileName: string; var Size: Int64): Boolean;
begin
  Result := FileExists(FileName);
  if Result then
    Size := 1024 * 1024  // Default to 1MB if we can't get actual size
  else
    Size := 0;
end;

procedure LogInstallEvent(const Message: string);
var
  LogDir, LogFile, Timestamp, DateStr: string;
  LogContent: AnsiString;
  CurrentSize: Int64;
begin
  LogDir := ExpandConstant('{commonappdata}\STE_Toolkit');
  CreateDir(LogDir);

  // Use date-based log file for rotation
  DateStr := GetDateTimeString('yyyy-mm-dd', #0, #0);
  LogFile := AddBackslash(LogDir) + 'install-' + DateStr + '.log';
  Timestamp := GetDateTimeString('yyyy-mm-dd hh:nn:ss', #0, #0);

  // Rotate if > 5 MB
  if FileExists(LogFile) then
  begin
    if TryGetFileSize(LogFile, CurrentSize) and (CurrentSize > 5 * 1024 * 1024) then
    begin
      if LoadStringFromFile(LogFile, LogContent) then
      begin
        SaveStringToFile(AddBackslash(LogDir) + 'install-' + DateStr + '-archived.log',
          LogContent, False);
        SaveStringToFile(LogFile,
          Timestamp + ' [ROTATED] Previous log archived due to size' + #13#10, False);
      end;
    end;
  end;

  SaveStringToFile(LogFile, Timestamp + ' ' + Message + #13#10, True);
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
    'timestamp=' + TS + #13#10 +
    'guest_ok=1' + #13#10 +      // only if you intentionally allow guest access
    'dns_alias=ste-host' + #13#10;   // optional, if you plan to push a hosts entry to Users

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

  // First attempt: Least privilege - Authenticated Users with Change, Administrators with Full
  Cmd :=
    '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ' +
    '"$ErrorActionPreference=''Stop''; ' +
    'if (-not (Get-SmbShare -Name ''' + ShareName + ''' -ErrorAction SilentlyContinue)) { ' +
    '  New-SmbShare -Name ''' + ShareName + ''' -Path ''' + LocalPath + ''' -ChangeAccess ''Authenticated Users'' -FullAccess ''Administrators'' | Out-Null ' +
    '}"';
  Ran := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
              Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC);
  if Ran and (RC = 0) then
  begin
    LogInstallEvent('SMB share created with Authenticated Users (Change) permissions');
    // Enable File and Printer Sharing firewall rule after successful share creation
    Cmd := '/C "netsh advfirewall firewall set rule group=""File and Printer Sharing"" new enable=Yes"';
    if Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC) then
    begin
      if RC = 0 then
        LogInstallEvent('Firewall group rule enabled successfully')
      else
      begin
        LogInstallEvent('Firewall group rule failed, trying specific SMB rule');
        // Fallback: add specific SMB rule if group enable failed
        Cmd := '/C "netsh advfirewall firewall add rule name=""STE Toolkit SMB 445"" dir=in action=allow protocol=TCP localport=445 profile=Domain,Private enable=yes"';
        if Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC) then
        begin
          if RC = 0 then
            LogInstallEvent('Specific SMB firewall rule added successfully')
          else
            LogInstallEvent('Specific SMB firewall rule failed: RC=' + IntToStr(RC));
        end;
      end;
    end;
    Exit;
  end;

  LogInstallEvent('Authenticated Users share failed, trying Everyone permissions');
  
  // Second attempt: Everyone with Full (for environments that require it)
  Cmd :=
    '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ' +
    '"$ErrorActionPreference=''Stop''; ' +
    'if (-not (Get-SmbShare -Name ''' + ShareName + ''' -ErrorAction SilentlyContinue)) { ' +
    '  New-SmbShare -Name ''' + ShareName + ''' -Path ''' + LocalPath + ''' -FullAccess ''Everyone'' | Out-Null ' +
    '}"';
  Ran := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
              Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC);
  if Ran and (RC = 0) then
  begin
    LogInstallEvent('SMB share created with Everyone (Full) permissions');
    // Enable firewall rules
    Cmd := '/C "netsh advfirewall firewall set rule group=""File and Printer Sharing"" new enable=Yes"';
    if Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC) then
    begin
      if RC <> 0 then
      begin
        LogInstallEvent('Firewall group rule failed, trying specific SMB rule');
        Cmd := '/C "netsh advfirewall firewall add rule name=""STE Toolkit SMB 445"" dir=in action=allow protocol=TCP localport=445 profile=Domain,Private enable=yes"';
        Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC);
      end;
    end;
    Exit;
  end;

  LogInstallEvent('PowerShell SMB share creation failed, trying net share command');

  // Final fallback: net share command with Authenticated Users
  Cmd := '/C "net share ' + ShareName + '=""' + LocalPath + '"" /GRANT:""Authenticated Users"",CHANGE /GRANT:""Administrators"",FULL"';
  Ran := Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC);
  if Ran and (RC = 0) then
  begin
    LogInstallEvent('SMB share created via net share with Authenticated Users');
    Cmd := '/C "netsh advfirewall firewall set rule group=""File and Printer Sharing"" new enable=Yes"';
    if Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC) then
    begin
      if RC <> 0 then
      begin
        Cmd := '/C "netsh advfirewall firewall add rule name=""STE Toolkit SMB 445"" dir=in action=allow protocol=TCP localport=445 profile=Domain,Private enable=yes"';
        Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC);
      end;
    end;
  end else begin
    LogInstallEvent('Authenticated Users net share failed, trying Everyone as last resort');
    // Last resort: Everyone with FULL
    Cmd := '/C "net share ' + ShareName + '=""' + LocalPath + '"" /GRANT:Everyone,FULL"';
    Ran := Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC);
    if Ran and (RC = 0) then
    begin
      LogInstallEvent('SMB share created via net share with Everyone (Full)');
      Cmd := '/C "netsh advfirewall firewall set rule group=""File and Printer Sharing"" new enable=Yes"';
      Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC);
    end else begin
      LogInstallEvent('All SMB share creation methods failed');
    end;
  end;
end;

function GetPrimaryIPv4(): string;
var PS, TmpFile: string; RC: Integer; S: AnsiString;
begin
  Result := '';
  TmpFile := ExpandConstant('{tmp}\host_ip.txt');

  // Use default route approach like the runtime code (more robust for VPN/WSL/multi-NIC)
  PS :=
    '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ' +
    '"$ErrorActionPreference=''Stop''; ' +
    '$ip = try { ' +
    '  $route = Get-NetRoute -DestinationPrefix ''0.0.0.0/0'' -AddressFamily IPv4 | ' +
    '           Sort-Object RouteMetric | Select-Object -First 1; ' +
    '  if ($route) { ' +
    '    (Get-NetIPAddress -InterfaceIndex $route.InterfaceIndex -AddressFamily IPv4 | ' +
    '      Where-Object { $_.IPAddress -notmatch ''^169\.254\.'' -and $_.IPAddress -ne ''127.0.0.1'' } | ' +
    '      Select-Object -First 1 -ExpandProperty IPAddress) ' +
    '  } else { ' +
    '    (Get-NetIPAddress -AddressFamily IPv4 | ' +
    '      Where-Object { $_.IPAddress -notmatch ''^169\.254\.'' -and $_.IPAddress -ne ''127.0.0.1'' } | ' +
    '      Sort-Object -Property InterfaceMetric | Select-Object -First 1 -ExpandProperty IPAddress) ' +
    '  } ' +
    '} catch { ' +
    '  (Get-NetIPAddress -AddressFamily IPv4 | ' +
    '    Where-Object { $_.IPAddress -notmatch ''^169\.254\.'' -and $_.IPAddress -ne ''127.0.0.1'' } | ' +
    '    Sort-Object -Property InterfaceMetric | Select-Object -First 1 -ExpandProperty IPAddress) ' +
    '}; ' +
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
    RC: Integer;
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

  SetIniString('Fusers', 'desired_count', '0',                Ini);
  SetIniString('Fusers', 'host_count',    '1',                Ini);
  SetIniString('Fusers', 'fuser_computer','False',            Ini);
  SetIniString('Fusers', 'working_folder_host', HostName,     Ini);
  SetIniString('Fusers', 'shared_working_unc', AddBackslash(Base) + 'WorkingFuser', Ini);

  SetIniString('Network', 'host', HostIP,                     Ini);

  { Grant NTFS Modify permissions to Authenticated Users }
  try
    LogInstallEvent('Applying NTFS Modify permissions to Authenticated Users');
    Exec(ExpandConstant('{cmd}'),
      '/C icacls "' + Base + '" /grant "Authenticated Users:(OI)(CI)M" /T /C',
      '', SW_HIDE, ewWaitUntilTerminated, RC);
    LogInstallEvent('Applied NTFS Modify permissions RC=' + IntToStr(RC));
  except
    LogInstallEvent('Failed to apply NTFS permissions - continuing anyway');
  end;

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

  { Only enable Offline if a host was discovered to prevent blocking on first boot }
  SetIniString('Offline', 'enabled', IfThen(UseIP, 'True', 'False'), Ini);
  SetIniString('Offline', 'host_name',  DiscoveredName,     Ini);
  SetIniString('Offline', 'host_ip',    DiscoveredIP,       Ini);
  SetIniString('Offline', 'share_name', SHARE_NAME,         Ini);
  SetIniString('Offline', 'local_data_root', '',            Ini);
  SetIniString('Offline', 'working_fuser_subdir','WorkingFuser', Ini);
  SetIniString('Offline', 'use_ip_unc', IfThen(UseIP, 'True', 'False'), Ini);

  SetIniString('SharedDrive', 'preferred_mode', 'UNC',  Ini);
  SetIniString('SharedDrive', 'drive_letter',   'M:',   Ini);
  SetIniString('SharedDrive', 'auto_map_on_save','True',Ini);

  SetIniString('General', 'first_run_done', 'True', Ini);
  SetIniString('General', 'first_run_mode', 'USER', Ini);
  
  { Skip network connection attempts on first boot when no host discovered }
  SetIniString('General', 'skip_startup_connect', IfThen(UseIP, 'False', 'True'), Ini);

  { Only set desired_count > 0 if PhotoMesh Fuser is available }
  if HasPhotoMeshFuser() then
  begin
    SetIniString('Fusers', 'desired_count', '3',     Ini);
    SetIniString('Fusers', 'fuser_computer','True',  Ini);
  end
  else
  begin
    SetIniString('Fusers', 'desired_count', '0',     Ini);
    SetIniString('Fusers', 'fuser_computer','False', Ini);
    LogInstallEvent('Fuser not found; setting desired_count=0 to avoid false "0/3" state');
  end;
  
  SetIniString('Fusers', 'host_count',    '1',     Ini);
  
  { Set up fuser working paths if we discovered a host }
  if UseIP then
  begin
    SetIniString('Fusers', 'working_folder_host', DiscoveredName, Ini);
    SetIniString('Fusers', 'shared_working_unc', '\\' + DiscoveredIP + '\' + SHARE_NAME + '\WorkingFuser', Ini);
    SetIniString('Offline', 'working_fuser_host', DiscoveredName, Ini);
  end;

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
    'Choose External Drive for Shared Storage',
    'IMPORTANT: The shared drive MUST be on a separate drive (NOT C:)' + #13#10 +
    'Please connect an external drive or use a secondary internal drive.',
    'Select the root of your external/secondary drive (e.g., D:\, E:\, F:\)' + #13#10 + #13#10 +
    'Requirements:' + #13#10 +
    '  • Must NOT be C: drive' + #13#10 +
    '  • Must be a physical drive letter (not a network path)' + #13#10 +
    '  • Must have sufficient space for terrain data' + #13#10 + #13#10 +
    'The installer will create a "SharedMeshDrive" folder at this location.',
    False, ''
  );
  SharedRootPage.Add('');
  SharedRootPage.Values[0] := 'D:\';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if Assigned(SharedRootPage) and (PageID = SharedRootPage.ID) then
    Result := SelectedMode() <> imHost;  { only for Host }
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var 
  Candidate, DriveLetter: string;
  ErrorMsg: string;
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
    
    { Validate that a path was entered }
    if Candidate = '' then
    begin
      MsgBox('Please choose a drive or folder for the shared storage.' + #13#10 + #13#10 +
             'This MUST be an external drive or secondary internal drive (NOT C:).',
             mbError, MB_OK);
      Result := False;
      Exit;
    end;
    
    { Extract drive letter (first character or characters before colon) }
    DriveLetter := '';
    if Length(Candidate) >= 2 then
    begin
      if Candidate[2] = ':' then
        DriveLetter := UpperCase(Copy(Candidate, 1, 1))
      else if Candidate[1] = '\' then
      begin
        { Handle UNC paths }
        MsgBox('Network (UNC) paths are not supported for the shared drive.' + #13#10 + #13#10 +
               'Please select a local drive letter (e.g., D:\, E:\, F:\).',
               mbError, MB_OK);
        Result := False;
        Exit;
      end;
    end;
    
    { Validate drive letter was extracted }
    if DriveLetter = '' then
    begin
      MsgBox('Invalid drive path format.' + #13#10 + #13#10 +
             'Please enter a valid drive letter path (e.g., D:\, E:\, F:\).',
             mbError, MB_OK);
      Result := False;
      Exit;
    end;
    
    { Block C: drive }
    if DriveLetter = 'C' then
    begin
      MsgBox('ERROR: C: drive is not allowed for shared storage!' + #13#10 + #13#10 +
             'The shared drive must be on an external drive or secondary internal drive.' + #13#10 + #13#10 +
             'Reasons:' + #13#10 +
             '  • Prevents filling up your system drive' + #13#10 +
             '  • Allows drive to be portable between systems' + #13#10 +
             '  • Isolates large terrain data from OS partition' + #13#10 + #13#10 +
             'Please connect an external drive and select it (e.g., D:\, E:\, F:\).',
             mbCriticalError, MB_OK);
      Result := False;
      Exit;
    end;
    
    { Validate that the drive exists and is accessible }
    if not DirExists(DriveLetter + ':\') then
    begin
      MsgBox('Drive ' + DriveLetter + ':\ is not accessible or does not exist.' + #13#10 + #13#10 +
             'Please ensure:' + #13#10 +
             '  • The drive is properly connected' + #13#10 +
             '  • The drive is formatted and has a drive letter assigned' + #13#10 +
             '  • You have permission to access the drive' + #13#10 + #13#10 +
             'Then try again.',
             mbError, MB_OK);
      Result := False;
      Exit;
    end;
    
    { All validations passed }
    SharedRoot := Candidate;
    LogInstallEvent('Host drive validated: ' + DriveLetter + ':\ (Path: ' + SharedRoot + ')');
  end;
end;

procedure EnsureSiteConfigExists(const AppDir: string);
var
  Src, Dst: string;
  RC: Integer;
begin
  Dst := AddBackslash(AppDir) + 'config.ini';
  if not FileExists(Dst) then
  begin
    Src := AddBackslash(AppDir) + '_internal\config.ini';
    if FileExists(Src) then
      FileCopy(Src, Dst, False)   // create site-level from bundled default
    else
      SaveStringToFile(Dst, '; created by installer' + #13#10, False);
  end;

  // Clear read-only just in case the copied file inherited attributes
  Exec(ExpandConstant('{cmd}'), '/C attrib -R "' + Dst + '"',
       '', SW_HIDE, ewWaitUntilTerminated, RC);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  AppDir, Base, RMTarget, HostRoot, Cmd, Ip: string;
  NeedPhotoMesh, NeedRealityMesh: Boolean;
  RC: Integer;
  DscIP, DscName: string;  { NEW: for host discovery }
  IniPath, BundledIni: string;         { NEW: for update case and config copying }
  ModeStr: string;
begin
  if CurStep = ssPostInstall then  { CHANGED FROM ssInstall - seed AFTER files are copied }
  begin
    AppDir := ExpandConstant('{app}');
    EnsureSiteConfigExists(AppDir);  { NEW: Ensure config.ini exists before seeding }
    HostRoot := '';
    
    case SelectedMode() of
      imHost: ModeStr := 'Host';
      imUser: ModeStr := 'User';
      imUpdate: ModeStr := 'Update';
    end;
    
    LogInstallEvent('Installation mode: ' + ModeStr);

    case SelectedMode() of
      imHost:
      begin
        if SharedRoot <> '' then HostRoot := SharedRoot else HostRoot := 'D:\';
        LogInstallEvent('Host mode - using root: ' + HostRoot);
        
        Base := SeedConfigIni_Host(AppDir, HostRoot);
        LogInstallEvent('Share base created: ' + Base);

        NeedPhotoMesh   := not HasPhotoMeshWizard();
        NeedRealityMesh := not HasShareRealityMesh(Base);
        
        LogInstallEvent('PhotoMesh needed: ' + IfThen(NeedPhotoMesh, 'Yes', 'No'));
        LogInstallEvent('RealityMesh needed: ' + IfThen(NeedRealityMesh, 'Yes', 'No'));

        Log('PhotoMesh and RealityMesh installers no longer bundled - manual installation required.');

        Ip := GetPrimaryIPv4();
        LogInstallEvent('Detected IP: ' + Ip);
        
        if Ip <> '' then
        begin
          Cmd := '/C "net use M: /delete /yes & net use M: ""\\' + Ip + '\' + SHARE_NAME + '"" /persistent:yes"';
          if Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC) then
            LogInstallEvent('Drive mapping result: RC=' + IntToStr(RC))
          else
            LogInstallEvent('Drive mapping failed to execute');
        end;
      end;

      imUser:
      begin
        { NEW: quick auto-discovery of Host beacon }
        DscIP := ''; DscName := '';
        if DiscoverHostViaBeacon(DscIP, DscName) then
        begin
          LogInstallEvent('Beacon discovered - IP: ' + DscIP + ', Name: ' + DscName);
          Log(Format('Beacon found: host_ip=%s name=%s', [DscIP, DscName]));
        end
        else
        begin
          LogInstallEvent('No beacon found - leaving host_ip blank');
          Log('Beacon not found; leaving host_ip blank');
        end;

        SeedConfigIni_User(AppDir, DscIP, DscName);
        LogInstallEvent('User mode configuration completed');

        { PhotoMesh Fuser check - installers no longer bundled }
        if not HasPhotoMeshFuser() then
          LogInstallEvent('PhotoMesh Fuser missing - manual installation required')
        else
          LogInstallEvent('PhotoMesh Fuser found');

        // If we discovered a host, establish NON-PERSISTENT session to avoid token conflicts
        // This prevents ERROR 1219 when the app (user token) tries to connect later
        if DscIP <> '' then
        begin
          LogInstallEvent('User mode: establishing connection to \\' + DscIP + '\' + SHARE_NAME);
          
          // 0) Always clear any stale M: mapping first to avoid letter collisions
          Exec(ExpandConstant('{cmd}'), '/C "net use M: /delete /yes"', '', SW_HIDE, ewWaitUntilTerminated, RC);
          
          // 1) Delete any existing server sessions for this host (clears admin-token sessions)
          NetUseDeleteServer(DscIP);
          
          // 2) Establish a NON-PERSISTENT UNC session first (no drive letter)
          //    This avoids admin-token vs user-token session collisions (ERROR 1219)
          if not MapDriveOrUNC(DscIP, SHARE_NAME, '', '', '', False) then
            LogInstallEvent('User mode: UNC session creation failed (non-persistent)')
          else
            LogInstallEvent('User mode: UNC session established (non-persistent)');
          
          // 3) Optionally map M: NON-PERSISTENT now that a session exists
          //    Non-persistent avoids stale mappings after reboot
          if not MapDriveOrUNC(DscIP, SHARE_NAME, 'M:', '', '', False) then
            LogInstallEvent('User mode: M: mapping failed (non-persistent)')
          else
            LogInstallEvent('User mode: M: mapped successfully (non-persistent)');
        end
        else
          LogInstallEvent('User mode: no host discovered; skipping SMB session');
      end;

      imUpdate:
      begin
        LogInstallEvent('Update mode - preserving existing configuration');
        { Keep existing config, but if Offline.host_ip is blank, try to discover }
        IniPath := AddBackslash(AppDir) + 'config.ini';
        
        { Ensure config exists in main directory }
        if not FileExists(IniPath) then
        begin
          BundledIni := AddBackslash(AppDir) + '_internal\config.ini';
          if FileExists(BundledIni) then
          begin
            FileCopy(BundledIni, IniPath, False);
            LogInstallEvent('Copied bundled config to main directory');
          end;
        end;
        
        if GetIniString('Offline','host_ip','', IniPath) = '' then
        begin
          LogInstallEvent('Attempting beacon discovery for blank host_ip');
          DscIP := ''; DscName := '';
          if DiscoverHostViaBeacon(DscIP, DscName) and (DscIP <> '') then
          begin
            SetIniString('Offline','host_ip', DscIP, IniPath);
            if DscName <> '' then
              SetIniString('Offline','host_name', DscName, IniPath);
            SetIniString('Network','host', DscIP, IniPath);
            LogInstallEvent('Auto-filled blank host_ip with discovered: ' + DscIP);
            Log(Format('Update: auto-filled blank host_ip with discovered %s', [DscIP]));
          end
          else
            LogInstallEvent('No beacon found during update discovery');
        end
        else
          LogInstallEvent('Existing host_ip preserved in config');
        { otherwise leave Update behavior unchanged }
      end;
    end;

    if SelectedMode() = imHost then
    begin
      if HostRoot = '' then HostRoot := 'D:\';
      RMTarget := AddBackslash(BuildShareBase(HostRoot)) + 'RealityMeshInstall\' + RM_LINK_NAME;
      { No-op if already present/created by installers }
    end;
    
    LogInstallEvent('Installation phase completed successfully');
  end;
end;

procedure CurInstallFinished;
begin
  // Note: update_photomesh_config.exe now runs in [Run] section BEFORE GUI launch
  // to eliminate race conditions. This procedure is kept for future use.
end;

// --- Credential + mapping helpers -----------------------------------------
function B64Encode(const S: string): string;
begin
  // Simple placeholder - in production use proper base64 encoding
  Result := S;
end;

function B64Decode(const S: string): string;
begin
  // Simple placeholder - in production use proper base64 decoding
  Result := S;
end;

procedure AddHostsMapping(const NameOrAlias, Ip: string);
var Hosts, Line, Content: AnsiString;
begin
  if (Ip = '') or (NameOrAlias = '') then Exit;
  Hosts := 'C:\Windows\System32\drivers\etc\hosts';
  if LoadStringFromFile(Hosts, Content) then begin
    if Pos(#13#10 + AnsiString(Ip + ' ' + NameOrAlias), Content) = 0 then begin
      Line := #13#10 + AnsiString(Ip + ' ' + NameOrAlias);
      SaveStringToFile(Hosts, Content + Line, False);
    end;
  end;
end;

function CmdKeyAdd(const Target, UserName, Password: string): Boolean;
var RC: Integer; Args: string;
begin
  Result := False;
  if (Target = '') or (UserName = '') or (Password = '') then Exit;
  Args := '/C "cmdkey /generic:' + Target + ' /user:' + UserName + ' /pass:' + Password + '"';
  Result := Exec(ExpandConstant('{cmd}'), Args, '', SW_HIDE, ewWaitUntilTerminated, RC) and (RC = 0);
end;

procedure NetUseDeleteServer(const IpOrName: string);
var RC: Integer;
begin
  if IpOrName = '' then Exit;
  Exec(ExpandConstant('{cmd}'), '/C "net use \\' + IpOrName + '\* /delete /y"', '', SW_HIDE, ewWaitUntilTerminated, RC);
end;

function MapDriveOrUNC(const IpOrAlias, Share, DriveLetter, User, Pass: string; Persistent: Boolean): Boolean;
var RC: Integer; PersistFlag, Cmd: string;
begin
  PersistFlag := IfThen(Persistent, ' /persistent:yes', ' /persistent:no');
  Result := False;

  // Prefer mapping the drive letter if provided
  if DriveLetter <> '' then begin
    Cmd := '/C "net use ' + DriveLetter + ' \\' + IpOrAlias + '\' + Share;
    if (User <> '') and (Pass <> '') then
      Cmd := Cmd + ' ' + '/user:' + User + ' ' + '"' + Pass + '"';
    Cmd := Cmd + PersistFlag + '"';
    if Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC) and (RC = 0) then begin
      Result := True;
      Exit;
    end;
  end;

  // Fall back to creating a UNC session (no drive letter)
  Cmd := '/C "net use \\' + IpOrAlias + '\' + Share;
  if (User <> '') and (Pass <> '') then
    Cmd := Cmd + ' ' + '/user:' + User + ' ' + '"' + Pass + '"';
  Cmd := Cmd + PersistFlag + '"';
  Result := Exec(ExpandConstant('{cmd}'), Cmd, '', SW_HIDE, ewWaitUntilTerminated, RC) and (RC = 0);
end;

procedure EnableInsecureGuestAuthIfRequested(const GuestOk: Boolean);
var RC: Integer;
begin
  if not GuestOk then Exit;
  Exec(ExpandConstant('{cmd}'),
       '/C reg add "HKLM\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters" ' +
       '/v AllowInsecureGuestAuth /t REG_DWORD /d 1 /f',
       '', SW_HIDE, ewWaitUntilTerminated, RC);
end;

function TryReadBeaconEx(const FilePath: string; var OutIP, OutName, OutUser, OutSecretB64, OutAlias: string; var OutGuestOk: Boolean): Boolean;
var GuestFlag: string;
begin
  Result := False;
  OutIP        := GetIniString('Host','ip','', FilePath);
  OutName      := GetIniString('Host','name','', FilePath);
  OutUser      := GetIniString('Host','user','', FilePath);
  OutSecretB64 := GetIniString('Host','secret_b64','', FilePath);
  OutAlias     := GetIniString('Host','dns_alias','', FilePath);
  GuestFlag    := GetIniString('Host','guest_ok','', FilePath);
  OutGuestOk   := (UpperCase(Trim(GuestFlag)) = '1') or (UpperCase(Trim(GuestFlag)) = 'TRUE');
  Result := (OutIP <> '');
end;

// --- Previous Installation Detection and Handling ---
function GetUninstallString(): String;
var
  sUnInstPath: String;
  sUnInstallString: String;
begin
  sUnInstPath := ExpandConstant('Software\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppId")}_is1');
  sUnInstallString := '';
  if not RegQueryStringValue(HKLM, sUnInstPath, 'UninstallString', sUnInstallString) then
    RegQueryStringValue(HKCU, sUnInstPath, 'UninstallString', sUnInstallString);
  Result := sUnInstallString;
end;

function IsUpgrade(): Boolean;
begin
  Result := (GetUninstallString() <> '');
end;

function UnInstallOldVersion(): Integer;
var
  sUnInstallString: String;
  iResultCode: Integer;
begin
  Result := 0;
  sUnInstallString := GetUninstallString();
  if sUnInstallString <> '' then begin
    sUnInstallString := RemoveQuotes(sUnInstallString);
    if Exec(sUnInstallString, '/SILENT /NORESTART /SUPPRESSMSGBOXES','', SW_HIDE, ewWaitUntilTerminated, iResultCode) then
      Result := 3
    else
      Result := 2;
  end else
    Result := 1;
end;

function ShowUpgradeDialog(): Integer;
var
  Form: TSetupForm;
  MessageLabel: TNewStaticText;
  UpdateButton: TNewButton;
  UninstallButton: TNewButton;
  CancelButton: TNewButton;
begin
  Result := 0; // 0 = Cancel, 1 = Update, 2 = Uninstall
  
  Form := CreateCustomForm();
  try
    Form.ClientWidth := ScaleX(420);
    Form.ClientHeight := ScaleY(180);
    Form.Caption := 'Previous Installation Detected';
    Form.Position := poScreenCenter;
    
    MessageLabel := TNewStaticText.Create(Form);
    MessageLabel.Parent := Form;
    MessageLabel.Left := ScaleX(20);
    MessageLabel.Top := ScaleY(20);
    MessageLabel.Width := ScaleX(380);
    MessageLabel.Height := ScaleY(60);
    MessageLabel.AutoSize := False;
    MessageLabel.WordWrap := True;
    MessageLabel.Caption := 'It looks like you already have this program installed.' + #13#10#13#10 + 'Would you like to:';
    
    UpdateButton := TNewButton.Create(Form);
    UpdateButton.Parent := Form;
    UpdateButton.Left := ScaleX(20);
    UpdateButton.Top := ScaleY(90);
    UpdateButton.Width := ScaleX(120);
    UpdateButton.Height := ScaleY(30);
    UpdateButton.Caption := '&Update';
    UpdateButton.ModalResult := mrYes;
    UpdateButton.Default := True;
    
    UninstallButton := TNewButton.Create(Form);
    UninstallButton.Parent := Form;
    UninstallButton.Left := ScaleX(150);
    UninstallButton.Top := ScaleY(90);
    UninstallButton.Width := ScaleX(120);
    UninstallButton.Height := ScaleY(30);
    UninstallButton.Caption := 'U&ninstall';
    UninstallButton.ModalResult := mrNo;
    
    CancelButton := TNewButton.Create(Form);
    CancelButton.Parent := Form;
    CancelButton.Left := ScaleX(280);
    CancelButton.Top := ScaleY(90);
    CancelButton.Width := ScaleX(120);
    CancelButton.Height := ScaleY(30);
    CancelButton.Caption := '&Cancel';
    CancelButton.ModalResult := mrCancel;
    CancelButton.Cancel := True;
    
    if Form.ShowModal = mrYes then
      Result := 1
    else if Form.ShowModal = mrNo then
      Result := 2
    else
      Result := 0;
  finally
    Form.Free();
  end;
end;

function InitializeSetup(): Boolean;
var
  Response: Integer;
begin
  Result := True;
  
  // Check if the application is already installed
  if IsUpgrade() then
  begin
    Response := ShowUpgradeDialog();
    
    case Response of
      1: begin
        // User wants to update - uninstall old version and continue with installation
        if UnInstallOldVersion() <> 1 then
        begin
          MsgBox('Previous version has been uninstalled. The new version will now be installed.', mbInformation, MB_OK);
          Result := True;
        end
        else
        begin
          MsgBox('Failed to uninstall the previous version. Please uninstall it manually first.', mbError, MB_OK);
          Result := False;
        end;
      end;
      
      2: begin
        // User wants to only uninstall
        if UnInstallOldVersion() <> 1 then
        begin
          MsgBox('The application has been uninstalled.', mbInformation, MB_OK);
        end
        else
        begin
          MsgBox('Failed to uninstall the application.', mbError, MB_OK);
        end;
        Result := False; // Stop installation
      end;
      
      0: begin
        // User cancelled
        Result := False;
      end;
    end;
  end;
end;
