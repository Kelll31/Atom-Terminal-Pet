"""Реестр инструментов Патрика.

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
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Protocol

from pydantic import BaseModel, ValidationError

logger = logging.getLogger("ai.tools")

# safe    — только чтение или безобидные действия (метрики, поиск, эмоции)
# caution — заметное вмешательство (открыть программу, нажать клавиши, громкость)
# danger  — необратимое/опасное (запуск команд, запись и удаление файлов, kill)
RiskLevel = Literal["safe", "caution", "danger"]

# Численный порядок уровней: нужен, чтобы сравнивать «что опаснее»,
# а не перечислять варианты в каждом if.
RISK_ORDER: dict[str, int] = {"safe": 0, "caution": 1, "danger": 2}

from core import paths

BACKEND_DIR = paths.DATA_ROOT
AUDIT_LOG = paths.data("logs", "audit.jsonl")

# ── Журнал действий ────────────────────────────────────────────────────────
# Журнал пишется на каждый вызов инструмента и живёт вечно, поэтому в него
# нельзя складывать полезную нагрузку: содержимое write_file, прочитанный
# буфер обмена и куски файлов (включая .env) осели бы на диске открытым
# текстом, а GET /api/audit отдал бы их в браузер целиком.
AUDIT_ARG_LIMIT = 200        # длиннее — в журнал уходит только длина строки
AUDIT_RESULT_LIMIT = 200     # результат интересен как «что вернулось», а не целиком
AUDIT_MAX_BYTES = 5 * 1024 * 1024   # порог ротации
AUDIT_BACKUPS = 2                   # сколько старых файлов храним

# Ключи аргументов, в которых по смыслу лежит содержимое, а не параметр.
# Текст для буфера обмена сюда не входит намеренно: он приходит под ключом
# "text", как и безобидная подпись на экране питомца, — буфер закрыт целиком
# через SENSITIVE_TOOLS, а подписи в журнале полезно видеть как есть.
CONTENT_ARG_KEYS = {"content", "body", "data", "payload"}

# Ключи, которые описывают ЦЕЛЬ действия, а не полезную нагрузку. Их значения
# в журнале и нужны: без пути запись «прочитал файл» бесполезна для разбора.
AUDIT_TARGET_KEYS = {"path", "root", "repo", "cwd", "target", "file_pattern", "pattern", "name"}

# Инструменты, у которых И аргументы, И результат — это чужой текст:
# буфер обмена (там бывают пароли) и чтение файлов. Для них в журнал
# попадают только метаданные: имя цели и размер.
SENSITIVE_TOOLS = {"clipboard", "read_file", "grep_files"}


def no_window_flags() -> int:
    """Флаги CreateProcess для подпроцессов инструментов.

    CREATE_NO_WINDOW нужен потому, что бэкенд обычно живёт в трее без консоли:
    без этого флага на каждую команду посреди экрана мигает чёрное окно cmd.
    На не-Windows константы нет, поэтому возвращаем 0 — Popen такой
    creationflags принимает на любой платформе, и код остаётся переносимым.
    """
    if sys.platform != "win32":
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


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
    # Уровень риска у некоторых инструментов зависит от аргументов, а не от
    # самого инструмента: open_program без аргументов — это «открыть файл»,
    # а с аргументами — произвольный запуск процесса; clipboard на чтение
    # безобиден, на запись — половина цепочки «записать → win+r → вставить».
    # Статическим полем risk такое не выразить, поэтому здесь необязательная
    # функция, которая уточняет уровень по конкретному вызову.
    risk_for: Callable[[dict[str, Any]], RiskLevel] | None = None
    category: str = "system"
    source: str = "local"
    enabled: bool = True

    def effective_risk(self, args: dict[str, Any] | None = None) -> RiskLevel:
        """Уровень риска конкретного вызова: не ниже базового.

        Понижать уровень аргументами нельзя намеренно — иначе достаточно было бы
        подобрать «безобидные» аргументы, чтобы обойти подтверждение.
        """
        if self.risk_for is None:
            return self.risk
        try:
            dynamic = self.risk_for(dict(args or {}))
        except Exception as e:  # noqa: BLE001 — сбой оценки не должен ослаблять защиту
            logger.warning(f"Не удалось уточнить риск для '{self.name}': {e}")
            return "danger"
        if dynamic not in RISK_ORDER:
            return "danger"
        return dynamic if RISK_ORDER[dynamic] > RISK_ORDER[self.risk] else self.risk

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
            # Подсказка панели: у таких инструментов показанный уровень —
            # минимальный, конкретный вызов может оказаться опаснее.
            "risk_dynamic": self.risk_for is not None,
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
        risk_for: Callable[[dict[str, Any]], RiskLevel] | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.register(
                ToolSpec(
                    name=name,
                    description=description,
                    func=func,
                    args_model=args_model,
                    risk=risk,
                    risk_for=risk_for,
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
    def needs_approval(
        self, spec: ToolSpec, autonomy: str, risk: RiskLevel | None = None
    ) -> bool:
        # risk передаётся отдельно, потому что уровень может зависеть от
        # аргументов вызова (см. ToolSpec.effective_risk).
        level = risk or spec.risk
        if autonomy == "full":
            return False
        if autonomy == "ask":
            return level != "safe"
        # auto_safe
        return level == "danger"

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
        risk = spec.effective_risk(call_args)
        if ctx is not None and self.needs_approval(spec, autonomy, risk):
            approved = await ctx.request_approval(
                name, call_args, risk, spec.description
            )
            if not approved:
                self._audit(name, call_args, "denied", "", 0.0)
                return False, "Пользователь отклонил выполнение этого действия."

        started = time.perf_counter()
        try:
            result = await self._call(spec, call_args)
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
    async def _call(spec: ToolSpec, call_args: dict[str, Any]) -> Any:
        """Вызывает функцию инструмента, не занимая цикл событий.

        Синхронные инструменты — это блокирующий ввод-вывод и WinAPI:
        перечисление процессов psutil занимает около 1.8 с, чтение файла с
        сетевого диска — сколько угодно. Всё это время цикл событий стоит,
        а вместе с ним стоит и отправка звуковых кусков на устройство:
        речь рвётся, кадры микрофона теряются. Поэтому синхронную функцию
        уводим в поток, а корутину исполняем как есть.
        """
        if inspect.iscoroutinefunction(spec.func):
            return await spec.func(**call_args)

        result = await asyncio.to_thread(spec.func, **call_args)
        # Редкий случай: обычная функция вернула awaitable (например, обёртка
        # над корутиной). Дожидаемся уже в цикле событий.
        if inspect.isawaitable(result):
            return await result
        return result

    @staticmethod
    def _truncate(text: str, limit: int = 6000) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + f"\n... [обрезано, всего {len(text)} символов]"

    # ── журнал действий ────────────────────────────────────────────────────
    @staticmethod
    def _audit_value(key: str, value: Any) -> Any:
        """Одно значение аргумента в виде, пригодном для вечного хранения."""
        if not isinstance(value, str):
            return value
        if key in CONTENT_ARG_KEYS:
            # Содержимое write_file и текст для буфера обмена не нужны никогда:
            # интересен факт «записали N символов туда-то», а не сами данные.
            return f"<{len(value)} символов>"
        if len(value) > AUDIT_ARG_LIMIT:
            return f"<строка {len(value)} символов>"
        return value

    @classmethod
    def _audit_args(cls, name: str, args: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        sensitive = name in SENSITIVE_TOOLS
        for key, value in (args or {}).items():
            if sensitive and isinstance(value, str) and key not in AUDIT_TARGET_KEYS:
                # У чувствительных инструментов в журнал идёт только цель
                # (путь, маска) и размеры — остальное это чужой текст.
                clean[key] = f"<{len(value)} символов>"
                continue
            clean[key] = cls._audit_value(key, value)
        return clean

    @staticmethod
    def _rotate_audit() -> None:
        """Перекладывает разросшийся журнал в .1/.2 и начинает новый.

        Без этого audit.jsonl растёт бесконечно, а GET /api/audit каждый раз
        читает его целиком (readlines) — на сотнях мегабайт это выедает память
        процесса в трее.
        """
        try:
            if os.path.getsize(AUDIT_LOG) < AUDIT_MAX_BYTES:
                return
        except OSError:
            return

        oldest = f"{AUDIT_LOG}.{AUDIT_BACKUPS}"
        if os.path.exists(oldest):
            os.remove(oldest)
        for index in range(AUDIT_BACKUPS - 1, 0, -1):
            src, dst = f"{AUDIT_LOG}.{index}", f"{AUDIT_LOG}.{index + 1}"
            if os.path.exists(src):
                os.replace(src, dst)
        os.replace(AUDIT_LOG, f"{AUDIT_LOG}.1")

    @classmethod
    def _audit(
        cls, name: str, args: dict[str, Any], status: str, result: str, duration: float
    ) -> None:
        try:
            os.makedirs(os.path.dirname(AUDIT_LOG), exist_ok=True)
            if os.path.exists(AUDIT_LOG):
                cls._rotate_audit()

            if name in SENSITIVE_TOOLS:
                # Результат read_file/grep_files/clipboard — это содержимое
                # чужих файлов и буфера (пароли, .env). В журнал только размер.
                short_result = f"<{len(result)} символов, содержимое не сохраняем>"
            else:
                short_result = cls._truncate(result or "", AUDIT_RESULT_LIMIT)

            entry = {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "tool": name,
                "args": cls._audit_args(name, args),
                "status": status,
                "duration_ms": round(duration * 1000),
                "result": short_result,
            }
            with open(AUDIT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            logger.debug(f"Не удалось записать журнал действий: {e}")


registry = ToolRegistry()
