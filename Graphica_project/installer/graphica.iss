; Graphica の Windows インストーラー(Inno Setup 6)。CI が PyInstaller の出力 dist\Graphica\ から作る。
;   iscc /DAppVersion=2.0.0 installer\graphica.iss
; 関連付けの名前(Graphica.Project と .gra / .graphica)は graphica/gui/file_association.py と同じにする。
; 環境設定のボタンで登録した人がインストーラーで入れ直しても、同じキーを上書きするだけで二重にならない。

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Graphica"
#define AppExe "Graphica.exe"
#define ProgId "Graphica.Project"

[Setup]
AppId={{6B0C2F4E-9A1D-4E7B-8C53-5F2D7E9A1B64}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=STsuruga
AppPublisherURL=https://github.com/STsuruga/Graphica
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; 管理者権限なしで入れられる(その利用者だけ)。管理者なら全員向けも選べる
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=Graphica-{#AppVersion}-setup
SetupIconFile=..\graphica\Graphica.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
LicenseFile=..\dist\Graphica\LICENSE

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "fileassoc"; Description: ".gra と .graphica を {#AppName} で開く"; GroupDescription: "ファイルの関連付け:"

[Files]
Source: "..\dist\Graphica\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; HKA は、その利用者だけのインストールなら HKCU、全員向けなら HKLM
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueName: ""; ValueData: "Graphica プロジェクト"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"",0"; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.gra"; ValueType: string; ValueName: ""; ValueData: "{#ProgId}"; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.graphica"; ValueType: string; ValueName: ""; ValueData: "{#ProgId}"; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.gra\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.graphica\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
