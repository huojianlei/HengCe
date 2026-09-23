#ifndef PackageRoot
  #error PackageRoot is required
#endif
#ifndef OutputRoot
  #error OutputRoot is required
#endif
#define AppVersion "1.0.5"
#ifndef AppFlavor
  #define AppFlavor "Production"
#endif
#if AppFlavor == "Experimental"
  #define AppShortName "衡策1.0.5演示版"
  #define AppFolder "FinAgent-Experimental"
  #define AppGuid "{{4274C07B-FF8C-44A4-A67B-12B3B8BC78AC}"
  #define AppRunningMutex "FinAgent105.Experimental.Desktop.Running"
#else
  #define AppShortName "衡策1.0.5"
  #define AppFolder "FinAgent"
  #define AppGuid "{{13161FDE-6F15-4049-9D94-F3B0DC428F1D}"
  #define AppRunningMutex "FinAgent105.Desktop.Running"
#endif

[Setup]
AppId={#AppGuid}
AppName={#AppShortName} · 智能预算差异分析与风险预警系统
AppVersion={#AppVersion}
AppPublisher=衡策项目组
DefaultDirName=D:\衡策\1.0.5\{#AppFolder}
DefaultGroupName={#AppShortName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0
OutputDir={#OutputRoot}
OutputBaseFilename=衡策-1.0.5-安装包
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableWelcomePage=yes
DisableDirPage=no
DisableProgramGroupPage=yes
DisableReadyPage=yes
Uninstallable=yes
CreateUninstallRegKey=yes
UninstallDisplayIcon={app}\FinAgent.exe
SetupIconFile={#PackageRoot}\衡策图标.ico
AppMutex={#AppRunningMutex}
CloseApplications=no
RestartApplications=no
SetupLogging=no
VersionInfoVersion=1.0.5.0
VersionInfoDescription=衡策安装程序

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce

[Files]
Source: "{#PackageRoot}\*"; DestDir: "{app}"; Excludes: "qa-模板包内验证\*,__pycache__\*,*.pyc"; Flags: ignoreversion recursesubdirs createallsubdirs

#if AppFlavor == "Production"
[InstallDelete]
Type: filesandordirs; Name: "{app}\desktop\experimental"
Type: files; Name: "{app}\desktop\web\demo.json"
#endif

[Icons]
Name: "{group}\{#AppShortName}"; Filename: "{app}\FinAgent.exe"; WorkingDir: "{app}"; IconFilename: "{app}\衡策图标.ico"
Name: "{group}\卸载{#AppShortName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppShortName}"; Filename: "{app}\FinAgent.exe"; WorkingDir: "{app}"; IconFilename: "{app}\衡策图标.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\FinAgent.exe"; Description: "启动衡策预算工作台"; Flags: nowait postinstall skipifsilent

[Code]
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := PageID = wpSelectTasks;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectDir then begin
    WizardForm.NextButton.Caption := '一键安装(&I)';
    WizardForm.SelectDirLabel.Caption := '选择安装位置，点击“一键安装”即可完成部署。Node、Python、知识库和嵌入模型已内置。';
  end;
end;
