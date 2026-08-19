"""Агент Атома: цикл «модель ↔ инструменты».

Модель получает список инструментов (локальные + MCP) и сама решает, что вызвать.
Каждый вызов проходит через реестр: проверка прав, подтверждение опасных действий,
запись в журнал. Все шаги транслируются в web-панель, поэтому пользователь видит,
что именно делает питомец.
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from typing import Any

import yaml
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from ai.tools import registry
from ai.tools.productivity import load_memory_digest
from core.settings import settings_store

logger = logging.getLogger("ai.agent")

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS_FILE = os.path.join(BACKEND_DIR, "config", "prompts.yaml")

FALLBACK_PROMPT = (
    "Ты — {pet_name}, кибер-питомец и помощник программиста, живущий в M5Stack AtomS3R. "
    "Отвечай коротко и по делу на русском языке."
)

NO_KEY_MESSAGE = (
    "Мозг не подключён: не задан API-ключ модели. Открой web-панель, вкладка «Настройки», "
    "укажи ключ и модель — и я снова смогу думать."
)


class AgentUnavailable(Exception):
    """Агент не может работать (нет ключа/модели)."""


def load_system_prompt(pc_context: dict[str, Any]) -> str:
    settings = settings_store.current
    template = FALLBACK_PROMPT
    if os.path.exists(PROMPTS_FILE):
        try:
            with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                template = data.get("system_prompt", template)
        except Exception as e:
            logger.error(f"Не удалось прочитать prompts.yaml: {e}")

    prompt = template.format(
        pet_name=settings.pet_name,
        cpu=pc_context.get("cpu", 0),
        ram=pc_context.get("ram", 0),
        gpu=pc_context.get("gpu", 0),
        temp=pc_context.get("temp", 0),
        media=pc_context.get("spotify", "ничего"),
    )

    autonomy_note = {
        "ask": "Каждое действие, меняющее систему, пользователь подтверждает вручную — предупреждай об этом.",
        "auto_safe": "Безопасные инструменты ты применяешь сам, опасные (запись файлов, команды, kill) пользователь подтверждает.",
        "full": "Тебе разрешено выполнять любые инструменты без подтверждения. Будь предельно аккуратен.",
    }[settings.autonomy]

    parts = [prompt, "", f"РЕЖИМ АВТОНОМИИ: {autonomy_note}"]

    roots = settings.allowed_roots
    if roots:
        parts.append("Доступные каталоги для файловых операций: " + "; ".join(roots))
    else:
        parts.append("Файловые инструменты пока недоступны: пользователь не выбрал рабочие каталоги.")

    memory = load_memory_digest()
    if memory:
        parts.append("\nЧТО ТЫ ПОМНИШЬ О ПОЛЬЗОВАТЕЛЕ:\n" + memory)

    parts.append(
        "\nПРАВИЛА РАБОТЫ С ИНСТРУМЕНТАМИ:\n"
        "- Если задачу можно выполнить инструментом — выполняй, а не рассказывай, как её сделать.\n"
        "- Сначала собери факты (get_pc_status, list_dir, read_file, git_status), потом действуй.\n"
        "- Опасные действия описывай пользователю до вызова: он увидит запрос подтверждения.\n"
        "- Не выдумывай результат инструмента. Если инструмент вернул ошибку — честно скажи об этом.\n"
        "- Итоговый ответ — короткий (1-3 предложения), без эмодзи и Markdown: его читает синтезатор речи."
    )
    return "\n".join(parts)


def build_llm(with_tools: bool = True):
    from langchain_openai import ChatOpenAI

    settings = settings_store.current
    if not settings.api_key:
        raise AgentUnavailable(NO_KEY_MESSAGE)

    headers = {}
    if settings.base_url and "openrouter.ai" in settings.base_url.lower():
        headers = {"HTTP-Referer": "http://localhost:8000", "X-Title": "Atom-Terminal-Pet"}

    llm = ChatOpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url or None,
        model=settings.model_name or "gpt-4o-mini",
        temperature=settings.temperature,
        timeout=90,
        max_retries=2,
        default_headers=headers,
    )

    if with_tools:
        schemas = registry.openai_schemas(settings.disabled_tools)
        if schemas:
            llm = llm.bind_tools(schemas)
    return llm


class AtomAgent:
    """Хранит историю диалога и выполняет задачи."""

    def __init__(self, history_limit: int = 16) -> None:
        self.history: deque[BaseMessage] = deque(maxlen=history_limit)

    def reset(self) -> None:
        self.history.clear()

    async def run(self, user_text: str, ctx: Any) -> str:
        """Выполняет задачу пользователя. ctx — контекст задачи (шаги, подтверждения)."""
        from monitor.pc_monitor import pc_monitor

        settings = settings_store.current
        pc_context = pc_monitor.latest_metrics()
        llm = build_llm(with_tools=True)

        messages: list[BaseMessage] = [SystemMessage(content=load_system_prompt(pc_context))]
        messages.extend(self.history)
        messages.append(HumanMessage(content=user_text))

        final_text = ""
        for step in range(settings.max_steps):
            await ctx.emit("agent_status", state="thinking", step=step + 1)

            try:
                ai_msg: AIMessage = await llm.ainvoke(messages)
            except Exception as e:  # noqa: BLE001
                logger.error(f"Ошибка обращения к модели: {e}")
                raise AgentUnavailable(f"Модель недоступна: {e}") from e

            messages.append(ai_msg)
            tool_calls = getattr(ai_msg, "tool_calls", None) or []

            if not tool_calls:
                final_text = self._text_of(ai_msg)
                break

            if isinstance(ai_msg.content, str) and ai_msg.content.strip():
                await ctx.add_step("thought", text=ai_msg.content.strip())

            for call in tool_calls:
                name = call.get("name", "")
                args = call.get("args", {}) or {}
                call_id = call.get("id") or name

                await ctx.emit("agent_status", state="working", tool=name)
                step_id = await ctx.add_step("tool_call", tool=name, args=args)

                ok, result = await registry.execute(
                    name,
                    args,
                    ctx=ctx,
                    autonomy=settings.autonomy,
                    disabled=settings.disabled_tools,
                )
                await ctx.add_step("tool_result", tool=name, ok=ok, result=result, parent=step_id)
                messages.append(ToolMessage(content=result, tool_call_id=call_id, name=name))
        else:
            final_text = (
                "Я сделал что мог, но задача оказалась слишком длинной — "
                "остановился на лимите шагов. Скажи, что делать дальше."
            )

        if not final_text:
            final_text = "Готово."

        self.history.append(HumanMessage(content=user_text))
        self.history.append(AIMessage(content=final_text))
        return final_text

    @staticmethod
    def _text_of(message: AIMessage) -> str:
        content = message.content
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):  # некоторые провайдеры отдают блоки
            parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            return "\n".join(p for p in parts if p).strip()
        return str(content or "").strip()


agent = AtomAgent()


def is_wake_word_present(text: str) -> bool:
    """Проверка обращения к питомцу по имени (только для голосового ввода)."""
    settings = settings_store.current
    if not settings.require_wake_word:
        return True
    lowered = text.lower()
    words = set(settings.wake_words) | {settings.pet_name.lower()}
    return any(word and word in lowered for word in words)


async def quick_reply(text: str) -> str:
    """Ответ без инструментов — используется для быстрых реплик и тестов связи."""
    llm = build_llm(with_tools=False)
    response = await llm.ainvoke(
        [SystemMessage(content=load_system_prompt({})), HumanMessage(content=text)]
    )
    return AtomAgent._text_of(response)


def tools_snapshot() -> list[dict[str, Any]]:
    disabled = set(settings_store.get("disabled_tools") or [])
    snapshot = []
    for spec in registry.all():
        info = spec.info()
        info["enabled"] = info["enabled"] and spec.name not in disabled
        snapshot.append(info)
    return sorted(snapshot, key=lambda s: (s["category"], s["name"]))


def describe_tools_for_log() -> str:
    return json.dumps(tools_snapshot(), ensure_ascii=False, indent=2)
