; Inno Setup script for FoxLogin (Windows x64; also runs on Windows 11 ARM via emulation).
; Built by packaging/build.py:  iscc /DAppVersion=1.0.0 /DSourceDir=... /DOutputDir=... foxlogin.iss

#ifndef AppVersion
  #define AppVersion "1.0.1"
#endif

[Setup]
AppId={{6F1D2C55-3A7E-4E39-9C52-F0C5A1D7B6E1}
AppName=FoxLogin
AppVersion={#AppVersion}
AppPublisher=FoxLogin
DefaultDirName={autopf}\FoxLogin
DefaultGroupName=FoxLogin
DisableProgramGroupPage=yes
; Per-user install by default: no admin prompt needed
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=FoxLogin-{#AppVersion}-windows-x64-setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\FoxLogin.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\FoxLogin"; Filename: "{app}\FoxLogin.exe"
Name: "{autodesktop}\FoxLogin"; Filename: "{app}\FoxLogin.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FoxLogin.exe"; Description: "{cm:LaunchProgram,FoxLogin}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Close running profiles' runners before files are removed
Filename: "{sys}\taskkill.exe"; Parameters: "/F /T /IM FoxLogin.exe"; Flags: runhidden; RunOnceId: "KillFoxLogin"
