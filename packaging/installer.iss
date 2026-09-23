; claude-tray - (c) 2026 Svatka Technologies(TM) (Alex Merovic). All rights reserved.
; Instalador do Claude Tray. Compilado por packaging\build.ps1 (Inno Setup 6).

#define AppName "Claude Tray"
#define AppVersion "1.1.0"
#define Publisher "Svatka Technologies™"
#define ExeName "ClaudeTray.exe"

[Setup]
; AppId fixo: e ele que faz a versao nova substituir a velha em vez de duplicar.
AppId={{6F2A9C1E-5B7D-4E3A-9D21-5A7C0B3E8F14}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#Publisher}
AppCopyright=© 2026 Svatka Technologies™ (Alex Merovic). All rights reserved.
AppPublisherURL=https://github.com/alexmerovic/claude-tray
AppSupportURL=https://github.com/alexmerovic/claude-tray/issues
VersionInfoCompany={#Publisher}
VersionInfoCopyright=© 2026 Svatka Technologies™ (Alex Merovic)
VersionInfoVersion={#AppVersion}
; Por usuario, sem admin: um medidor de uso nao tem por que pedir elevacao.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\Svatka\Claude Tray
DefaultGroupName=Svatka Technologies
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
SetupIconFile=ClaudeTray.ico
UninstallDisplayIcon={app}\{#ExeName}
UninstallDisplayName={#AppName}
OutputDir=..\dist
OutputBaseFilename=ClaudeTray-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Fecha o medidor rodando antes de sobrescrever o .exe numa atualizacao.
CloseApplications=force
RestartApplications=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "autostart"; Description: "Start with Windows"; Flags: checkedonce
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "..\dist\{#ExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\AGENTS.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#ExeName}"
Name: "{group}\License"; Filename: "{app}\LICENSE.txt"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon
; Mesmo nome que o `--autostart` do app usa (autostart.py): um substitui o
; outro em vez de subirem dois medidores no logon.
Name: "{userstartup}\claude-tray"; Filename: "{app}\{#ExeName}"; Tasks: autostart

[Run]
Filename: "{app}\{#ExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#ExeName}"; Flags: runhidden; RunOnceId: "StopTray"
