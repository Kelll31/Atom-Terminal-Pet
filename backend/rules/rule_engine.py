"""Движок правил: реакция питомца на состояние ПК.

Правило = условие по метрике (cpu/ram/gpu/temp) + действие:
  * set_emotion — сменить мордочку и сказать фразу;
  * speak       — только произнести фразу;
  * agent_task  — поставить агенту задачу (например, «найди, что грузит процессор»).

У каждого правила есть выдержка (duration_seconds) и период перезарядки
(cooldown_seconds), чтобы питомец не тараторил одно и то же.
"""

import asyncio
import logging
import os
import time

import yaml

from monitor.pc_monitor import pc_monitor

logger = logging.getLogger("rules.engine")

DEFAULT_COOLDOWN = 300


class RuleEngine:
    def __init__(self, config_path="rules/rules.yaml"):
        self.config_path = config_path
        self.rules = []
        self.is_running = False

        # rule_id -> момент, когда условие стало истинным
        self._active_since: dict[str, float] = {}
        # rule_id -> момент последнего срабатывания
        self._last_fired: dict[str, float] = {}

        self.load_rules()

    @property
    def full_path(self) -> str:
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), self.config_path)

    def load_rules(self):
        if not os.path.exists(self.full_path):
            logger.warning(f"Файл правил не найден: {self.full_path}")
            self.rules = []
            return

        try:
            with open(self.full_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self.rules = data.get("rules", []) or []
            logger.info(f"Загружено правил: {len(self.rules)}")
        except yaml.YAMLError as e:
            logger.error(f"Не удалось разобрать rules.yaml: {e}")

    def evaluate_condition(self, condition, metrics) -> bool:
        current = metrics.get(condition.get("metric"))
        target = condition.get("value")
        operator = condition.get("operator")
        if current is None or target is None:
            return False

        comparisons = {
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            "==": lambda a, b: a == b,
        }
        check = comparisons.get(operator)
        return bool(check and check(current, target))

    async def execute_action(self, rule: dict):
        from core.events import bus

        action = rule.get("action", {}) or {}
        action_type = action.get("type", "set_emotion")
        emotion = action.get("emotion", "idle")
        text = action.get("text", "")

        logger.info(f"Сработало правило '{rule.get('id')}': {action_type}")

        if action_type == "agent_task":
            from tasks.task_manager import task_manager

            prompt = action.get("task") or text
            if prompt:
                await task_manager.submit(prompt, source="rule")
            return

        if action_type == "speak":
            await bus.speak(text, emotion=emotion)
            return

        await bus.emit("speak", emotion=emotion, text=text)

    async def engine_loop(self):
        self.is_running = True
        logger.info("Движок правил запущен.")

        while self.is_running:
            try:
                metrics = pc_monitor.latest_metrics()
                now = time.time()

                for rule in self.rules:
                    rule_id = str(rule.get("id"))
                    condition = rule.get("condition") or {}

                    if not self.evaluate_condition(condition, metrics):
                        self._active_since.pop(rule_id, None)
                        continue

                    started = self._active_since.setdefault(rule_id, now)
                    if now - started < condition.get("duration_seconds", 0):
                        continue

                    cooldown = rule.get("cooldown_seconds", DEFAULT_COOLDOWN)
                    if now - self._last_fired.get(rule_id, 0) < cooldown:
                        continue

                    self._last_fired[rule_id] = now
                    await self.execute_action(rule)

                await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                self.is_running = False
                logger.info("Движок правил остановлен.")
                break
            except Exception as e:
                logger.error(f"Ошибка в движке правил: {e}")
                await asyncio.sleep(2.0)


rule_engine = RuleEngine()
