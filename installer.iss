; Instalador do NEXUS PC (Inno Setup 6). Compilado pelo GitHub Actions.
#ifndef AppVersion
  #define AppVersion "2.1.0"
#endif
[Setup]
AppId={{6E1B7E0C-6D0A-4D86-9F6B-2B6B3C2F9A11}
AppName=NEXUS PC
AppVersion={#AppVersion}
AppPublisher=Erik Messias
DefaultDirName={autopf}\NEXUS PC
DefaultGroupName=NEXUS PC
OutputDir=dist
OutputBaseFilename=NexusPC-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\NexusPC.exe
WizardStyle=modern

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "dist\NexusPC.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\NEXUS PC"; Filename: "{app}\NexusPC.exe"
Name: "{autodesktop}\NEXUS PC"; Filename: "{app}\NexusPC.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; Flags: unchecked

[Run]
Filename: "{app}\NexusPC.exe"; Description: "Abrir o NEXUS PC"; Flags: nowait postinstall skipifsilent
