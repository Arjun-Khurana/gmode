; Inno Setup script for the Windows installer. packaging/build.py compiles it with ISCC and passes
; AppVersion, SourceDir (the PyInstaller dist/GMode folder), OutputDir, OutputBase and IconFile.
; Installs per user by default (no admin prompt); the first page offers an all-users install.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; AppId identifies GMode to Windows across versions: never change it, or upgrades install side by side
AppId={{9AB18657-12AE-46F0-83DF-1001F2B79EF5}
AppName=GMode
AppVersion={#AppVersion}
AppVerName=GMode {#AppVersion}
AppPublisher=GMode
AppPublisherURL=https://github.com/Arjun-Khurana/gmode
DefaultDirName={autopf}\GMode
DefaultGroupName=GMode
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBase}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\GMode.exe
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ChangesAssociations=yes
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "assoc"; Description: "Open .gmode project files with GMode"; GroupDescription: "File types:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; an upgrade replaces the whole app folder, so files dropped from a newer build don't linger
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\GMode"; Filename: "{app}\GMode.exe"
Name: "{autodesktop}\GMode"; Filename: "{app}\GMode.exe"; Tasks: desktopicon

[Registry]
; HKA is the current user's classes for a per-user install, the machine's for an all-users install
Root: HKA; Subkey: "Software\Classes\.gmode"; ValueType: string; ValueName: ""; ValueData: "GMode.Project"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\GMode.Project"; ValueType: string; ValueName: ""; ValueData: "GMode project"; Flags: uninsdeletekey; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\GMode.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\GMode.exe,0"; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\GMode.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\GMode.exe"" ""%1"""; Tasks: assoc

[Run]
Filename: "{app}\GMode.exe"; Description: "{cm:LaunchProgram,GMode}"; Flags: nowait postinstall skipifsilent
