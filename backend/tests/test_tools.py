"""Тесты реестра инструментов: валидация, песочница файлов, подтверждения,
а также защиты, ради которых инструменты переписывались: запуск без оболочки,
защищённые процессы, усечение журнала аудита и исполнение вне цикла событий."""

import asyncio
import json
import threading
import time

import psutil
import pytest
from pydantic import BaseModel, Field

from ai.tools.base import AUDIT_LOG, ToolRegistry, ToolSpec
from ai.tools.files import resolve_path
from ai.tools.base import ToolError
from core.settings import settings_store


class EchoArgs(BaseModel):
    text: str = Field(..., description="что вернуть")


def build_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            name="echo",
            description="Возвращает текст",
            func=lambda text: f"echo: {text}",
            args_model=EchoArgs,
            risk="safe",
        )
    )
    reg.register(
        ToolSpec(
            name="wipe",
            description="Опасное действие",
            func=lambda: "стёрто",
            risk="danger",
        )
    )
    return reg


class FakeContext:
    def __init__(self, approve: bool):
        self.task_id = "test"
        self.approve = approve
        self.requests: list[str] = []

    async def request_approval(self, tool, args, risk, description):
        self.requests.append(tool)
        return self.approve

    async def emit(self, action, **payload):
        pass


async def test_execute_validates_arguments():
    reg = build_registry()
    ok, result = await reg.execute("echo", {"wrong": 1})
    assert ok is False
    assert "Некорректные аргументы" in result


async def test_execute_runs_safe_tool_without_approval():
    reg = build_registry()
    ctx = FakeContext(approve=False)
    ok, result = await reg.execute("echo", {"text": "привет"}, ctx=ctx, autonomy="auto_safe")
    assert ok is True
    assert result == "echo: привет"
    assert ctx.requests == []


async def test_dangerous_tool_requires_approval():
    reg = build_registry()
    denied = FakeContext(approve=False)
    ok, result = await reg.execute("wipe", {}, ctx=denied, autonomy="auto_safe")
    assert ok is False
    assert "отклонил" in result
    assert denied.requests == ["wipe"]

    allowed = FakeContext(approve=True)
    ok, result = await reg.execute("wipe", {}, ctx=allowed, autonomy="auto_safe")
    assert ok is True
    assert result == "стёрто"


async def test_full_autonomy_skips_approval():
    reg = build_registry()
    ctx = FakeContext(approve=False)
    ok, _ = await reg.execute("wipe", {}, ctx=ctx, autonomy="full")
    assert ok is True
    assert ctx.requests == []


async def test_ask_mode_confirms_caution_tools():
    reg = build_registry()
    reg.register(
        ToolSpec(name="risky", description="Осторожно", func=lambda: "ok", risk="caution")
    )
    ctx = FakeContext(approve=False)
    ok, _ = await reg.execute("risky", {}, ctx=ctx, autonomy="ask")
    assert ok is False
    assert ctx.requests == ["risky"]


async def test_unknown_tool_reports_available_tools():
    reg = build_registry()
    ok, result = await reg.execute("nope", {})
    assert ok is False
    assert "echo" in result


async def test_disabled_tool_is_not_executed():
    reg = build_registry()
    ok, result = await reg.execute("echo", {"text": "hi"}, disabled=["echo"])
    assert ok is False
    assert "отключён" in result


def test_files_sandbox_blocks_paths_outside_roots(tmp_path, monkeypatch):
    allowed = tmp_path / "workspace"
    allowed.mkdir()
    (allowed / "file.txt").write_text("hello", encoding="utf-8")

    monkeypatch.setattr(settings_store.current, "allowed_roots", [str(allowed)])

    assert resolve_path(str(allowed / "file.txt")).name == "file.txt"

    with pytest.raises(ToolError):
        resolve_path(str(tmp_path / "secret.txt"), must_exist=False)


def test_tool_schema_is_openai_shaped():
    reg = build_registry()
    schema = reg.get("echo").schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "echo"
    assert "text" in schema["function"]["parameters"]["properties"]


# ── A0.3: инструменты уровня safe не должны попадать в оболочку ─────────────
class FakeProcess:
    """Минимальный дублёр asyncio.subprocess.Process."""

    def __init__(self, output: bytes = b"diff") -> None:
        self.pid = 4242
        self.returncode = 0
        self._output = output
        self.killed = False

    async def communicate(self):
        return self._output, None

    def kill(self):
        self.killed = True

    async def wait(self):
        return 0


@pytest.fixture
def no_shell(monkeypatch):
    """Подменяет запуск процессов: exec записывается, shell запрещён вовсе."""
    calls: list[list[str]] = []

    async def fake_exec(*argv, **kwargs):
        calls.append(list(argv))
        assert kwargs.get("stdin") is not None, "подпроцессу не закрыли stdin"
        assert "creationflags" in kwargs, "не передан creationflags (окно консоли)"
        return FakeProcess()

    async def fake_shell(cmd, **kwargs):  # pragma: no cover — обязан не вызываться
        raise AssertionError(f"инструмент уровня safe ушёл в оболочку: {cmd!r}")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", fake_shell)
    return calls


async def test_git_diff_does_not_execute_injected_path(tmp_path, monkeypatch, no_shell):
    """Враждебный path не должен ни склеиваться с командой, ни что-то запускать."""
    from ai.tools.dev import git_diff

    monkeypatch.setattr(settings_store.current, "allowed_roots", [str(tmp_path)])
    hostile = '." & calc & echo "'

    await git_diff(str(tmp_path), path=hostile)

    assert len(no_shell) == 1
    argv = no_shell[0]
    # Путь — отдельный элемент списка, целиком, без кавычек и склейки.
    assert argv[0] == "git"
    assert argv[-1] == hostile
    assert argv[-2] == "--"
    assert not any("calc" in part for part in argv[:-1])


async def test_git_status_runs_without_shell(tmp_path, monkeypatch, no_shell):
    from ai.tools.dev import git_status

    monkeypatch.setattr(settings_store.current, "allowed_roots", [str(tmp_path)])
    (tmp_path / ".git").mkdir()

    await git_status(str(tmp_path))

    assert [argv[:2] for argv in no_shell] == [["git", "rev-parse"], ["git", "status"], ["git", "log"]]


def test_open_program_with_arguments_is_danger():
    from ai.tools import registry as real_registry

    spec = real_registry.get("open_program")
    assert spec.effective_risk({"target": "notepad", "args": ""}) == "caution"
    assert spec.effective_risk({"target": "powershell", "args": "-enc ZQBjAGgAbwA="}) == "danger"
    # В «разумном балансе» запуск с аргументами обязан спросить подтверждение.
    assert real_registry.needs_approval(
        spec, "auto_safe", spec.effective_risk({"target": "cmd", "args": "/c whoami"})
    )


# ── B4.9: стоп-слова по границам слов ──────────────────────────────────────
@pytest.mark.parametrize(
    "command, expected",
    [
        ("format D: /q", "format"),
        ("shutdown /s /t 0", "shutdown"),
        ("cipher    /w c:\\temp", "cipher /w"),
        ("pytest -k test_formatter", None),
        ("npm run reformat", None),
        ("git log --grep=shutdowns", None),
    ],
)
def test_stop_words_match_whole_words(command, expected):
    from ai.tools.dev import find_stop_word

    assert find_stop_word(command) == expected


# ── B4.9: защищённые процессы ──────────────────────────────────────────────
class FakeProc:
    def __init__(self, pid: int, name: str) -> None:
        self.info = {"pid": pid, "name": name}
        self.terminated = False

    def terminate(self):
        self.terminated = True


def _fake_process_iter(monkeypatch, procs):
    monkeypatch.setattr(psutil, "process_iter", lambda *a, **kw: iter(procs))
    return procs


def test_kill_process_refuses_protected_substring(monkeypatch):
    """'csrss' — подстрока системного csrss.exe, синий экран по запросу модели."""
    from ai.tools.system import kill_process

    procs = _fake_process_iter(monkeypatch, [FakeProc(4, "csrss.exe"), FakeProc(700, "csrss.exe")])

    with pytest.raises(ToolError) as err:
        kill_process("csrss")

    assert "системные" in str(err.value)
    assert not any(p.terminated for p in procs)


def test_kill_process_prefers_exact_name(monkeypatch):
    from ai.tools.system import kill_process

    helper = FakeProc(11, "notepad_helper.exe")
    real = FakeProc(12, "notepad.exe")
    _fake_process_iter(monkeypatch, [helper, real])

    result = kill_process("notepad")

    assert "notepad.exe" in result
    assert real.terminated is True
    assert helper.terminated is False


def test_kill_process_skips_protected_among_candidates(monkeypatch):
    """Системный кандидат отсеивается, обычный с тем же корнем — завершается."""
    from ai.tools.system import kill_process

    system_proc = FakeProc(4, "csrss.exe")
    user_proc = FakeProc(900, "csrss_monitor.exe")
    _fake_process_iter(monkeypatch, [system_proc, user_proc])

    result = kill_process("csrss", all_matching=True)

    assert system_proc.terminated is False
    assert user_proc.terminated is True
    assert "csrss_monitor.exe" in result


def test_press_keys_and_clipboard_risk_escalates():
    from ai.tools import registry as real_registry

    keys = real_registry.get("press_keys")
    assert keys.effective_risk({"keys": "ctrl+s"}) == "caution"
    assert keys.effective_risk({"keys": "win+r"}) == "danger"
    assert keys.effective_risk({"keys": "alt+f4"}) == "danger"
    assert keys.effective_risk({"keys": "ENTER"}) == "danger"

    clip = real_registry.get("clipboard")
    assert clip.effective_risk({"text": ""}) == "caution"
    assert clip.effective_risk({"text": "shutdown /s"}) == "danger"


# ── B4.9: журнал аудита ────────────────────────────────────────────────────
def _last_audit_entry() -> dict:
    with open(AUDIT_LOG, "r", encoding="utf-8") as f:
        return json.loads(f.readlines()[-1])


class SaveArgs(BaseModel):
    path: str = Field(...)
    content: str = Field(...)


async def test_audit_does_not_store_file_content():
    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            name="save",
            description="пишет файл",
            func=lambda path, content: f"Записано {len(content)} символов в {path}.",
            args_model=SaveArgs,
        )
    )
    secret = "секрет-" * 800  # длинное «содержимое файла»

    ok, _ = await reg.execute("save", {"path": "C:/tmp/a.txt", "content": secret})
    assert ok is True

    entry = _last_audit_entry()
    line = json.dumps(entry, ensure_ascii=False)
    assert "секрет-секрет" not in line
    assert entry["args"]["content"] == f"<{len(secret)} символов>"
    assert entry["args"]["path"] == "C:/tmp/a.txt"  # цель остаётся читаемой


async def test_audit_hides_clipboard_payload():
    reg = ToolRegistry()
    reg.register(
        ToolSpec(name="clipboard", description="буфер", func=lambda: "пароль-из-буфера")
    )

    await reg.execute("clipboard", {})

    entry = _last_audit_entry()
    assert "пароль-из-буфера" not in json.dumps(entry, ensure_ascii=False)
    assert "символов" in entry["result"]


async def test_audit_truncates_long_result():
    reg = ToolRegistry()
    reg.register(ToolSpec(name="dump", description="много текста", func=lambda: "x" * 10_000))

    await reg.execute("dump", {})

    entry = _last_audit_entry()
    assert len(entry["result"]) < 400
    assert "обрезано" in entry["result"]


def test_audit_rotates_by_size(monkeypatch):
    from ai.tools import base as tools_base

    monkeypatch.setattr(tools_base, "AUDIT_MAX_BYTES", 200)
    with open(AUDIT_LOG, "w", encoding="utf-8") as f:
        f.write("x" * 500 + "\n")

    ToolRegistry._audit("probe", {}, "ok", "готово", 0.01)

    import os

    assert os.path.exists(f"{AUDIT_LOG}.1")
    with open(AUDIT_LOG, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1  # журнал начат заново
    assert json.loads(lines[0])["tool"] == "probe"


# ── B4.1: синхронные инструменты не держат цикл событий ────────────────────
async def test_sync_tool_runs_outside_event_loop():
    """Синхронная функция уходит в поток, цикл в это время продолжает крутиться."""
    main_thread = threading.get_ident()
    seen: dict[str, int] = {}

    def slow() -> str:
        seen["thread"] = threading.get_ident()
        time.sleep(0.25)
        return "готово"

    reg = ToolRegistry()
    reg.register(ToolSpec(name="slow", description="медленный", func=slow))

    ticks = 0

    async def heartbeat() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    beat = asyncio.create_task(heartbeat())
    ok, result = await reg.execute("slow", {})
    beat.cancel()

    assert (ok, result) == (True, "готово")
    assert seen["thread"] != main_thread, "инструмент выполнился в потоке цикла событий"
    assert ticks >= 5, f"цикл событий стоял: тиков всего {ticks}"


async def test_async_tool_is_awaited_in_loop():
    """Корутины по-прежнему исполняются в цикле — им нужен running loop."""

    async def probe() -> str:
        asyncio.get_running_loop()  # упало бы в отдельном потоке
        return "в цикле"

    reg = ToolRegistry()
    reg.register(ToolSpec(name="probe", description="корутина", func=probe))

    ok, result = await reg.execute("probe", {})
    assert (ok, result) == (True, "в цикле")


async def test_set_reminder_is_coroutine_tool():
    """Регресс B4.1: напоминание создаёт asyncio-задачу, значит не должно
    уезжать в поток без цикла событий."""
    import inspect

    from ai.tools import registry as real_registry

    for name in ("set_reminder", "cancel_reminder"):
        assert inspect.iscoroutinefunction(real_registry.get(name).func), name
