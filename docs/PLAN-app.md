# План доработки приложения: трей, бэкенд, панель, упаковка

Все пути относительно корня репозитория. Приоритеты P0–P3, трудоёмкость S (вечер),
M (2–3 вечера), L (неделя+). Ссылки `файл:строка` — на состояние рабочего дерева 2026-09-07.

## Цели и ограничения

- Главная цель: Патрик живёт в трее Windows, стартует вместе с системой, панель в браузере
  нужна только для настройки. Всё ежедневное (микрофон, перебить, подтверждения, помодоро)
  доступно из трея.
- Один разработчик, Windows 11, Python 3.14 в `backend/venv`, Node.js для MCP-серверов.
- Сервер обязан быть доступен по Wi-Fi для питомца, значит нельзя просто закрыть его на
  localhost. Нужно развести «устройство» (наружу) и «управление» (только loopback).
- Обратная совместимость: прошивка 3.0.0 работает с новым сервером.

## Что уже есть

- `backend/tray_app.py`: единственный экземпляр (мьютекс), uvicorn в фоновом потоке, меню
  (панель, папка данных, журнал, автозапуск через HKCU\Run, перезапуск, выход), подмена
  `stdout/stderr` для windowed-сборки. `backend/tray_icon.py` рисует иконку и `.ico`.
- `backend/core/paths.py`: ресурсы и данные разведены, обходов в коде нет.
- `packaging/`: `atompet.spec` (onedir), `build.ps1`, `installer.iss`, `VERSION`.
- Тесты: 57 в бэкенде, 9 в панели, все проходят.

## Чего нет или что сломано

- Сборка 31.08 не дошла до PyInstaller; `packaging/` не закоммичен, `*.spec` игнорируется.
- Исключение при `from main import app` в трее уходит в `/dev/null`: статус «Остановлен» без причины.
- Сервер на `0.0.0.0` без аутентификации, CORS `*` с credentials, LFI в раздаче панели,
  инъекции в оболочку из «безопасных» инструментов.
- Питомец по Wi-Fi получает весь панельный трафик, включая снимок задач и микрофон браузера.
- Без открытой панели запрос подтверждения умирает по таймауту через 180 с.

---

## Этап A0 — Безопасность и протокол (P0, 2–3 дня)

### [ ] A0.1 LFI в раздаче панели — S
`backend/main.py:637-648`: `os.path.join(dist_dir, full_path)` без нормализации.
Подтверждено: `GET /../../backend/settings.json` отдаёт файл с ключом.
Сделать `Path(dist_dir, full_path).resolve()` и `is_relative_to(dist)`, иначе `index.html`.
Для `index.html` — `Cache-Control: no-store` (после обновления старый index тянет
несуществующие хэшированные ассеты).
Приёмка: тест в `test_main.py` на `..` и путь с буквой диска → отдаётся index.

### [ ] A0.2 Управление только с loopback — M
- Middleware: клиент не loopback → разрешены только WS устройства и `/firmware/*`,
  остальное 403.
- CORS: явные origins (`http://localhost:8000`, `http://127.0.0.1:8000`,
  `http://localhost:5173`), без `allow_credentials` (`main.py:94-100`).
- `TrustedHostMiddleware`: localhost, 127.0.0.1, LAN-IP.
- WS: если пришёл `Origin` не из списка — закрыть (ESP32 Origin не шлёт).
- Токен устройства (следующий шаг, этап T3): `DEVICE_TOKEN` генерируется при первом
  запуске в `data/`, передаётся прошивке по USB вместе с Wi-Fi, проверяется в query WS.
Приёмка: preflight с чужим Origin → нет `Access-Control-Allow-Origin`;
`POST /api/tools/run_command/run` с не-loopback → 403.

### [ ] A0.3 Инъекции в оболочку — S
- `backend/ai/tools/dev.py:18-26, 119-126`: `git_status`/`git_diff` через
  `create_subprocess_exec(["git", ...])`, `path` — отдельный аргумент. Сейчас `git_diff`
  помечен safe, а `path='" & calc & "'` выполняет команду без подтверждения.
- `backend/ai/tools/system.py:274-275`: `open_program` через `os.startfile` для
  файлов/URL и `Popen([exe, *args])` без shell; при непустых `args` — risk=danger.
- Все subprocess: `stdin=DEVNULL` и `creationflags=CREATE_NO_WINDOW`. В windowed-сборке
  без этого — `WinError 6` и мигающие окна cmd.
Приёмка: тест `git_diff(path='" & calc & "')` не запускает ничего лишнего.

### [ ] A0.4 Устройство — не панельный клиент — M (пара с fw F1.4)
`backend/core/ws_manager.py:108-119`, `backend/core/events.py:125-143`, `backend/main.py:219-222`.
- `broadcast_json` и `broadcast_binary*` исключают `device_ws`.
- В `EventBus.emit`: если `device_on_wifi` и `action in DEVICE_ACTIONS` →
  `send_json(_device_message(msg), device_ws)`. Транслитерация и лимит 64 символа
  сейчас работают только по USB.
- `tasks_snapshot` не слать устройству. Панель запрашивает его сама (`get_tasks`).
- `broadcast_binary` только при `audio_output` в `pet`/`both`; по USB это уже учтено, по Wi-Fi нет.
- `DEVICE_ACTIONS` += `set_autorotate`, `restart`, `status`, `device_volume` (переименовать
  `set_volume`, чтобы не путать с инструментом громкости ПК). `listening`/`pomodoro` —
  сервер не шлёт, пометить мёртвыми.
- `main.py:135-137`: устройством считать только клиента, чей `device_status` содержит `fw`
  (и токен после A0.2). Сейчас любой WS-клиент с `device_status` отбирает USB-питомца.
- Сохранять `device_info["proto"]` для различения версий прошивки.
Приёмка: тест в `test_events.py` — при `device_on_wifi` кириллический `speak` уходит
транслитом, `task_update` не уходит вовсе.

### [ ] A0.5 Тесты не трогают данные пользователя — S
`backend/tests/conftest.py`: `ATOM_DATA_DIR` = temp до импорта `core.paths`, копия
`settings.example.json`. Сейчас `test_main.py:36-51` перезаписывает реальный
`settings.json`, `test_tools.py` пишет в `logs/audit.jsonl`.

### [ ] A0.6 Git и сборка: мелочи, без которых ничего не соберётся — S
- `.gitignore`: `!packaging/atompet.spec`; закоммитить `packaging/` без `build/`, `dist/`, `out/`.
- `packaging/atompet.spec:23-27`: добавить `backend/rules` в `datas` — иначе `rules.yaml`
  не попадает в сборку и правил «из коробки» нет.
- `backend/requirements.txt`: `winrt-Windows.Foundation`, `winrt-Windows.Storage.Streams`
  (без них `MediaManager.request_async()` падает, «что играет» не работает уже сейчас);
  добавить в `hiddenimports`.

---

## Этап T1 — Трей: надёжный старт и стоп (P0/P1, 2 дня)

### [ ] T1.1 Видимые ошибки старта — S
`backend/tray_app.py:141-158`: `from main import app` и `uvicorn.Config` внутри
`try/except BaseException` → `self.error`, `logger.exception`. Поток-наблюдатель ждёт
`started` или смерти потока; смерть без `started` → `error = "Сервер не запустился — см. журнал"`,
`icon.notify`, красная иконка. `threading.excepthook` пишет в `app.log`.
Отдельно: если `settings.json` не распарсился и `core/settings.py:132,147` откатился на
дефолты — уведомить, а не молчать.
Приёмка: испортить `prompts.yaml` → уведомление с текстом ошибки.

### [ ] T1.2 Честная проба порта — S
`backend/tray_app.py:132-139`: `SO_REUSEADDR` на Windows разрешает bind на занятый порт,
проба всегда говорит «свободно». Использовать `SO_EXCLUSIVEADDRUSE`. Если занят —
`GET /api/health`: отвечает Патрик → «уже запущен из исходников», иначе имя процесса через
`psutil.net_connections`.

### [ ] T1.3 Выход без заморозки и без сирот — M
- `on_quit`: скрыть иконку → `notify("Завершаю…")` → `runner.stop()` в отдельном потоке →
  `icon.stop()`. Сейчас `stop(timeout=20)` блокирует цикл сообщений pystray до 20 с.
- `backend/main.py:77-89`: `serial_manager.stop()` до `mcp_manager.cleanup()`; отменённые
  задачи ожидать через `gather` с таймаутом; отменять `_reminder_tasks`
  (`ai/tools/productivity.py:53`).
- Job Object с `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` при старте (ctypes): дочерние `node`
  MCP умирают вместе с процессом даже при `taskkill /F`.
Приёмка: выход при двух работающих MCP → в диспетчере нет `node`, COM-порт свободен.

### [ ] T1.4 «Перезапустить сервер» = перезапуск процесса — S
`backend/tray_app.py:225-228` создаёт новый event loop, а `asyncio.Lock`/`Queue` в
синглтонах (`core/events.py:110`, `tasks/task_manager.py:117`, `ai/voice.py:128`)
привязаны к старому → `RuntimeError` на первой задаче. Проще: освободить мьютекс,
`Popen([sys.executable, *sys.argv[1:]])`, затем `on_quit`.

### [ ] T1.5 Второй экземпляр и флаг `--quit` — S
Вместо MessageBox: событие `Local\AtomTerminalPet.Open` → главная копия открывает панель.
`AtomPet.exe --quit` → событие `.Quit` → главная копия делает `on_quit`. Нужно установщику
(P2.4) вместо `taskkill /F`.

### [ ] T1.6 Мелочи — S
- Автозапуск из исходников через `pythonw.exe` (`tray_app.py:80-83`), иначе при логоне консоль.
- `WinDLL("kernel32", use_last_error=True)` + `ctypes.get_last_error()`; проверять
  NULL-хендл мьютекса (`tray_app.py:54-57`).

---

## Этап P2 — Сборка и установщик до конца (P1, 2–3 дня)

### [ ] P2.1 Разделить зависимости — S
`backend/requirements.txt` → только runtime. Перед удалением проверить grep импортов:
`langchain`, `langchain-community`, `langgraph`, `edge-tts`, `miniaudio`, `pydub`, `jinja2`,
`python-dotenv`, `python-multipart` в коде не импортируются; `pydub` на Python 3.14 сломан.
`requirements-dev.txt` += `ruff`. Новые: `packaging/requirements-build.txt`
(`pyinstaller==6.22.2`, `pystray==0.19.5`, `pillow==12.3.0`), `firmware/requirements.txt`
(`platformio`). Зафиксировать версию Python для сборки.

### [ ] P2.2 spec — S
- `sys.path.insert(0, BACKEND)` до `collect_submodules("ai.tools")` (`atompet.spec:67`
  сейчас возвращает пустой список, спасает только явный импорт в `ai/tools/__init__.py`).
- `datas` += `backend/rules`, `packaging/VERSION`.
- `EXE(version=...)`: ресурс версии с продуктом и компанией — без него SmartScreen и
  антивирусы злее.
- `excludes` += `pip`, `setuptools`.
- `node_modules` (31 МБ) оставить, но в `build.ps1` делать `npm ci --omit=dev` в `backend/`.

### [ ] P2.3 Версия из одного места — S
`packaging/VERSION` → в `datas` → `core/paths.py: version()` → `/api/health`
(сейчас захардкожено `main.py:92`), заголовок трея, `installer.iss` через `/DAppVersion`.

### [ ] P2.4 Установщик без прав администратора — M
`packaging/installer.iss`:
- `PrivilegesRequired=lowest`, `PrivilegesRequiredOverridesAllowed=dialog`,
  `DefaultDirName={userpf}\AtomTerminalPet`. Сейчас `admin` + запись в HKCU и
  `{localappdata}` из `[Code]` — при вводе чужих админ-кредов автозапуск и «удалить данные»
  уходят в hive администратора.
- Правило брандмауэра — отдельный необязательный шаг с `Verb: runas`, плюс пункт в трее
  «Разрешить подключение по Wi-Fi» (`ShellExecuteW(..., "runas", "netsh", ...)`).
- `PrepareToInstall`/`InitializeUninstall`: `AtomPet.exe --quit`, ждать 15 с,
  `taskkill` — fallback. Сейчас `InitializeSetup` убивает приложение до показа мастера.
- `[InstallDelete] Type: filesandordirs; Name: "{app}\_internal"` — старые ассеты не копятся.
- `CurUninstallStepChanged(usUninstall)`: удалять HKCU\Run независимо от того, была ли
  выбрана задача автозапуска при установке.

### [ ] P2.5 build.ps1 — S
`Start-Transcript packaging/out/build.log`; `npm ci` вместо `npm install`; зависимости из
`requirements-build.txt`; необязательная подпись `signtool` при заданном
`ATOMPET_CERT_THUMBPRINT` и `SignTool=` в Inno.

### [ ] P2.6 Полная сборка и smoke-тест — M
На чистом аккаунте Windows: установить → иконка в трее → панель открывается → ввести ключ →
команда в чате выполняется → MCP `web_search` при наличии Node → USB-питомец подключается →
выход чистый → удаление с вопросом о данных. Чеклист в `packaging/SMOKE.md`.

---

## Этап T3 — Трей: ежедневный UX (P1/P2, 3–4 дня)

Всё ниже делается без WS-клиента: сервер живёт в том же процессе.

### [ ] T3.1 Мост «сервер → трей» — S
- `EventBus.subscribe(cb)`: список слушателей в `emit` (`core/events.py:125`).
- В lifespan: `app.state.loop = asyncio.get_running_loop()`.
- Из потока трея: `asyncio.run_coroutine_threadsafe(coro, app.state.loop)`.

### [ ] T3.2 Статус-иконка — M
Шесть состояний: остановлен/ошибка, питомец не подключён, слушает, думает, говорит,
«не беспокоить». Бейдж поверх `tray_icon.build_image`, картинки кэшируются, меняется
`icon.icon`. Источники: `agent_status` (`ai/agent.py:155,180`, `tasks/task_manager.py:287-304`),
`voice_state`, `device_status_update`, `runner.error`.

### [ ] T3.3 Меню быстрых действий — S
- Микрофон вкл/выкл → `settings_store.update({"voice_enabled": ...})` + `bus.emit("set_mic")`.
- Перебить → `voice_pipeline.interrupt("tray")` (`ai/voice.py:242`).
- Помодоро 25 мин / стоп → `pc_monitor.start_pomodoro/stop_pomodoro`
  (`monitor/pc_monitor.py:194-200`), остаток минут в тексте пункта.
- Не беспокоить → новая настройка `quiet_mode`: `bus.speak` не озвучивает (только панель
  и экран), `rule_engine` не говорит и не меняет эмоцию.
- Звук: питомец / ПК / оба (`audio_output`).
- Ссылки: Настройки `/settings`, Прошивка `/install`, Журнал `/debug`.
- Статус устройства в меню: «USB COM5» / «Wi-Fi 192.168.x.x» / «не подключён».
- «Скопировать адрес сервера» (LAN-IP:8000) — нужен для `SERVER_IP` в прошивке.

### [ ] T3.4 Подтверждения из уведомлений — M
`tasks/task_manager.py:190-235` ждёт ответа до 180 с; без открытой панели пользователь
запрос не видит. Подписаться на `approval_request` → тост с кнопками «Разрешить / Отклонить»
(`windows-toasts`; нужен AUMID через `SetCurrentProcessExplicitAppUserModelID` и
`AppUserModelID` у ярлыка в `[Icons]`) → `task_manager.resolve_approval(id, decision)`.
Fallback для portable-сборки: balloon + динамический раздел меню «Подтверждения».
Уведомлять и о `task failed`.

### [ ] T3.5 Первый запуск и диагностика — S
- Пустой `api_key` → уведомление «Укажите ключ модели» + панель на `/settings`.
- `shutil.which("node")` пуст → «Node.js не найден, MCP-серверы недоступны», а не общая
  ошибка MCP.
- Нет модели Vosk → пункт «Скачать модель распознавания» в `data/models` с прогрессом.
  `backend/scripts/download_vosk_model.py:10` перевести на `paths.data("models")`;
  подсказка в `ai/stt.py:44` про скрипт в сборке бессмысленна.
- «Собрать диагностику» → zip: `app.log`, `settings.json` без ключей, `/api/health`.

---

## Этап B4 — Бэкенд: голос и агент (P1/P2, 3–4 дня)

### [ ] B4.1 Синхронные инструменты вне event loop — S
`backend/ai/tools/base.py:199-201`: `await asyncio.to_thread(spec.func, **args)` для
не-корутин. `list_processes` занимает 1.8 с в loop, `grep_files`/`delete_path` — секунды;
на это время останавливается отправка аудио на устройство и речь рвётся.
`set_reminder` (`ai/tools/productivity.py:126`) вызывает `create_task` из sync-функции —
сделать `async def`.

### [ ] B4.2 Монитор ПК — S
`backend/monitor/pc_monitor.py:137-141`: сбор метрик через `to_thread`; `nvidia-smi` с
таймаутом 4 с сейчас блокирует loop. Убрать GPUtil. `:183-184`: слать `update_pc` и при
`serial_manager.is_connected` — сейчас USB-питомец без открытой панели метрик не получает.

### [ ] B4.3 Не слышать себя — M
`backend/ai/voice.py:171-173`, `backend/core/events.py:241-268`: флаг `_speaking` истинен
только внутри `send_audio`, между предложениями он ложный, и VAD ловит хвост своей речи.
Сделать счётчик активных реплик на всё время `speak()`; «окно тишины» 0.5–0.8 с после речи
(настройка); слать устройству `set_mic off/on` на время речи. Во время речи копить preroll,
чтобы не терять начало фразы при перебивании (`voice.py:231-250`).

### [ ] B4.4 Очередь речи — S
`core/events.py:165,219`: напоминание, правило, `shake`, `/api/say` инкрементируют
`speech_id` и молча обрывают потоковый ответ агента. Сериализовать `speak()` через lock;
инвалидировать только по `cancel_speech`.

### [ ] B4.5 Темп TTS по часам и `audio_start{id}` — S (пара с fw F1.6)
`core/events.py:249-259`: чанк `i` не раньше `t0 + i·0.128 − 0.3`, а не `sleep(0.11)`;
перед новым предложением учитывать `queued_ms` из `device_status`. Перед потоком слать
`{"action":"audio_start","id":speech_id}`; прошивка 3.0.0 его игнорирует.

### [ ] B4.6 Распознавание — S
`backend/ai/stt.py:33-55`: lock на загрузку модели (сейчас две первые фразы грузят её
дважды), прогрев в lifespan. `ai/voice.py:200-206`: `AcceptWaveform` на каждый чанк,
`PartialResult` раз в 0.25 с — сейчас партиалы в панели мусорные.

### [ ] B4.7 Устойчивость обработчиков — S
- `main.py:224-241`: try/except вокруг одного сообщения, а не всего соединения
  (сейчас `count="abc"` рвёт WS устройства).
- `tasks/task_manager.py:257-267`: различать отмену воркера и задачи
  (`asyncio.current_task().cancelling()`), иначе на выключении звучит «Отменил задачу».
- `core/mcp_client.py:204-209`: дренировать очередь упавшего сервера (сейчас 100 с ожидания).
- `ai/voice.py:216`: держать ссылки на fire-and-forget задачи.
- `ai/agent.py:57-64`: `format_map` вместо `format` — фигурная скобка в `prompts.yaml`
  роняет все задачи; `:166` обрабатывать `invalid_tool_calls`; общий дедлайн задачи через
  `asyncio.timeout` (сейчас теоретически до 40 минут).

### [ ] B4.8 Serial в отдельном потоке — M
`backend/core/serial_manager.py:78-149`: побайтовая state machine (как в `Link.cpp:262`),
поток чтения + `call_soon_threadsafe`, запись через очередь и поток (сейчас `write_timeout=2`
прямо из `bus.emit`); ловить `SerialException`/`OSError` по типу, а не по подстроке.
Handshake: после открытия порта слать `status`, ждать `device_status` 2 с, иначе отпустить —
сейчас захватывается любой Espressif по VID.

### [ ] B4.9 Безопасность P1 — S каждая
- `ai/tools/base.py:224-239`: аудит усекать (`content` → длина, `clipboard`/`read_file` —
  только метаданные), ротация по размеру, хвост через `seek`.
- `ai/tools/dev.py:60-65`: `blocked_commands` по границам слов; `run_command` даже в
  `full` спрашивать (или `allow_always` на сессию); по таймауту убивать дерево
  (`psutil.children(recursive=True)`).
- `ai/tools/system.py:121-151`: `kill_process` — защищённые имена проверять для каждого
  кандидата, точное совпадение первым (сейчас `target="csrss"` попадает в `csrss.exe`).
- `press_keys` с `win`/`enter`/`alt+f4` и запись в буфер → danger; чтение буфера → caution.
- `ai/stt.py:126`: ключ LLM не подставлять в чужой `stt_base_url`.
- `core/mcp_client.py:142`: минимальный env для MCP вместо всего `os.environ`.
- `core/settings.py:112`: маска ключа не должна раскрывать 8 символов; `main.py:363`
  ValidationError → 400, а не 500 с трейсбеком.
- `remember`: блок памяти в промпте помечать как данные; новые записи показывать в панели
  с кнопкой удаления.

### [ ] B4.10 Мелочи — S
`allow_always` с ключом (tool, аргументы) и TTL; авто-deny повторного вызова после отказа
в рамках задачи; `SettingsPayload` (`main.py:245-273`) генерировать из
`Settings.model_fields`; `add_step` не публиковать всю задачу на каждый шаг; удалить
мёртвый код (`agent.py:276-305`, `stt.py:171-175`, алиасы `BACKEND_DIR`);
`settings.example.json` обновить (убрать `автом` из wake_words — ловит «автоматически»);
`prompts.yaml` через `paths.seeded`, чтобы характер можно было править в сборке.

---

## Этап W5 — Панель: надёжность и онбординг (P1/P2, 3 дня)

### [ ] W5.1 Ошибки не роняют SPA — S
`web/src/api.ts`: общий `apiFetch()` (base URL, `res.ok`, JSON, таймаут). `ErrorBoundary`
в `main.tsx`. `SettingsPage.tsx:66-113`: состояние ошибки с «Повторить» (сейчас при 422
белый экран, при недоступном сервере — вечный лоадер). `RulesPage.tsx:43-64`: при
неудачной загрузке блокировать сохранение (иначе перезапись `rules.yaml` пустым списком).
`ToolsPage.tsx:87-157`: try/catch, `busy`, показывать 404 от toggle MCP.

### [ ] W5.2 Соединение — S
`web/src/store/useAppStore.ts:170-340`: в `onopen` запрашивать `GET /api/tasks` и
восстанавливать `approvals` (сейчас теряются при F5); в `onclose` сбрасывать
`agentStatus`, `voice`, `approvals`; backoff 1→15 с с джиттером и guard `socket !== ws`;
ping каждые 25 с, закрывать без pong; реконнект при `visibilitychange`. Явный игнор-лист
(`agent_step`, `beep`, `stop_audio`, `set_rotation`); `reminders_update` → стор.

### [ ] W5.3 Адрес API — S
`web/src/config.ts:3-7`: в проде `window.location.origin`; сейчас `ATOM_PORT` в трее
ломает панель.

### [ ] W5.4 Ресурсы офлайн — S
`esp-web-tools` из npm вместо unpkg (`web/index.html:14`; без сети в Chrome показывается
«Нужен Chrome или Edge»); шрифты self-host; `favicon` (`/vite.svg` → 404), `lang="ru"`,
`title`. Удалить устаревший `web/firmware/`.

### [ ] W5.5 Микрофон ПК — S
`web/src/components/PCMicTester.tsx:16-87`: не звать `getUserMedia` при монтировании
(первое, что видит новый пользователь — запрос доступа к микрофону); `track.stop()` после
`enumerateDevices`; cleanup при unmount; `AudioWorklet`. `MicStreamPlayer`: убрать
`console.log` на чанк, ограничить накопленную задержку, `close()`.

### [ ] W5.6 Онбординг — M
Карточка-чеклист на Dashboard, пока `!health.has_key || !device.connected ||
allowed_roots.length === 0`: ключ → устройство → каталоги. `VoiceBar` — честное состояние
(«Нет микрофона» с переходом на Прошивку). `petName` из настроек вместо «Патрик» в
десяти местах. Чип «нет связи» → «проверьте значок Патрика в трее». Русифицировать
`DebugPage`, `MicStreamPlayer`, `PCMicTester`.

### [ ] W5.7 Карточка «Устройство» — M (пара с fw F2.9)
`POST /api/device/command {action, ...}` с whitelist `DEVICE_ACTIONS`. UI: громкость,
яркость/авто, микрофон, «Найти питомца», экран, автоповорот, перезагрузка. `rotation` и
`autorotate` брать из `device_status` (сейчас счётчик в localStorage расходится с NVS, а
автоповорот выключается навсегда). В `DeviceHealth` показать `mic`, `volume`,
`drop_in/out`, `queued_ms`, `frame_ms`.

### [ ] W5.8 InstallPage — S
Слать `pet_name`, `ota_pass` (`InstallPage.tsx:135-139`); `lan_ip` из `/api/health` для
предзаполнения IP сервера; баннер «прошивка работает в Chrome/Edge и только по адресу
http://127.0.0.1:8000»; продлевать `pause_reconnect` на каждый `state-changed`
(`EspWebInstallButton.tsx:29-36`, 60 с меньше времени прошивки); пароль Wi-Fi не хранить
в localStorage.

### [ ] W5.9 Чат и подтверждения — S/M
Markdown, Shift+Enter, потоковые «мысли» из `agent_step`; `ApprovalDock` с обратным
отсчётом, бейдж в `document.title`, `Notification`. MCP: токенизатор аргументов с кавычками
(`ToolsPage.tsx:121` рвёт пути с пробелами) и поля `env`/`cwd`. Слайдеры через
`onPointerUp` + debounce; wake-words — локальная строка, парсинг на blur.

### [ ] W5.10 Тесты — S
Вынести `handleMessage(data)` из `connectWebSocket`, табличные тесты редьюсеров; тесты
на состояние ошибки Settings и guard в Rules. `package.json`: скрипты `test`, `typecheck`.

---

## Этап 6 — Фичи (backlog)

- **Push-to-talk — L.** `RegisterHotKey` в потоке с собственным циклом сообщений; захват
  микрофона ПК через `sounddevice` → `voice_pipeline.feed()`; на нажатии
  `open_conversation()` без wake-word. Сейчас звук в бэкенд приходит только с устройства
  или из браузера.
- **Мини-окно чата у трея — L.** Дёшево: `msedge --app=http://127.0.0.1:8000/#/mini
  --window-size=420,640`. Полноценно: pywebview в отдельном процессе `AtomPet.exe --panel`,
  позиционирование через `Shell_NotifyIconGetRect`.
- ~~**Автообновление — M–L.**~~ Сделано: `core/updater.py` раз в сутки смотрит последний
  релиз на GitHub (или свой `latest.json` через настройку `update_url`), качает setup.exe с
  проверкой sha256 и ставит его `/SILENT`; приложение закрывается само через quit-handler
  трея, установщик возвращает его обратно (`Check: WizardSilent`). Выпуск — `packaging/release.ps1`.
  Осталось: без подписи кода каждое обновление упирается в SmartScreen.
- **История задач в SQLite — M.** Поиск, экспорт, метрики токенов из `usage_metadata`.
- **Матрица автономии по инструментам — M.** Вместо трёх глобальных уровней.
- **Кэш TTS для частых фраз, выбор голоса и скорости SAPI — S.**
- **faster-whisper как третий STT-движок — M.**
- **Правила-наблюдатели — M.** File watcher над `allowed_roots`, повторяющиеся напоминания.
- **Загрузка модели Vosk из панели — M.** С прогрессом через WS, выбор small/big.

## Риски

- A0.2 ломает сценарий «панель с другого ПК по LAN». Это осознанно; задокументировать в README.
- Job Object (T1.3): проверить, что PyInstaller onedir не порождает промежуточный процесс.
- `windows-toasts` требует AUMID и ярлыка: в portable-zip кнопки в тостах не работают,
  fallback обязателен.
- P2.1: перед удалением зависимостей grep импортов (`langchain_openai` используется).
- Python 3.14 свежий, часть колёс не собирается; держать 3.12/3.13 запасным вариантом для сборки.

## Что не делаем и почему

- Не переписываем панель на Electron/Tauri: pystray плюс браузер (или `--app` окно Edge)
  покрывает потребность, сборка остаётся Python-only.
- Не делаем onefile: модель Vosk и зависимости — сотни мегабайт, распаковка при каждом старте.
- Не упаковываем Node.js: остаётся системной зависимостью, трей предупреждает.
- Не вводим логин с паролем: достаточно loopback-only для управления и токена для устройства.
