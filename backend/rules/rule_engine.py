import asyncio
import logging
import os
import time

import yaml

from core.ws_manager import manager
from monitor.pc_monitor import pc_monitor

logger = logging.getLogger("rules.engine")


class RuleEngine:
    def __init__(self, config_path="rules/rules.yaml"):
        self.config_path = config_path
        self.rules = []
        self.is_running = False

        # State tracker: { rule_id: timestamp_condition_started_being_true }
        self.rule_state = {}

        self.load_rules()

    def load_rules(self):
        full_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), self.config_path
        )
        if not os.path.exists(full_path):
            logger.warning(f"Rules file not found at {full_path}")
            return

        with open(full_path, "r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f)
                self.rules = data.get("rules", [])
                logger.info(f"Loaded {len(self.rules)} rules.")
            except yaml.YAMLError as e:
                logger.error(f"Failed to parse rules.yaml: {e}")

    def evaluate_condition(self, condition, metrics) -> bool:
        metric_name = condition.get("metric")
        operator = condition.get("operator")
        target_value = condition.get("value")

        current_value = metrics.get(metric_name)
        if current_value is None:
            return False

        if operator == ">":
            return current_value > target_value
        elif operator == "<":
            return current_value < target_value
        elif operator == "==":
            return current_value == target_value
        elif operator == ">=":
            return current_value >= target_value
        elif operator == "<=":
            return current_value <= target_value
        return False

    async def execute_action(self, action):
        action_type = action.get("type")
        if action_type == "set_emotion":
            payload = {
                "action": "speak",
                "emotion": action.get("emotion", "idle"),
                "text": action.get("text", ""),
            }
            logger.info(f"Rule Triggered! Executing action: {payload}")
            await manager.broadcast_json(payload)

    async def engine_loop(self):
        self.is_running = True
        logger.info("Rule Engine started.")

        while self.is_running:
            try:
                # We reuse collect_metrics or fetch latest values
                # Since pc_monitor is running, we can just grab latest (we need a way to store them)
                # For simplicity, we just call collect_metrics here again or read properties
                metrics = {
                    "cpu": int(
                        pc_monitor.get_gpu_usage()
                    ),  # using as placeholder if we were caching, but let's just collect
                    "temp": pc_monitor.get_cpu_temp(),
                }

                # A better approach: call collect_metrics
                full_metrics = await pc_monitor.collect_metrics()

                now = time.time()
                for rule in self.rules:
                    rule_id = rule.get("id")
                    cond = rule.get("condition")

                    if self.evaluate_condition(cond, full_metrics):
                        if rule_id not in self.rule_state:
                            self.rule_state[rule_id] = now

                        duration_needed = cond.get("duration_seconds", 0)
                        time_active = now - self.rule_state[rule_id]

                        # Use a flag to ensure we don't trigger endlessly
                        # e.g., only trigger once per condition met
                        trigger_key = f"{rule_id}_fired"

                        if time_active >= duration_needed and not self.rule_state.get(
                            trigger_key
                        ):
                            await self.execute_action(rule.get("action"))
                            self.rule_state[trigger_key] = True  # Mark as fired
                    else:
                        # Condition no longer met, reset state
                        if rule_id in self.rule_state:
                            del self.rule_state[rule_id]
                        trigger_key = f"{rule_id}_fired"
                        if trigger_key in self.rule_state:
                            del self.rule_state[trigger_key]

                await asyncio.sleep(1.0)

            except asyncio.CancelledError:
                self.is_running = False
                logger.info("Rule Engine stopped.")
                break
            except Exception as e:
                logger.error(f"Error in rule engine loop: {e}")
                await asyncio.sleep(1.0)


rule_engine = RuleEngine()
