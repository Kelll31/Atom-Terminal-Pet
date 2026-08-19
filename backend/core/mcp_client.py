"""Менеджер MCP-серверов.

Каждый сервер живёт в собственной asyncio-задаче: там же открыт stdio-транспорт
и сессия MCP. Вызовы инструментов приходят в очередь этой задачи и выполняются
внутри неё — так мы не тащим anyio cancel scope между задачами (частая причина
зависаний и «Attempted to exit cancel scope in a different task»).

Инструменты серверов регистрируются в общем реестре (ai.tools.registry),
поэтому агент не различает локальные и удалённые инструменты.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass, field
from typing import Any

import yaml
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from ai.tools.base import ToolSpec, registry

logger = logging.getLogger("core.mcp_client")

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BACKEND_DIR, "config", "mcp_servers.yaml")

CALL_TIMEOUT = 90.0
START_TIMEOUT = 45.0


@dataclass
class ServerState:
    name: str
    config: dict[str, Any]
    status: str = "stopped"  # stopped | starting | ready | error | disabled
    error: str = ""
    tools: list[str] = field(default_factory=list)
    task: asyncio.Task | None = None
    queue: asyncio.Queue | None = None
    stop_event: asyncio.Event | None = None

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": self.config.get("command", ""),
            "args": self.config.get("args", []),
            "enabled": self.config.get("enabled", True),
            "description": self.config.get("description", ""),
            "status": self.status,
            "error": self.error,
            "tools": self.tools,
        }


class MCPManager:
    def __init__(self, config_path: str = CONFIG_PATH):
        self.config_path = config_path
        self.servers: dict[str, ServerState] = {}

    # ── конфигурация ───────────────────────────────────────────────────────
    def load_config(self) -> dict[str, dict[str, Any]]:
        if not os.path.exists(self.config_path):
            logger.warning(f"Файл MCP-серверов не найден: {self.config_path}")
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("mcpServers", {}) or {}
        except Exception as e:
            logger.error(f"Не удалось прочитать конфигурацию MCP: {e}")
            return {}

    def save_config(self) -> None:
        data = {"mcpServers": {name: st.config for name, st in self.servers.items()}}
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    # ── жизненный цикл ─────────────────────────────────────────────────────
    async def initialize(self) -> None:
        from core.settings import settings_store

        configs = self.load_config()
        for name, cfg in configs.items():
            self.servers[name] = ServerState(name=name, config=cfg)

        if not settings_store.get("mcp_enabled", True):
            for state in self.servers.values():
                state.status = "disabled"
            logger.info("MCP отключён в настройках.")
            return

        await asyncio.gather(
            *(self.start_server(name) for name in list(self.servers)),
            return_exceptions=True,
        )
        ready = [s.name for s in self.servers.values() if s.status == "ready"]
        logger.info(
            f"MCP: запущено серверов {len(ready)}/{len(self.servers)}; "
            f"инструментов подключено: {sum(len(s.tools) for s in self.servers.values())}"
        )

    async def start_server(self, name: str) -> bool:
        state = self.servers.get(name)
        if state is None:
            return False
        if not state.config.get("enabled", True):
            state.status = "disabled"
            return False
        if state.task and not state.task.done():
            return state.status == "ready"

        command = state.config.get("command")
        if not command:
            state.status = "error"
            state.error = "не указана команда запуска"
            return False

        # На Windows npx/node — это .cmd-обёртки, которые не запускаются без shell.
        resolved = shutil.which(command) or command
        state.config.setdefault("args", [])

        state.status = "starting"
        state.error = ""
        state.queue = asyncio.Queue()
        state.stop_event = asyncio.Event()
        ready_event = asyncio.Event()

        params = StdioServerParameters(
            command=resolved,
            args=list(state.config.get("args", [])),
            env={**os.environ, **(state.config.get("env") or {})},
            cwd=state.config.get("cwd") or BACKEND_DIR,
        )

        state.task = asyncio.create_task(
            self._server_worker(state, params, ready_event), name=f"mcp:{name}"
        )
        try:
            await asyncio.wait_for(ready_event.wait(), timeout=START_TIMEOUT)
        except asyncio.TimeoutError:
            state.status = "error"
            state.error = f"сервер не ответил за {START_TIMEOUT:.0f} с"
            logger.error(f"MCP '{name}': {state.error}")
            await self.stop_server(name)
            return False

        return state.status == "ready"

    async def _server_worker(
        self, state: ServerState, params: StdioServerParameters, ready: asyncio.Event
    ) -> None:
        try:
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    await self._register_tools(state, session)
                    state.status = "ready"
                    ready.set()
                    logger.info(f"MCP '{state.name}' готов, инструментов: {len(state.tools)}")

                    while not state.stop_event.is_set():
                        get_request = asyncio.create_task(state.queue.get())
                        wait_stop = asyncio.create_task(state.stop_event.wait())
                        done, pending = await asyncio.wait(
                            {get_request, wait_stop}, return_when=asyncio.FIRST_COMPLETED
                        )
                        for task in pending:
                            task.cancel()
                        if get_request not in done:
                            break

                        tool_name, arguments, future = get_request.result()
                        if future.cancelled():
                            continue
                        try:
                            result = await asyncio.wait_for(
                                session.call_tool(tool_name, arguments=arguments),
                                timeout=CALL_TIMEOUT,
                            )
                            future.set_result(self._format_result(result))
                        except Exception as e:  # noqa: BLE001
                            if not future.done():
                                future.set_exception(e)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            state.status = "error"
            state.error = str(e)
            logger.error(f"MCP '{state.name}' упал: {e}")
        finally:
            registry.unregister_source(f"mcp:{state.name}")
            state.tools = []
            if state.status not in ("error", "disabled"):
                state.status = "stopped"
            ready.set()

    async def stop_server(self, name: str) -> None:
        state = self.servers.get(name)
        if not state:
            return
        if state.stop_event:
            state.stop_event.set()
        if state.task and not state.task.done():
            state.task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(state.task), timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            except Exception as e:  # noqa: BLE001 — сервер мог упасть при закрытии
                logger.debug(f"MCP '{name}' завершился с ошибкой: {e}")
        registry.unregister_source(f"mcp:{name}")
        state.tools = []
        state.task = None
        if state.status != "error":
            state.status = "disabled" if not state.config.get("enabled", True) else "stopped"

    async def restart_server(self, name: str) -> bool:
        await self.stop_server(name)
        return await self.start_server(name)

    async def cleanup(self) -> None:
        await asyncio.gather(
            *(self.stop_server(name) for name in list(self.servers)), return_exceptions=True
        )

    # ── управление списком серверов ────────────────────────────────────────
    async def upsert_server(self, name: str, config: dict[str, Any]) -> dict[str, Any]:
        config.setdefault("enabled", True)
        if name in self.servers:
            await self.stop_server(name)
            self.servers[name].config = config
        else:
            self.servers[name] = ServerState(name=name, config=config)
        self.save_config()
        await self.start_server(name)
        return self.servers[name].info()

    async def remove_server(self, name: str) -> bool:
        if name not in self.servers:
            return False
        await self.stop_server(name)
        del self.servers[name]
        self.save_config()
        return True

    async def set_enabled(self, name: str, enabled: bool) -> bool:
        state = self.servers.get(name)
        if not state:
            return False
        state.config["enabled"] = enabled
        self.save_config()
        if enabled:
            return await self.start_server(name)
        await self.stop_server(name)
        return True

    def status(self) -> list[dict[str, Any]]:
        return [state.info() for state in self.servers.values()]

    # ── инструменты ────────────────────────────────────────────────────────
    async def _register_tools(self, state: ServerState, session: ClientSession) -> None:
        try:
            response = await asyncio.wait_for(session.list_tools(), timeout=30)
        except Exception as e:  # noqa: BLE001
            state.error = f"не удалось получить список инструментов: {e}"
            logger.error(f"MCP '{state.name}': {state.error}")
            return

        source = f"mcp:{state.name}"
        registry.unregister_source(source)
        state.tools = []

        for tool in response.tools:
            schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {}
            if hasattr(schema, "model_dump"):
                schema = schema.model_dump()
            if not isinstance(schema, dict):
                schema = {"type": "object", "properties": {}}

            risk = self._risk_from_annotations(tool)
            tool_name = f"{state.name}__{tool.name}" if self._name_conflicts(tool.name) else tool.name

            registry.register(
                ToolSpec(
                    name=tool_name,
                    description=f"[{state.name}] {tool.description or tool.name}",
                    func=self._make_caller(state, tool.name),
                    json_schema=schema,
                    risk=risk,
                    category="mcp",
                    source=source,
                )
            )
            state.tools.append(tool_name)

    @staticmethod
    def _name_conflicts(name: str) -> bool:
        return registry.get(name) is not None

    @staticmethod
    def _risk_from_annotations(tool: Any) -> str:
        ann = getattr(tool, "annotations", None)
        if ann is not None:
            if getattr(ann, "read_only_hint", None) or getattr(ann, "readOnlyHint", None):
                return "safe"
            if getattr(ann, "destructive_hint", None) or getattr(ann, "destructiveHint", None):
                return "danger"
        return "caution"

    def _make_caller(self, state: ServerState, remote_name: str):
        async def call(**kwargs: Any) -> str:
            if state.status != "ready" or state.queue is None:
                raise RuntimeError(f"MCP-сервер '{state.name}' сейчас недоступен ({state.status}).")
            future: asyncio.Future = asyncio.get_running_loop().create_future()
            await state.queue.put((remote_name, kwargs, future))
            return await asyncio.wait_for(future, timeout=CALL_TIMEOUT + 10)

        return call

    @staticmethod
    def _format_result(result: Any) -> str:
        is_error = getattr(result, "is_error", None)
        if is_error is None:
            is_error = getattr(result, "isError", False)

        blocks = getattr(result, "content", None) or []
        texts: list[str] = []
        for block in blocks:
            text = getattr(block, "text", None)
            if text:
                texts.append(text)
            elif getattr(block, "type", "") == "image":
                texts.append("[изображение получено, но модель его не видит]")

        if not texts:
            structured = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
            if structured:
                import json

                texts.append(json.dumps(structured, ensure_ascii=False, default=str))

        output = "\n".join(texts) or "(пустой ответ инструмента)"
        return f"Ошибка инструмента: {output}" if is_error else output


mcp_manager = MCPManager()
