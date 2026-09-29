; Установщик Патрика для Windows.
;
; Собирается из packaging/build.ps1 — там подставляется версия и проверяется,
; что каталог dist\AtomPet уже собран PyInstaller'ом.
;
; Установка требует прав администратора не ради папки Program Files, а ради
; правила брандмауэра: питомец подключается к серверу по Wi-Fi, и без открытого
; входящего порта он до него не достучится. Данные пользователя при этом лежат
; не в Program Files, а в %LOCALAPPDATA% (см. backend/core/paths.py), поэтому
; программа спокойно работает из-под обычной учётной записи.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#define AppName "Atom Terminal Pet"
#define AppExe "AtomPet.exe"
#define AppMutexName "Local\AtomTerminalPet"
#define FirewallRule "Atom Terminal Pet"

[Setup]
AppId={{7A3C1E64-4F2B-4B8E-9D71-0C5A9E2F8B31}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Atom Terminal Pet
DefaultDirName={autopf}\AtomTerminalPet
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
OutputDir=out
OutputBaseFilename=AtomTerminalPet-{#AppVersion}-setup
SetupIconFile=atompet.ico
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
; Запасной вариант, если taskkill ниже не сработал: Inno сам попросит закрыть.
AppMutex={#AppMutexName}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"
Name: "autostart"; Description: "Запускать вместе с Windows"; GroupDescription: "Дополнительно:"
Name: "firewall"; Description: "Разрешить питомцу подключаться по Wi-Fi (правило брандмауэра, порт 8000)"; GroupDescription: "Дополнительно:"

[Files]
Source: "dist\AtomPet\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "AtomTerminalPet"; ValueData: """{app}\{#AppExe}"""; \
    Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{sys}\netsh.exe"; \
    Parameters: "advfirewall firewall add rule name=""{#FirewallRule}"" dir=in action=allow program=""{app}\{#AppExe}"" enable=yes profile=private,domain"; \
    StatusMsg: "Открываю порт для питомца…"; Flags: runhidden; Tasks: firewall
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppName}"; \
    Flags: nowait postinstall skipifsilent
; Тихое обновление из самого приложения: программа закрылась ради установки,
; поэтому после неё её надо вернуть. runasoriginaluser — потому что установщик
; работает от администратора, а питомец должен жить в сеансе пользователя.
Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: WizardSilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExe}"; \
    Flags: runhidden; RunOnceId: "StopAtomPet"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#FirewallRule}"""; \
    Flags: runhidden; RunOnceId: "DropFirewallRule"

[Code]
procedure StopRunningApp;
var
  ResultCode: Integer;
begin
  // Приложение живёт в трее и на запрос диспетчера перезапуска не отвечает,
  // поэтому закрываем его сами — иначе файлы окажутся занятыми.
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe}', '',
       SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function InitializeSetup(): Boolean;
begin
  StopRunningApp;
  Result := True;
end;

function InitializeUninstall(): Boolean;
begin
  StopRunningApp;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\AtomTerminalPet');
    if DirExists(DataDir) then
    begin
      // Спрашиваем, а не удаляем молча: там лежат ключ от нейросети,
      // заметки и долговременная память о пользователе.
      if MsgBox('Удалить настройки, заметки и журналы Патрика?' + #13#10 + #13#10 +
                DataDir + #13#10 + #13#10 +
                'Ответьте «Нет», если планируете установить программу заново.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
