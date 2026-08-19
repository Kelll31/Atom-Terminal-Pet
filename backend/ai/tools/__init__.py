"""Набор инструментов Атома.

Импорт пакета регистрирует все локальные инструменты в общем реестре.
MCP-инструменты добавляются туда же при подключении серверов
(см. core/mcp_client.py).
"""

from ai.tools import dev, files, productivity, system  # noqa: F401  (регистрация побочным эффектом)
from ai.tools.base import ExecutionContext, RiskLevel, ToolError, ToolSpec, registry

__all__ = ["registry", "ToolSpec", "ToolError", "RiskLevel", "ExecutionContext"]
