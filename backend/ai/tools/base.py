"""Реестр инструментов Атома.

Каждый инструмент описывается ToolSpec: имя, описание, pydantic-схема аргументов,
уровень риска и категория. Реестр умеет:
  * отдавать схемы в формате OpenAI (для bind_tools у любой LLM),
  * исполнять инструмент по имени с валидацией аргументов,
  * пропускать вызов через ExecutionContext (подтверждения + журнал).

Инструменты MCP-серверов регистрируются здесь же (source="mcp:<server>"),
поэтому агент работает с локальными и удалёнными инструментами одинаково.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Protocol

from pydantic import BaseModel, ValidationError

logger = logging.getLogger("ai.tools")

# safe    — только чтение или безобидные действия (метрики, поиск, эмоции)
# caution — заметное вмешательство (открыть программу, нажать клавиши, громкость)
# danger  — необратимое/опасное (запуск команд, запись и удаление файлов, kill)
RiskLevel = Literal["safe", "caution", "danger"]

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AUDIT_LOG = os.path.join(BACKEND_DIR, "logs", "audit.jsonl")


class ExecutionContext(Protocol):
    """Контекст выполнения, который предоставляет менеджер задач."""

    task_id: str

    async def request_approval(
        self, tool: str, args: dict[str, Any], risk: RiskLevel, description: str
    ) -> bool: ...

    async def emit(self, action: str, **payload: Any) -> None: ...


@dataclass
class ToolSpec:
    name: str
    description: str
    func: Callable[..., Any]
    args_model: type[BaseModel] | None = None
    json_schema: dict[str, Any] | None = None  # для MCP-инструментов
    risk: RiskLevel = "safe"
    category: str = "system"
    source: str = "local"
    enabled: bool = True

    def schema(self) -> dict[str, Any]:
        if self.args_model is not None:
            params = self.args_model.model_json_schema()
            params.pop("title", None)
            for prop in params.get("properties", {}).values():
                prop.pop("title", None)
        else:
            params = self.json_schema or {"type": "object", "properties": {}}
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description[:1024],
                "parameters": params,
            },
        }

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "risk": self.risk,
            "category": self.category,
            "source": self.source,
            "enabled": self.enabled,
        }


class ToolError(Exception):
    """Ожидаемая ошибка инструмента — возвращается модели как текст."""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    # ── регистрация ────────────────────────────────────────────────────────
    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._tools:
            logger.warning(f"Инструмент '{spec.name}' переопределён ({spec.source})")
        self._tools[spec.name] = spec
        return spec

    def tool(
        self,
        name: str,
        description: str,
        args_model: type[BaseModel] | None = None,
        risk: RiskLevel = "safe",
        category: str = "system",
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.register(
                ToolSpec(
                    name=name,
                    description=description,
                    func=func,
                    args_model=args_model,
                    risk=risk,
                    category=category,
                )
            )
            return func

        return decorator

    def unregister_source(self, source: str) -> None:
        for name in [n for n, s in self._tools.items() if s.source == source]:
            del self._tools[name]

    # ── выборка ────────────────────────────────────────────────────────────
    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def enabled_specs(self, disabled: list[str] | None = None) -> list[ToolSpec]:
        blocked = set(disabled or [])
        return [s for s in self._tools.values() if s.enabled and s.name not in blocked]

    def openai_schemas(self, disabled: list[str] | None = None) -> list[dict[str, Any]]:
        return [s.schema() for s in self.enabled_specs(disabled)]

    def set_enabled(self, name: str, enabled: bool) -> bool:
        spec = self._tools.get(name)
        if not spec:
            return False
        spec.enabled = enabled
        return True

    # ── исполнение ─────────────────────────────────────────────────────────
    def needs_approval(self, spec: ToolSpec, autonomy: str) -> bool:
        if autonomy == "full":
            return False
        if autonomy == "ask":
            return spec.risk != "safe"
        # auto_safe
        return spec.risk == "danger"

    async def execute(
        self,
        name: str,
        args: dict[str, Any],
        ctx: ExecutionContext | None = None,
        autonomy: str = "auto_safe",
        disabled: list[str] | None = None,
    ) -> tuple[bool, str]:
        """Возвращает (успех, текст результата для модели)."""
        spec = self._tools.get(name)
        if spec is None:
            return False, f"Инструмент '{name}' не найден. Доступные: {', '.join(sorted(self._tools))}"

        if not spec.enabled or name in set(disabled or []):
            return False, f"Инструмент '{name}' отключён в настройках."

        # Валидация аргументов
        call_args = dict(args or {})
        if spec.args_model is not None:
            try:
                model = spec.args_model(**call_args)
                call_args = model.model_dump()
            except ValidationError as e:
                return False, f"Некорректные аргументы для '{name}': {e.errors()}"

        # Подтверждение пользователя
        if ctx is not None and self.needs_approval(spec, autonomy):
            approved = await ctx.request_approval(
                name, call_args, spec.risk, spec.description
            )
            if not approved:
                self._audit(name, call_args, "denied", "", 0.0)
                return False, "Пользователь отклонил выполнение этого действия."

        started = time.perf_counter()
        try:
            result = spec.func(**call_args)
            if inspect.isawaitable(result):
                result = await result
            text = result if isinstance(result, str) else json.dumps(
                result, ensure_ascii=False, default=str
            )
            ok = True
        except ToolError as e:
            text, ok = f"Ошибка: {e}", False
        except asyncio.TimeoutError:
            text, ok = "Ошибка: превышено время выполнения.", False
        except Exception as e:  # noqa: BLE001 — модель должна увидеть текст ошибки
            logger.exception(f"Инструмент '{name}' упал")
            text, ok = f"Ошибка выполнения: {type(e).__name__}: {e}", False

        duration = time.perf_counter() - started
        self._audit(name, call_args, "ok" if ok else "error", text, duration)
        return ok, self._truncate(text)

    @staticmethod
    def _truncate(text: str, limit: int = 6000) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + f"\n... [обрезано, всего {len(text)} символов]"

    @staticmethod
    def _audit(
        name: str, args: dict[str, Any], status: str, result: str, duration: float
    ) -> None:
        try:
            os.makedirs(os.path.dirname(AUDIT_LOG), exist_ok=True)
            entry = {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "tool": name,
                "args": args,
                "status": status,
                "duration_ms": round(duration * 1000),
                "result": result[:500],
            }
            with open(AUDIT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            logger.debug(f"Не удалось записать журнал действий: {e}")


registry = ToolRegistry()
