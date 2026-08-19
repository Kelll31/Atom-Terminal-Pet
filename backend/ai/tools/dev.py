"""Инструменты для работы с кодом: shell-команды и git."""

from __future__ import annotations

import asyncio
import logging
import os

from pydantic import BaseModel, Field

from ai.tools.base import ToolError, registry
from ai.tools.files import resolve_path
from core.settings import settings_store

logger = logging.getLogger("ai.tools.dev")


async def _run(cmd: str, cwd: str, timeout: int) -> tuple[int, str]:
    """Запускает команду в оболочке и возвращает (код возврата, вывод)."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise ToolError(f"команда выполнялась дольше {timeout} с и была остановлена.")

    text = (stdout or b"").decode("utf-8", errors="replace").strip()
    return proc.returncode or 0, text


class RunCommandArgs(BaseModel):
    command: str = Field(..., description="Команда для оболочки Windows, например 'npm run build' или 'pytest -q'")
    cwd: str = Field(..., description="Рабочий каталог (абсолютный путь внутри разрешённых)")
    timeout_sec: int = Field(120, description="Таймаут в секундах")


@registry.tool(
    name="run_command",
    description=(
        "Выполняет команду в терминале Windows в указанном каталоге и возвращает её вывод. "
        "Подходит для сборки, тестов, npm/pip/git. Команда выполняется от имени пользователя — "
        "будь аккуратен и не запускай деструктивные вещи."
    ),
    args_model=RunCommandArgs,
    risk="danger",
    category="dev",
)
async def run_command(command: str, cwd: str, timeout_sec: int = 120) -> str:
    command = command.strip()
    if not command:
        raise ToolError("Пустая команда.")

    lowered = command.lower()
    for blocked in settings_store.get("blocked_commands") or []:
        if blocked.lower() in lowered:
            raise ToolError(
                f"команда содержит запрещённый фрагмент '{blocked}' и заблокирована политикой безопасности."
            )

    workdir = resolve_path(cwd)
    if not workdir.is_dir():
        raise ToolError(f"{workdir} — не каталог.")

    limit = min(int(timeout_sec or 120), int(settings_store.get("command_timeout_sec", 120)))
    code, output = await _run(command, str(workdir), limit)

    head = f"$ {command}   (в {workdir})\nКод возврата: {code}"
    return f"{head}\n{output or '(пустой вывод)'}"


class GitArgs(BaseModel):
    repo: str = Field(..., description="Путь к git-репозиторию")


@registry.tool(
    name="git_status",
    description="Показывает ветку, незакоммиченные изменения и последние коммиты репозитория.",
    args_model=GitArgs,
    risk="safe",
    category="dev",
)
async def git_status(repo: str) -> str:
    workdir = resolve_path(repo)
    if not (workdir / ".git").exists():
        raise ToolError(f"{workdir} не является git-репозиторием.")

    _, branch = await _run("git rev-parse --abbrev-ref HEAD", str(workdir), 20)
    _, status = await _run("git status --short", str(workdir), 20)
    _, log = await _run('git log --oneline -5', str(workdir), 20)

    return (
        f"Репозиторий: {workdir}\n"
        f"Ветка: {branch}\n\n"
        f"Изменения:\n{status or '  рабочее дерево чистое'}\n\n"
        f"Последние коммиты:\n{log}"
    )


class GitDiffArgs(BaseModel):
    repo: str = Field(..., description="Путь к git-репозиторию")
    staged: bool = Field(False, description="Показать проиндексированные изменения (--staged)")
    path: str = Field("", description="Ограничить diff одним файлом или каталогом")


@registry.tool(
    name="git_diff",
    description="Показывает diff рабочего дерева — что именно изменилось в коде.",
    args_model=GitDiffArgs,
    risk="safe",
    category="dev",
)
async def git_diff(repo: str, staged: bool = False, path: str = "") -> str:
    workdir = resolve_path(repo)
    cmd = "git --no-pager diff --stat -p"
    if staged:
        cmd += " --staged"
    if path:
        cmd += f' -- "{path}"'
    _, out = await _run(cmd, str(workdir), 30)
    return out or "Изменений нет."


class ProjectOverviewArgs(BaseModel):
    path: str = Field(..., description="Корень проекта")


@registry.tool(
    name="project_overview",
    description=(
        "Быстрый обзор проекта: определяет стек (package.json, requirements.txt, platformio.ini и т.п.), "
        "структуру верхнего уровня и доступные скрипты."
    ),
    args_model=ProjectOverviewArgs,
    risk="safe",
    category="dev",
)
def project_overview(path: str) -> str:
    root = resolve_path(path)
    if not root.is_dir():
        raise ToolError(f"{root} — не каталог.")

    markers = {
        "package.json": "Node.js / JavaScript",
        "requirements.txt": "Python",
        "pyproject.toml": "Python",
        "platformio.ini": "PlatformIO / встраиваемое ПО",
        "Cargo.toml": "Rust",
        "go.mod": "Go",
        "pom.xml": "Java / Maven",
        "CMakeLists.txt": "C/C++ CMake",
        "Dockerfile": "Docker",
    }

    lines = [f"Проект: {root}"]
    stack = [desc for f, desc in markers.items() if (root / f).exists()]
    lines.append("Стек: " + (", ".join(sorted(set(stack))) or "не определён"))

    entries = sorted(
        (p for p in root.iterdir() if not p.name.startswith(".")),
        key=lambda p: (p.is_file(), p.name.lower()),
    )
    lines.append("Структура:")
    for entry in entries[:40]:
        lines.append(f"  {'[DIR ] ' if entry.is_dir() else '[FILE] '}{entry.name}")

    pkg = root / "package.json"
    if pkg.exists():
        try:
            import json

            data = json.loads(pkg.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {})
            if scripts:
                lines.append("npm-скрипты: " + ", ".join(scripts.keys()))
        except Exception:
            pass

    readme = next((root / n for n in ("README.md", "readme.md") if (root / n).exists()), None)
    if readme:
        head = readme.read_text(encoding="utf-8", errors="replace")[:800]
        lines.append(f"README (начало):\n{head}")

    return "\n".join(lines)
