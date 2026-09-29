"""Инструменты для работы с кодом: shell-команды и git.

Про безопасность здесь важно понимать две вещи.

1. run_command — это буквально «выполнить произвольную команду». Никакой
   песочницы нет и быть не может: команда идёт в оболочку Windows от имени
   пользователя. Поэтому уровень инструмента danger, то есть подтверждение
   спрашивается во всех режимах автономии, кроме full.
2. Инструменты git помечены safe и выполняются без подтверждения — значит,
   ни один их аргумент не имеет права попасть в командную строку оболочки.
   Раньше git_diff подставлял путь внутрь кавычек, и аргумент вида
   `x" & calc & "` запускал постороннюю программу: достаточно было
   промпт-инъекции с веб-страницы или из прочитанного файла. Теперь git
   запускается через create_subprocess_exec списком аргументов — путь уходит
   отдельным элементом списка, и оболочки в этой цепочке нет вообще.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess

import psutil
from pydantic import BaseModel, Field

from ai.tools.base import ToolError, no_window_flags, registry
from ai.tools.files import resolve_path
from core.settings import settings_store

logger = logging.getLogger("ai.tools.dev")


def _child_env() -> dict[str, str]:
    """Окружение подпроцесса: как у бэкенда, но с предсказуемой кодировкой."""
    return {**os.environ, "PYTHONIOENCODING": "utf-8"}


def _spawn_kwargs() -> dict[str, object]:
    """Общие параметры запуска для всех подпроцессов инструментов.

    stdin=DEVNULL обязателен: в собранном приложении из трея стандартного
    ввода нет вовсе, и дочерний процесс, унаследовавший «ничей» дескриптор,
    падает с ошибкой неверного дескриптора. CREATE_NO_WINDOW (через
    no_window_flags, чтобы код не ломался вне Windows) убирает чёрное окно
    консоли, которое иначе мигает на каждую команду.
    """
    return {
        "stdin": subprocess.DEVNULL,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.STDOUT,
        "env": _child_env(),
        "creationflags": no_window_flags(),
    }


def _kill_tree(proc: asyncio.subprocess.Process) -> None:
    """Убивает процесс вместе с потомками.

    proc.kill() убивает только саму оболочку. Дети (компилятор, node, pytest)
    остаются жить, продолжают греть процессор и держать файлы — а пользователь
    уверен, что команду остановили по таймауту. psutil уже есть в зависимостях,
    поэтому обходим дерево им.
    """
    try:
        parent = psutil.Process(proc.pid)
        victims = parent.children(recursive=True) + [parent]
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        victims = []

    for victim in victims:
        try:
            victim.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    try:
        proc.kill()
    except ProcessLookupError:
        pass


async def _communicate(
    proc: asyncio.subprocess.Process, timeout: int, what: str
) -> tuple[int, str]:
    """Ждёт завершения, а по таймауту убивает всё дерево процессов."""
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        _kill_tree(proc)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            logger.warning(f"Процесс {proc.pid} не завершился после kill")
        raise ToolError(f"{what} выполнялась дольше {timeout} с и была остановлена.")

    text = (stdout or b"").decode("utf-8", errors="replace").strip()
    return proc.returncode or 0, text


async def _run_shell(cmd: str, cwd: str, timeout: int) -> tuple[int, str]:
    """Запускает строку в оболочке. Только для run_command (уровень danger)."""
    proc = await asyncio.create_subprocess_shell(cmd, cwd=cwd, **_spawn_kwargs())
    return await _communicate(proc, timeout, "команда")


async def _run_exec(argv: list[str], cwd: str, timeout: int) -> tuple[int, str]:
    """Запускает программу списком аргументов, БЕЗ оболочки.

    Именно этим пользуются инструменты уровня safe: аргумент любой формы
    остаётся аргументом, метасимволы оболочки (& | > `) не интерпретируются,
    потому что оболочки в цепочке нет.
    """
    proc = await asyncio.create_subprocess_exec(*argv, cwd=cwd, **_spawn_kwargs())
    return await _communicate(proc, timeout, f"команда {argv[0]}")


# ── Список стоп-слов (НЕ песочница) ────────────────────────────────────────
# Честно про то, что это такое: список подстрок из настроек, который отсекает
# несколько заведомо разрушительных команд (format, diskpart, shutdown...).
# Это защита от опечатки и от «модель увлеклась», а не граница безопасности:
# обойти список тривиально (переменные окружения, кодировка base64, свой .bat).
# Единственная настоящая защита для run_command — подтверждение пользователя.
#
# Сопоставление идёт по границам слов, потому что подстрочный фильтр ловил
# безобидное: «format» блокировал pytest -k test_format и prettier --format,
# а «shutdown» — grep shutdown в логах.
def _stop_word_pattern(fragment: str) -> re.Pattern[str]:
    escaped = re.escape(fragment.strip())
    # Границу ставим только там, где она осмысленна: у фрагментов вида
    # "rd /s /q c:\\" края и так не буквенные, лишний \b там не сработает.
    left = r"(?<![\w\-])" if fragment[:1].isalnum() or fragment[:1] == "_" else ""
    right = r"(?![\w\-])" if fragment[-1:].isalnum() or fragment[-1:] == "_" else ""
    return re.compile(left + escaped + right, re.IGNORECASE)


def find_stop_word(command: str) -> str | None:
    """Возвращает сработавшее стоп-слово или None."""
    # Пробелы схлопываем: "cipher    /w" и "cipher /w" — одно и то же.
    normalized = re.sub(r"\s+", " ", command)
    for fragment in settings_store.get("blocked_commands") or []:
        if not str(fragment).strip():
            continue
        if _stop_word_pattern(str(fragment)).search(normalized):
            return str(fragment)
    return None


class RunCommandArgs(BaseModel):
    command: str = Field(..., description="Команда для оболочки Windows, например 'npm run build' или 'pytest -q'")
    cwd: str = Field(..., description="Рабочий каталог (абсолютный путь внутри разрешённых)")
    timeout_sec: int = Field(120, description="Таймаут в секундах")


@registry.tool(
    name="run_command",
    description=(
        "Выполняет команду в терминале Windows в указанном каталоге и возвращает её вывод. "
        "Подходит для сборки, тестов, npm/pip/git. Команда выполняется в оболочке от имени "
        "пользователя, песочницы нет — есть лишь короткий список стоп-слов (format, diskpart, "
        "shutdown и подобные), который не заменяет осторожность. Не запускай деструктивные вещи."
    ),
    args_model=RunCommandArgs,
    risk="danger",
    category="dev",
)
async def run_command(command: str, cwd: str, timeout_sec: int = 120) -> str:
    command = command.strip()
    if not command:
        raise ToolError("Пустая команда.")

    stop_word = find_stop_word(command)
    if stop_word:
        raise ToolError(
            f"команда содержит стоп-слово '{stop_word}' и не будет выполнена. "
            "Список стоп-слов настраивается в панели (blocked_commands)."
        )

    workdir = resolve_path(cwd)
    if not workdir.is_dir():
        raise ToolError(f"{workdir} — не каталог.")

    limit = min(int(timeout_sec or 120), int(settings_store.get("command_timeout_sec", 120)))
    code, output = await _run_shell(command, str(workdir), limit)

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

    _, branch = await _run_exec(["git", "rev-parse", "--abbrev-ref", "HEAD"], str(workdir), 20)
    _, status = await _run_exec(["git", "status", "--short"], str(workdir), 20)
    _, log = await _run_exec(["git", "log", "--oneline", "-5"], str(workdir), 20)

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

    # Каждый элемент — отдельный аргумент процесса. Путь идёт после "--",
    # поэтому git трактует его как путь, даже если он начинается с дефиса,
    # а метасимволы оболочки в нём остаются обычными символами имени файла.
    argv = ["git", "--no-pager", "diff", "--stat", "-p"]
    if staged:
        argv.append("--staged")
    if path:
        argv += ["--", path]

    _, out = await _run_exec(argv, str(workdir), 30)
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
