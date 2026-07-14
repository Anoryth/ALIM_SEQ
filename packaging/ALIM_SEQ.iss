; Inno Setup — ALIM_SEQ Windows installer.
; Offers the ADMIN choice (all users, Program Files) or NO-ADMIN (current user,
; %LOCALAPPDATA%) via Inno's standard dialog (thanks to
; PrivilegesRequiredOverridesAllowed).
;
; Compilation (on Windows, after PyInstaller):
;     iscc packaging\ALIM_SEQ.iss
; -> produces packaging\Output\ALIM_SEQ-Setup.exe

#define AppName "ALIM_SEQ"
; AppVersion can be overridden on the command line: ISCC /DAppVersion=1.2.3
; (the CI derives it from the git tag). Fallback value for a manual compilation.
#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif
#define AppPublisher "FP"
#define AppExe "ALIM_SEQ.exe"

[Setup]
AppId={{B3E6F2A1-9C2D-4E7A-9B1F-ALIMSEQ00001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
; {autopf} = Program Files (admin) or %LOCALAPPDATA%\Programs (no admin),
; resolved according to the mode chosen at install time.
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=Output
OutputBaseFilename={#AppName}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Icon of the installer and of the "Programs and Features" entry.
SetupIconFile=icon.ico
; Application logo in the wizard (welcome/finish page + top-right corner).
WizardImageFile=wizard-large.bmp
WizardSmallImageFile=wizard-small.bmp
ArchitecturesInstallIn64BitMode=x64compatible
; --- Admin / no-admin choice ---
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
UninstallDisplayIcon={app}\{#AppExe}

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; PyInstaller produces a FOLDER (onedir mode): dist\ALIM_SEQ\ (ALIM_SEQ.exe +
; _internal\). We install the whole folder; the exe lands in {app}\ALIM_SEQ.exe.
Source: "..\dist\ALIM_SEQ\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
; User-chosen DATA folder: we drop config.json and the default sequences there
; (without overwriting any existing files; never removed at uninstall time to
; preserve the user's data).
Source: "..\config.json"; DestDir: "{code:GetDataDir}"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "..\sequences\*"; DestDir: "{code:GetDataDir}\sequences"; Flags: recursesubdirs onlyifdoesntexist uninsneveruninstall

[Dirs]
; Create the data folder (logs, tests will be written there at runtime).
Name: "{code:GetDataDir}"; Flags: uninsneveruninstall
Name: "{code:GetDataDir}\logs"; Flags: uninsneveruninstall

[Registry]
; The chosen location is read by launcher.py at startup (HKA = HKLM for an admin
; install, HKCU for a per-user install).
Root: HKA; Subkey: "Software\ALIM_SEQ"; ValueType: string; ValueName: "DataDir"; ValueData: "{code:GetDataDir}"; Flags: uninsdeletekey

[Icons]
; The application starts in Qt (the only interface, no parameter).
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
{ Extra page: where to store the DATA (config.json, logs, tests). }
var
  DataDirPage: TInputDirWizardPage;

procedure InitializeWizard;
begin
  DataDirPage := CreateInputDirPage(wpSelectDir,
    'Data location',
    'Where should ALIM_SEQ store its configuration and logs?',
    'ALIM_SEQ will write in this folder:' + #13#10 +
    '    - config.json (the configuration, editable from the app)' + #13#10 +
    '    - logs\ (application log and test folders: measurements, reports)' + #13#10 +
    '    - sequences\ (your sequences)' + #13#10 + #13#10 +
    'Choose a WRITABLE folder (avoid Program Files). By default, your Documents folder:',
    False, '');
  DataDirPage.Add('');
  DataDirPage.Values[0] := ExpandConstant('{userdocs}\ALIM_SEQ');
end;

function GetDataDir(Param: String): String;
begin
  Result := DataDirPage.Values[0];
end;
