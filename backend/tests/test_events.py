"""Тесты шины событий: подготовка текста к озвучке и маршрутизация к устройству.

Главное, что здесь проверяется, — разделение адресатов. Панель и питомец
получают РАЗНЫЕ данные: панели уходит всё и как есть, устройству — только
команды из DEVICE_ACTIONS и только после _device_message (транслитерация плюс
обрезка). Транспорт при этом не должен ни на что влиять: по Wi-Fi через
manager.send_to_device и по USB через serial_manager должно уходить одно и то же.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events import DEVICE_ACTIONS, EventBus, sanitize_for_speech


def fake_manager(*, on_wifi: bool) -> MagicMock:
    """Заглушка ConnectionManager с честными асинхронными методами.

    Голый MagicMock тут не годится: шина делает `await manager.send_to_device(...)`,
    а результат обычного MagicMock ожидать нельзя — тест падал бы на TypeError
    вместо проверки маршрутизации.

    Возвращаемые значения повторяют контракт настоящего менеджера: адресные
    методы отвечают False, когда питомца на WebSocket нет, и шина по этому
    признаку уходит на USB.
    """
    manager = MagicMock()
    manager.device_on_wifi = on_wifi
    manager.broadcast_json = AsyncMock()
    manager.broadcast_binary = AsyncMock()
    manager.send_to_device = AsyncMock(return_value=on_wifi)
    manager.send_binary_to_device = AsyncMock(return_value=on_wifi)
    return manager


def install_bus(monkeypatch, *, on_wifi: bool) -> tuple[EventBus, MagicMock, MagicMock]:
    """Шина с подменёнными транспортами. Возвращает (шина, менеджер, serial).

    Кабель считаем воткнутым всегда: так каждый тест проверяет именно выбор
    маршрута, а не то, что USB «случайно» оказался недоступен.
    """
    manager = fake_manager(on_wifi=on_wifi)
    serial = MagicMock(is_connected=True)
    monkeypatch.setattr("core.events.manager", manager)
    monkeypatch.setattr("core.events.serial_manager", serial)
    return EventBus(), manager, serial


def set_audio_output(monkeypatch, value: str) -> None:
    """Меняет настройку вывода звука только на время теста."""
    from core.settings import settings_store

    monkeypatch.setattr(settings_store.current, "audio_output", value)


def silence_pc_speaker(monkeypatch) -> AsyncMock:
    """Глушит колонки ПК: тесту не нужен реальный звук на машине разработчика."""
    player = AsyncMock(return_value=True)
    monkeypatch.setattr("ai.tts.play_on_pc", player)
    return player


# ── Подготовка текста ──────────────────────────────────────────────────────
def test_sanitize_removes_markdown_and_links():
    text = "**Готово!** Смотри https://example.com/very/long/path и файл D:/projects/app/main.py"
    clean = sanitize_for_speech(text)

    assert "**" not in clean
    assert "https" not in clean
    assert "ссылка" in clean
    assert "путь" in clean


def test_sanitize_replaces_code_block():
    clean = sanitize_for_speech("Вот код:\n```python\nprint(1)\n```\nвсё")
    assert "print" not in clean
    assert "фрагмент кода" in clean


def test_sanitize_collapses_whitespace_and_emoji():
    assert sanitize_for_speech("Привет   🚀\n\nмир") == "Привет мир"


def test_device_actions_cover_firmware_commands_only():
    """Служебные события агента не должны засорять канал устройства."""
    assert {"speak", "set_emotion", "update_pc", "stop_audio"} <= DEVICE_ACTIONS
    assert "agent_step" not in DEVICE_ACTIONS
    assert "task_update" not in DEVICE_ACTIONS
    assert "tasks_snapshot" not in DEVICE_ACTIONS
    assert "approval_request" not in DEVICE_ACTIONS


# ── Маршрутизация команд ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_wifi_command_goes_through_send_to_device_transliterated(monkeypatch):
    """По Wi-Fi команда уходит адресно и в «узком» виде, а не как есть.

    Раньше по Wi-Fi питомец получал сообщение панели целиком: кириллицу, которую
    встроенный шрифт рисует мусором, и текст любой длины, не влезающий в буфер
    команды прошивки.
    """
    bus, manager, serial = install_bus(monkeypatch, on_wifi=True)
    long_text = "Привет! " * 20

    await bus.emit("speak", emotion="happy", text=long_text)

    manager.send_to_device.assert_awaited_once()
    sent = manager.send_to_device.await_args.args[0]
    assert sent["action"] == "speak"
    assert sent["emotion"] == "happy"
    assert sent["text"].startswith("Privet!")
    assert "П" not in sent["text"] and "р" not in sent["text"]
    assert len(sent["text"]) <= 64

    # По USB то же самое дублировать не надо — питомец уже получил команду
    serial.send_json.assert_not_called()

    # А панель получает исходный текст целиком: у неё UTF-8 и нет лимита
    panel = manager.broadcast_json.await_args.args[0]
    assert panel["text"] == long_text


@pytest.mark.asyncio
async def test_usb_command_gets_exactly_the_same_transform(monkeypatch):
    """Переработка сообщения общая для обоих транспортов, а не только для USB."""
    bus, manager, serial = install_bus(monkeypatch, on_wifi=False)
    long_text = "Привет! " * 20

    await bus.emit("speak", emotion="happy", text=long_text)

    manager.send_to_device.assert_not_awaited()
    serial.send_json.assert_called_once()
    sent = serial.send_json.call_args.args[0]
    assert sent["action"] == "speak"
    assert sent["text"].startswith("Privet!")
    assert len(sent["text"]) <= 64


@pytest.mark.asyncio
async def test_wifi_failure_falls_back_to_usb(monkeypatch):
    """Сокет питомца отвалился между проверкой и отправкой — спасает кабель."""
    bus, manager, serial = install_bus(monkeypatch, on_wifi=True)
    manager.send_to_device.return_value = False

    await bus.emit("set_emotion", emotion="happy")

    manager.send_to_device.assert_awaited_once()
    serial.send_json.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("on_wifi", [True, False])
@pytest.mark.parametrize(
    "action, payload",
    [
        ("task_update", {"task": {"id": "1", "status": "running"}}),
        ("tasks_snapshot", {"tasks": [{"id": "1"}] * 50}),
        ("agent_step", {"step": {}}),
        ("approval_request", {"id": "1"}),
    ],
)
async def test_panel_only_events_never_reach_device(monkeypatch, action, payload, on_wifi):
    """Снимок задач и лог агента в буфер команды не влезают и рвут WebSocket 1009."""
    bus, manager, serial = install_bus(monkeypatch, on_wifi=on_wifi)

    await bus.emit(action, **payload)

    manager.broadcast_json.assert_awaited_once()
    manager.send_to_device.assert_not_awaited()
    serial.send_json.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("on_wifi", [True, False])
async def test_device_volume_becomes_set_volume_on_the_wire(monkeypatch, on_wifi):
    """Наружу device_volume (чтобы не путать с громкостью ПК), на провод — set_volume."""
    bus, manager, serial = install_bus(monkeypatch, on_wifi=on_wifi)

    await bus.emit("device_volume", value=70)

    if on_wifi:
        sent = manager.send_to_device.await_args.args[0]
    else:
        sent = serial.send_json.call_args.args[0]
    assert sent == {"action": "set_volume", "value": 70}

    # В панели действие остаётся с исходным именем
    assert manager.broadcast_json.await_args.args[0]["action"] == "device_volume"


@pytest.mark.asyncio
async def test_emit_raw_uses_the_same_routing(monkeypatch):
    """pc_monitor шлёт готовый словарь — маршрут обязан быть тем же, что у emit."""
    bus, manager, serial = install_bus(monkeypatch, on_wifi=True)

    await bus.emit_raw({"action": "update_pc", "cpu": 42})

    manager.send_to_device.assert_awaited_once_with({"action": "update_pc", "cpu": 42})
    serial.send_json.assert_not_called()


# ── Локальные подписчики (трей) ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_subscribe_receives_events_and_unsubscribe_stops_them(monkeypatch):
    bus, _manager, _serial = install_bus(monkeypatch, on_wifi=True)
    seen: list[dict] = []

    unsubscribe = bus.subscribe(seen.append)
    await bus.emit("agent_status", state="thinking")
    assert seen == [{"action": "agent_status", "state": "thinking"}]

    unsubscribe()
    await bus.emit("agent_status", state="idle")
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_broken_listener_does_not_break_delivery(monkeypatch):
    """Упавший трей не должен обрывать рассылку остальным адресатам."""
    bus, manager, _serial = install_bus(monkeypatch, on_wifi=True)
    seen: list[dict] = []

    def explode(_message: dict) -> None:
        raise RuntimeError("трей упал")

    bus.subscribe(explode)
    bus.subscribe(seen.append)

    await bus.emit("set_emotion", emotion="happy")

    assert len(seen) == 1
    manager.broadcast_json.assert_awaited_once()
    manager.send_to_device.assert_awaited_once()


# ── Речь и прерывание ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_interrupt_stops_current_speech_but_not_the_next_one(monkeypatch):
    """Прерывание глушит текущую реплику и не должно затыкать питомца навсегда."""
    bus, _manager, _serial = install_bus(monkeypatch, on_wifi=True)
    speech = bus.begin_speech()

    await bus.cancel_speech()
    assert not bus._is_current(speech)  # прошлая реплика больше не актуальна

    # Новая реплика снова считается текущей — питомец не онемел
    next_speech = bus.begin_speech()
    assert bus._is_current(next_speech)


@pytest.mark.asyncio
async def test_send_audio_stops_when_speech_is_superseded(monkeypatch):
    bus, manager, _serial = install_bus(monkeypatch, on_wifi=True)
    speech = bus.begin_speech()
    bus.begin_speech()  # пришла новая реплика — старая устарела

    await bus.send_audio(b"\x00\x01" * 8192, speech)
    manager.broadcast_binary.assert_not_called()
    manager.send_binary_to_device.assert_not_awaited()


# ── Гейт аудио по настройке вывода ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_audio_reaches_device_over_wifi(monkeypatch):
    """Регресс: после разделения панелей и устройства звук по Wi-Fi пропадал."""
    monkeypatch.setattr("core.events.AUDIO_CHUNK_DELAY", 0)
    set_audio_output(monkeypatch, "device")
    bus, manager, serial = install_bus(monkeypatch, on_wifi=True)

    pcm = b"\x01\x02" * 512
    await bus.send_audio(pcm)

    manager.send_binary_to_device.assert_awaited_once_with(pcm)
    manager.broadcast_binary.assert_awaited_once_with(pcm)
    serial.send_binary.assert_not_called()


@pytest.mark.asyncio
async def test_audio_reaches_device_over_usb_when_no_wifi(monkeypatch):
    monkeypatch.setattr("core.events.AUDIO_CHUNK_DELAY", 0)
    set_audio_output(monkeypatch, "device")
    bus, manager, serial = install_bus(monkeypatch, on_wifi=False)

    pcm = b"\x01\x02" * 512
    await bus.send_audio(pcm)

    serial.send_binary.assert_called_once_with(pcm)
    manager.broadcast_binary.assert_awaited_once_with(pcm)


@pytest.mark.asyncio
@pytest.mark.parametrize("on_wifi", [True, False])
async def test_audio_skips_device_when_output_is_pc_only(monkeypatch, on_wifi):
    """«Только колонки ПК» обязано работать на обоих транспортах.

    По USB гейт был всегда, а по Wi-Fi звук шёл общей рассылкой — и питомец
    говорил, хотя пользователь просил выводить голос только на компьютер.
    Панель при этом поток получать должна: там осциллограф, а не динамик.
    """
    monkeypatch.setattr("core.events.AUDIO_CHUNK_DELAY", 0)
    set_audio_output(monkeypatch, "pc")
    player = silence_pc_speaker(monkeypatch)
    bus, manager, serial = install_bus(monkeypatch, on_wifi=on_wifi)

    pcm = b"\x01\x02" * 512
    await bus.send_audio(pcm)

    manager.broadcast_binary.assert_awaited_once_with(pcm)
    manager.send_binary_to_device.assert_not_awaited()
    serial.send_binary.assert_not_called()
    player.assert_awaited_once()


@pytest.mark.asyncio
async def test_audio_goes_everywhere_in_both_mode(monkeypatch):
    monkeypatch.setattr("core.events.AUDIO_CHUNK_DELAY", 0)
    set_audio_output(monkeypatch, "both")
    player = silence_pc_speaker(monkeypatch)
    bus, manager, _serial = install_bus(monkeypatch, on_wifi=True)

    pcm = b"\x01\x02" * 512
    await bus.send_audio(pcm)

    manager.broadcast_binary.assert_awaited_once_with(pcm)
    manager.send_binary_to_device.assert_awaited_once_with(pcm)
    player.assert_awaited_once()
