#define MyAppName "GTA5 RAGECOOP Launcher"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "Local Coop Tools"
#define MyAppExeName "GTA5CoopLauncher.exe"

[Setup]
AppId={{B8C57C74-67D4-4D8A-BF09-4B41C7A9C0A5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\GTA5 RAGECOOP Launcher
DefaultGroupName=GTA5 RAGECOOP Launcher
DisableProgramGroupPage=no
OutputDir=..\dist
OutputBaseFilename=GTA5CoopSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=GTA V RAGECOOP one-click launcher setup
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
SetupIconFile=..\assets\app_icon.ico

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\GTA5CoopLauncher.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\launcher_config.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "WINDOWS_SETUP_RU.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\github-avatar.png"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "..\dist\PLAYER_INSTRUCTIONS_RU.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\RageCoop.Client.zip"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\RageCoop.Server-win-x64.zip"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\RageCoopPlus.zip"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\ScriptHookV.zip"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\ScriptHookVDotNetEnhanced-v1.1.0.5.zip"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\wireguard-amd64-1.1.msi"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\wireguard-installer.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\playit.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Dirs]
Name: "{app}\logs"

[Icons]
Name: "{group}\GTA5 RAGECOOP Launcher"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Инструкция игроку"; Filename: "{app}\PLAYER_INSTRUCTIONS_RU.txt"; WorkingDir: "{app}"
Name: "{group}\Инструкция setup"; Filename: "{app}\WINDOWS_SETUP_RU.txt"; WorkingDir: "{app}"
Name: "{group}\Удалить GTA5 RAGECOOP Launcher"; Filename: "{uninstallexe}"
Name: "{autodesktop}\GTA5 RAGECOOP Launcher"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "msiexec.exe"; Parameters: "/i ""{app}\wireguard-amd64-1.1.msi"" /passive /norestart"; StatusMsg: "Installing WireGuard VPN..."; Check: ShouldInstallWireGuard
Filename: "{app}\playit.exe"; WorkingDir: "{app}"; StatusMsg: "Starting playit tunnel client..."; Flags: nowait skipifsilent; Check: ShouldLaunchPlayit
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить GTA5 RAGECOOP Launcher"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
Type: files; Name: "{app}\launcher_config.json.*.bak"

[Code]
var
  VpnPage: TWizardPage;
  NoVpnRadio: TNewRadioButton;
  WireGuardRadio: TNewRadioButton;
  PlayitRadio: TNewRadioButton;

procedure InitializeWizard;
begin
  VpnPage := CreateCustomPage(
    wpSelectTasks,
    'VPN / tunnel',
    'Выбери, что подготовить для подключения друга'
  );

  NoVpnRadio := TNewRadioButton.Create(VpnPage);
  NoVpnRadio.Parent := VpnPage.Surface;
  NoVpnRadio.Left := 0;
  NoVpnRadio.Top := ScaleY(8);
  NoVpnRadio.Width := VpnPage.SurfaceWidth;
  NoVpnRadio.Caption := 'Ничего не устанавливать: VPN уже настроен вручную';
  NoVpnRadio.Checked := True;

  WireGuardRadio := TNewRadioButton.Create(VpnPage);
  WireGuardRadio.Parent := VpnPage.Surface;
  WireGuardRadio.Left := 0;
  WireGuardRadio.Top := NoVpnRadio.Top + ScaleY(32);
  WireGuardRadio.Width := VpnPage.SurfaceWidth;
  WireGuardRadio.Caption := 'WireGuard VPN: встроенный установщик будет запущен после копирования файлов';

  PlayitRadio := TNewRadioButton.Create(VpnPage);
  PlayitRadio.Parent := VpnPage.Surface;
  PlayitRadio.Left := 0;
  PlayitRadio.Top := WireGuardRadio.Top + ScaleY(32);
  PlayitRadio.Width := VpnPage.SurfaceWidth;
  PlayitRadio.Caption := 'playit.gg tunnel: встроенный playit.exe будет запущен после установки';
end;

function ShouldInstallWireGuard: Boolean;
begin
  Result := Assigned(WireGuardRadio) and WireGuardRadio.Checked;
end;

function ShouldLaunchPlayit: Boolean;
begin
  Result := Assigned(PlayitRadio) and PlayitRadio.Checked;
end;
