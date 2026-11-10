; Stamp Studio — скрипт Inno Setup 6. Собирается конвейером GitHub Actions.
;   ISCC /DAppVersion=6.2.0 installer.iss                -> StampStudio-Setup-6.2.0.exe
;   ISCC /DAppVersion=6.2.0 /DCanon installer.iss        -> StampStudioCanon-Setup-6.2.0.exe
#ifndef AppVersion
  #define AppVersion "6.2.0"
#endif
#ifdef Canon
  #define AppName "Stamp Studio Canon"
  #define AppExe "StampStudioCanon.exe"
  #define DistDir "dist\StampStudioCanon"
  #define OutBase "StampStudioCanon-Setup"
  #define AppGuid "{{B4E1A0C2-6F3D-4E7A-9C15-2D8F0A7B3E61}"
#else
  #define AppName "Stamp Studio"
  #define AppExe "StampStudio.exe"
  #define DistDir "dist\StampStudio"
  #define OutBase "StampStudio-Setup"
  #define AppGuid "{{A9D27F54-1C8E-4B36-8F0A-5E3C7D9B2A40}"
#endif

[Setup]
AppId={#AppGuid}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Stamp Studio
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=installer_out
OutputBaseFilename={#OutBase}-{#AppVersion}
SetupIconFile=icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes
DisableDirPage=auto

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "installed.flag"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent
