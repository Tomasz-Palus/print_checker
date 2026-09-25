; Instalator adCheckera na Windows (Inno Setup 6). Buduje go GitHub (build.yml):
;   iscc /DAppVersion=0.3 packaging\windows\adchecker.iss
; Instaluje dla bieżącego użytkownika (bez uprawnień administratora) do
; %LOCALAPPDATA%\Programs\adChecker, skrót w menu Start i na pulpicie.
#ifndef AppVersion
  #define AppVersion "0.0"
#endif

[Setup]
AppId={{6F1B7C2A-3D84-4E0B-9C51-2A7D0E4B8F13}
AppName=adChecker
AppVersion={#AppVersion}
AppVerName=adChecker {#AppVersion}
AppPublisher=Adsystem
DefaultDirName={localappdata}\Programs\adChecker
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=adChecker-{#AppVersion}-Windows-instalator
SetupIconFile=..\adchecker.ico
UninstallDisplayIcon={app}\adChecker.exe
UninstallDisplayName=adChecker
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; stara wersja programu znika w całości — biblioteki z różnych wersji nie mogą się mieszać
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\..\dist\adChecker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\adChecker"; Filename: "{app}\adChecker.exe"
Name: "{autodesktop}\adChecker"; Filename: "{app}\adChecker.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\adChecker.exe"; Description: "{cm:LaunchProgram,adChecker}"; Flags: nowait postinstall skipifsilent
; aktualizacja z programu („Zaktualizuj teraz") idzie po cichu — wtedy program startuje sam
Filename: "{app}\adChecker.exe"; Flags: nowait skipifnotsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
