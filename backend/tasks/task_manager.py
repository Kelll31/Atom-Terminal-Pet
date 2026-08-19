"""Очередь задач Атома.

Пользователь ставит задачу (голосом или из web-панели) — она попадает в очередь
и выполняется по одной, чтобы питомец не говорил двумя голосами одновременно.
Каждый шаг выполнения (мысль, вызов инструмента, результат) публикуется в UI,
а опасные действия ждут подтверждения пользователя.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from ai.agent import AgentUnavailable, agent
from core.events import bus
from core.settings import settings_store

logger = logging.getLogger("tasks.manager")

TaskStatus = Literal["queued", "running", "waiting_approval", "done", "failed", "cancelled"]


@dataclass
class Step:
    id: str
    type: str  # thought | tool_call | tool_result | note
    ts: float
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    result: str = ""
    ok: bool = True
    text: str = ""
    parent: str = ""

    def dict(self) -> dict[str, Any]:
        data = asdict(self)
        if len(data["result"]) > 2000:
            data["result"] = data["result"][:2000] + "…"
        return data


@dataclass
class Task:
    id: str
    text: str
    source: str = "chat"  # chat | voice | rule | api
    status: TaskStatus = "queued"
    steps: list[Step] = field(default_factory=list)
    result: str = ""
    error: str = ""
    created: float = field(default_factory=time.time)
    finished: float | None = None

    @property
    def title(self) -> str:
        return self.text if len(self.text) <= 70 else self.text[:67] + "…"

    def dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "title": self.title,
            "source": self.source,
            "status": self.status,
            "steps": [s.dict() for s in self.steps],
            "result": self.result,
            "error": self.error,
            "created": self.created,
            "finished": self.finished,
            "duration": round((self.finished or time.time()) - self.created, 1),
        }


class TaskContext:
    """Реализация ExecutionContext для реестра инструментов."""

    def __init__(self, task: Task, manager: "TaskManager") -> None:
        self.task = task
        self.task_id = task.id
        self.manager = manager

    async def emit(self, action: str, **payload: Any) -> None:
        await bus.emit(action, task_id=self.task.id, **payload)

    async def add_step(self, step_type: str, **payload: Any) -> str:
        step = Step(
            id=uuid.uuid4().hex[:8],
            type=step_type,
            ts=time.time(),
            tool=payload.get("tool", ""),
            args=payload.get("args", {}) or {},
            result=str(payload.get("result", "")),
            ok=bool(payload.get("ok", True)),
            text=str(payload.get("text", "")),
            parent=str(payload.get("parent", "")),
        )
        self.task.steps.append(step)
        await bus.emit("agent_step", task_id=self.task.id, step=step.dict())
        await self.manager.publish(self.task)
        return step.id

    async def request_approval(
        self, tool: str, args: dict[str, Any], risk: str, description: str
    ) -> bool:
        return await self.manager.request_approval(self.task, tool, args, risk, description)


class TaskManager:
    def __init__(self, history_limit: int = 40) -> None:
        self.tasks: OrderedDict[str, Task] = OrderedDict()
        self.history_limit = history_limit
        self.queue: asyncio.Queue[Task] = asyncio.Queue()
        self.worker: asyncio.Task | None = None
        self.current: Task | None = None
        self._running_task: asyncio.Task | None = None

        # Подтверждения
        self.pending_approvals: dict[str, dict[str, Any]] = {}
        self._approval_futures: dict[str, asyncio.Future] = {}
        self.session_allow: set[str] = set()

    # ── жизненный цикл ─────────────────────────────────────────────────────
    def start(self) -> None:
        if self.worker is None or self.worker.done():
            self.worker = asyncio.create_task(self._worker_loop(), name="task-worker")

    async def stop(self) -> None:
        if self._running_task and not self._running_task.done():
            self._running_task.cancel()
        if self.worker and not self.worker.done():
            self.worker.cancel()

    # ── публичный API ──────────────────────────────────────────────────────
    async def submit(self, text: str, source: str = "chat") -> Task:
        task = Task(id=uuid.uuid4().hex[:10], text=text.strip(), source=source)
        self.tasks[task.id] = task
        while len(self.tasks) > self.history_limit:
            self.tasks.popitem(last=False)

        await self.queue.put(task)
        await self.publish(task)
        self.start()
        return task

    def get(self, task_id: str) -> Task | None:
        return self.tasks.get(task_id)

    def list(self) -> list[dict[str, Any]]:
        return [t.dict() for t in list(self.tasks.values())[::-1]]

    async def cancel(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if not task:
            return False
        if task.status in ("done", "failed", "cancelled"):
            return False

        if self.current and self.current.id == task_id and self._running_task:
            self._running_task.cancel()
        else:
            task.status = "cancelled"
            task.finished = time.time()
            await self.publish(task)

        # Снимаем ожидающие подтверждения этой задачи
        for approval_id, info in list(self.pending_approvals.items()):
            if info["task_id"] == task_id:
                await self.resolve_approval(approval_id, "deny")
        return True

    # ── подтверждения ──────────────────────────────────────────────────────
    async def request_approval(
        self, task: Task, tool: str, args: dict[str, Any], risk: str, description: str
    ) -> bool:
        if tool in self.session_allow:
            return True

        approval_id = uuid.uuid4().hex[:8]
        info = {
            "id": approval_id,
            "task_id": task.id,
            "task_title": task.title,
            "tool": tool,
            "args": args,
            "risk": risk,
            "description": description,
            "created": time.time(),
        }
        self.pending_approvals[approval_id] = info
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._approval_futures[approval_id] = future

        previous_status = task.status
        task.status = "waiting_approval"
        await self.publish(task)
        await bus.emit("approval_request", **info)
        await bus.set_emotion("thinking", "Confirm?")

        timeout = settings_store.get("approval_timeout_sec", 180)
        try:
            decision = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            decision = "deny"
            await bus.emit("approval_resolved", id=approval_id, decision="timeout")
        except asyncio.CancelledError:
            self.pending_approvals.pop(approval_id, None)
            self._approval_futures.pop(approval_id, None)
            raise
        finally:
            self.pending_approvals.pop(approval_id, None)
            self._approval_futures.pop(approval_id, None)
            task.status = previous_status if previous_status != "waiting_approval" else "running"
            await self.publish(task)

        if decision == "allow_always":
            self.session_allow.add(tool)
        return decision in ("allow", "allow_always")

    async def resolve_approval(self, approval_id: str, decision: str) -> bool:
        future = self._approval_futures.get(approval_id)
        if future is None or future.done():
            return False
        future.set_result(decision)
        await bus.emit("approval_resolved", id=approval_id, decision=decision)
        return True

    # ── внутреннее ─────────────────────────────────────────────────────────
    async def publish(self, task: Task) -> None:
        await bus.emit("task_update", task=task.dict())

    async def _worker_loop(self) -> None:
        logger.info("Очередь задач запущена.")
        while True:
            task = await self.queue.get()
            if task.status == "cancelled":
                continue
            self.current = task
            self._running_task = asyncio.create_task(self._execute(task))
            try:
                await self._running_task
            except asyncio.CancelledError:
                task.status = "cancelled"
                task.finished = time.time()
                await self.publish(task)
                await bus.speak("Отменил задачу.", emotion="sad")
            finally:
                self.current = None
                self._running_task = None
                self.queue.task_done()

    async def _execute(self, task: Task) -> None:
        task.status = "running"
        await self.publish(task)
        await bus.set_emotion("thinking", "Thinking...")

        ctx = TaskContext(task, self)
        try:
            result = await agent.run(task.text, ctx)
            task.result = result
            task.status = "done"
            task.finished = time.time()
            await self.publish(task)
            await bus.emit("agent_status", state="speaking")
            await bus.speak(result, emotion="happy")
            await bus.set_emotion("listening", "Listening...")
        except AgentUnavailable as e:
            task.status = "failed"
            task.error = str(e)
            task.finished = time.time()
            await self.publish(task)
            await bus.speak(str(e), emotion="sad")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("Задача упала")
            task.status = "failed"
            task.error = f"{type(e).__name__}: {e}"
            task.finished = time.time()
            await self.publish(task)
            await bus.speak("Что-то пошло не так, подробности в панели.", emotion="panic")


task_manager = TaskManager()
