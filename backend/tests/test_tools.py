"""Тесты реестра инструментов: валидация, песочница файлов, подтверждения."""

import pytest
from pydantic import BaseModel, Field

from ai.tools.base import ToolRegistry, ToolSpec
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
