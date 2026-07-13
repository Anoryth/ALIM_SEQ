; Inno Setup — installateur Windows d'ALIM_SEQ.
; Propose le choix ADMIN (tous les utilisateurs, Program Files) ou
; SANS DROITS ADMIN (utilisateur courant, %LOCALAPPDATA%) via la boîte de dialogue
; standard d'Inno (grâce à PrivilegesRequiredOverridesAllowed).
;
; Compilation (sous Windows, après PyInstaller) :
;     iscc packaging\ALIM_SEQ.iss
; -> produit packaging\Output\ALIM_SEQ-Setup.exe

#define AppName "ALIM_SEQ"
; AppVersion peut être surchargée en ligne de commande : ISCC /DAppVersion=1.2.3
; (la CI la dérive du tag git). Valeur de repli pour une compilation manuelle.
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
; {autopf} = Program Files (admin) ou %LOCALAPPDATA%\Programs (sans admin),
; résolu selon le mode choisi à l'installation.
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=Output
OutputBaseFilename={#AppName}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Icone de l'installateur et de l'entree "Programmes et fonctionnalites".
SetupIconFile=icon.ico
; Logo de l'application dans l'assistant (page d'accueil/fin + coin sup. droit).
WizardImageFile=wizard-large.bmp
WizardSmallImageFile=wizard-small.bmp
ArchitecturesInstallIn64BitMode=x64compatible
; --- Choix admin / sans admin ---
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
UninstallDisplayIcon={app}\{#AppExe}

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Choix de l'interface : cochee = Qt (moderne) ; decochee = Tkinter (legere).
Name: "guiqt"; Description: "Interface graphique Qt (moderne, recommandee) — decochez pour l'interface Tkinter legere"; GroupDescription: "Interface graphique :"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; PyInstaller produit un DOSSIER (mode onedir) : dist\ALIM_SEQ\ (ALIM_SEQ.exe +
; _internal\). On installe tout le dossier ; l'exe atterrit dans {app}\ALIM_SEQ.exe.
Source: "..\dist\ALIM_SEQ\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
; Dossier de DONNEES choisi par l'utilisateur : on y depose config.json et les
; sequences par defaut (sans ecraser d'eventuels fichiers existants ; jamais
; supprimes a la desinstallation pour preserver les donnees de l'utilisateur).
Source: "..\config.json"; DestDir: "{code:GetDataDir}"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "..\sequences\*"; DestDir: "{code:GetDataDir}\sequences"; Flags: recursesubdirs onlyifdoesntexist uninsneveruninstall

[Dirs]
; Cree le dossier de donnees (logs, essais y seront ecrits a l'execution).
Name: "{code:GetDataDir}"; Flags: uninsneveruninstall
Name: "{code:GetDataDir}\logs"; Flags: uninsneveruninstall

[Registry]
; L'emplacement choisi est lu par launcher.py au demarrage (HKA = HKLM en
; installation admin, HKCU en installation par utilisateur).
Root: HKA; Subkey: "Software\ALIM_SEQ"; ValueType: string; ValueName: "DataDir"; ValueData: "{code:GetDataDir}"; Flags: uninsdeletekey

[Icons]
; Raccourci Qt (aucun parametre : le lanceur demarre en Qt par defaut).
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: guiqt
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon and guiqt
; Raccourci Tkinter (--gui tk : le lanceur respecte ce choix).
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--gui tk"; Tasks: not guiqt
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--gui tk"; Tasks: desktopicon and not guiqt
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent; Tasks: guiqt
Filename: "{app}\{#AppExe}"; Parameters: "--gui tk"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent; Tasks: not guiqt

[Code]
{ Page supplementaire : ou ranger les DONNEES (config.json, journaux, essais). }
var
  DataDirPage: TInputDirWizardPage;

procedure InitializeWizard;
begin
  DataDirPage := CreateInputDirPage(wpSelectDir,
    'Emplacement des donnees',
    'Ou ALIM_SEQ doit-il ranger la configuration et les journaux ?',
    'ALIM_SEQ ecrira dans ce dossier :' + #13#10 +
    '    - config.json (la configuration, editable depuis l''appli)' + #13#10 +
    '    - logs\ (journal applicatif et dossiers d''essai : mesures, rapports)' + #13#10 +
    '    - sequences\ (vos sequences)' + #13#10 + #13#10 +
    'Choisissez un dossier INSCRIPTIBLE (evitez Program Files). Par defaut, votre dossier Documents :',
    False, '');
  DataDirPage.Add('');
  DataDirPage.Values[0] := ExpandConstant('{userdocs}\ALIM_SEQ');
end;

function GetDataDir(Param: String): String;
begin
  Result := DataDirPage.Values[0];
end;
