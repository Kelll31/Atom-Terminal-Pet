"""Файловые инструменты. Все операции ограничены каталогами из настроек
(`allowed_roots`) — Атом не может выйти за их пределы."""

from __future__ import annotations

import fnmatch
import logging
import os
import shutil
from pathlib import Path

from pydantic import BaseModel, Field

from ai.tools.base import ToolError, registry
from core.settings import settings_store

logger = logging.getLogger("ai.tools.files")

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".pio", "dist", "build", ".idea"}
TEXT_SUFFIXES = {
    ".txt", ".md", ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".cpp", ".c", ".h", ".hpp", ".java", ".kt", ".go",
    ".rs", ".rb", ".php", ".sh", ".ps1", ".bat", ".html", ".css", ".scss", ".sql",
    ".env", ".gitignore", ".xml", ".csv", ".log",
}


def resolve_path(raw: str, must_exist: bool = True) -> Path:
    """Приводит путь к абсолютному и проверяет, что он внутри разрешённых корней."""
    if not raw or not str(raw).strip():
        raise ToolError("Путь не указан.")

    path = Path(os.path.expandvars(os.path.expanduser(str(raw).strip())))
    try:
        path = path.resolve()
    except OSError as e:
        raise ToolError(f"некорректный путь: {e}")

    roots = settings_store.get("allowed_roots") or []
    if not roots:
        raise ToolError(
            "Не задан ни один разрешённый каталог. Добавьте рабочие папки "
            "в настройках web-панели (раздел «Доступ к файлам»)."
        )

    for root in roots:
        try:
            root_path = Path(os.path.expanduser(root)).resolve()
        except OSError:
            continue
        if path == root_path or root_path in path.parents:
            break
    else:
        raise ToolError(
            f"Путь '{path}' вне разрешённых каталогов: {', '.join(roots)}. "
            "Пользователь может добавить каталог в настройках."
        )

    if must_exist and not path.exists():
        raise ToolError(f"Путь не существует: {path}")
    return path


class ListDirArgs(BaseModel):
    path: str = Field(..., description="Абсолютный путь к каталогу")
    pattern: str = Field("*", description="Маска имён, например '*.py'")


@registry.tool(
    name="list_dir",
    description="Показывает содержимое каталога: файлы с размерами и вложенные папки.",
    args_model=ListDirArgs,
    risk="safe",
    category="files",
)
def list_dir(path: str, pattern: str = "*") -> str:
    target = resolve_path(path)
    if not target.is_dir():
        raise ToolError(f"{target} — это файл, а не каталог.")

    dirs, files = [], []
    for entry in sorted(target.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_dir():
            dirs.append(f"[DIR ] {entry.name}/")
        elif fnmatch.fnmatch(entry.name, pattern):
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0
            files.append(f"[FILE] {entry.name} ({size / 1024:.1f} КБ)")

    if not dirs and not files:
        return f"{target} — пусто."
    listing = "\n".join(dirs[:100] + files[:200])
    return f"{target}\n{listing}"


class ReadFileArgs(BaseModel):
    path: str = Field(..., description="Абсолютный путь к файлу")
    max_lines: int = Field(400, description="Сколько строк прочитать (по умолчанию 400)")
    start_line: int = Field(1, description="С какой строки начать (нумерация с 1)")


@registry.tool(
    name="read_file",
    description="Читает текстовый файл (код, конфиг, лог) с нумерацией строк.",
    args_model=ReadFileArgs,
    risk="safe",
    category="files",
)
def read_file(path: str, max_lines: int = 400, start_line: int = 1) -> str:
    target = resolve_path(path)
    if target.is_dir():
        raise ToolError(f"{target} — каталог. Используй list_dir.")
    if target.stat().st_size > 5 * 1024 * 1024:
        raise ToolError("Файл больше 5 МБ — слишком большой для чтения целиком.")

    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise ToolError(f"не удалось прочитать файл: {e}")

    lines = text.splitlines()
    start = max(1, start_line)
    chunk = lines[start - 1 : start - 1 + max(1, max_lines)]
    numbered = "\n".join(f"{start + i:>5}| {line}" for i, line in enumerate(chunk))
    tail = ""
    if start - 1 + len(chunk) < len(lines):
        tail = f"\n... показано {len(chunk)} из {len(lines)} строк."
    return f"{target}\n{numbered}{tail}"


class WriteFileArgs(BaseModel):
    path: str = Field(..., description="Абсолютный путь к файлу")
    content: str = Field(..., description="Содержимое файла")
    mode: str = Field("overwrite", description="'overwrite' — перезаписать, 'append' — дописать в конец")


@registry.tool(
    name="write_file",
    description="Создаёт или перезаписывает текстовый файл. Перед перезаписью делает резервную копию .bak.",
    args_model=WriteFileArgs,
    risk="danger",
    category="files",
)
def write_file(path: str, content: str, mode: str = "overwrite") -> str:
    target = resolve_path(path, must_exist=False)
    target.parent.mkdir(parents=True, exist_ok=True)

    if mode == "append":
        with open(target, "a", encoding="utf-8") as f:
            f.write(content)
        return f"Дописано {len(content)} символов в {target}."

    if target.exists():
        try:
            shutil.copy2(target, target.with_suffix(target.suffix + ".bak"))
        except Exception as e:
            logger.warning(f"Не удалось создать резервную копию {target}: {e}")

    target.write_text(content, encoding="utf-8")
    return f"Записано {len(content)} символов в {target}."


class SearchFilesArgs(BaseModel):
    root: str = Field(..., description="Каталог, в котором искать")
    pattern: str = Field(..., description="Маска имени файла, например '*.tsx' или 'main.*'")
    limit: int = Field(50, description="Максимум результатов")


@registry.tool(
    name="search_files",
    description="Рекурсивно ищет файлы по маске имени. Пропускает node_modules, .git, venv и подобные.",
    args_model=SearchFilesArgs,
    risk="safe",
    category="files",
)
def search_files(root: str, pattern: str, limit: int = 50) -> str:
    base = resolve_path(root)
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if fnmatch.fnmatch(name, pattern):
                found.append(os.path.join(dirpath, name))
                if len(found) >= max(1, limit):
                    return "\n".join(found) + "\n(достигнут лимит результатов)"
    return "\n".join(found) if found else f"По маске '{pattern}' в {base} ничего не найдено."


class GrepArgs(BaseModel):
    root: str = Field(..., description="Каталог, в котором искать")
    query: str = Field(..., description="Искомая подстрока (без учёта регистра)")
    file_pattern: str = Field("*", description="Ограничить маской файлов, например '*.py'")
    limit: int = Field(40, description="Максимум совпадений")


@registry.tool(
    name="grep_files",
    description="Ищет текст внутри файлов и показывает путь, номер строки и саму строку.",
    args_model=GrepArgs,
    risk="safe",
    category="files",
)
def grep_files(root: str, query: str, file_pattern: str = "*", limit: int = 40) -> str:
    base = resolve_path(root)
    needle = query.lower()
    hits: list[str] = []

    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if not fnmatch.fnmatch(name, file_pattern):
                continue
            fpath = Path(dirpath) / name
            if fpath.suffix and fpath.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                if fpath.stat().st_size > 2 * 1024 * 1024:
                    continue
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if needle in line.lower():
                            hits.append(f"{fpath}:{i}: {line.strip()[:200]}")
                            if len(hits) >= max(1, limit):
                                return "\n".join(hits) + "\n(достигнут лимит совпадений)"
            except OSError:
                continue
    return "\n".join(hits) if hits else f"'{query}' в {base} не найдено."


class MakeDirArgs(BaseModel):
    path: str = Field(..., description="Путь создаваемого каталога")


@registry.tool(
    name="make_dir",
    description="Создаёт каталог (вместе с родительскими).",
    args_model=MakeDirArgs,
    risk="caution",
    category="files",
)
def make_dir(path: str) -> str:
    target = resolve_path(path, must_exist=False)
    target.mkdir(parents=True, exist_ok=True)
    return f"Каталог создан: {target}"


class DeletePathArgs(BaseModel):
    path: str = Field(..., description="Путь к файлу или каталогу")
    recursive: bool = Field(False, description="Удалить каталог со всем содержимым")


@registry.tool(
    name="delete_path",
    description="Удаляет файл или каталог. Действие необратимо.",
    args_model=DeletePathArgs,
    risk="danger",
    category="files",
)
def delete_path(path: str, recursive: bool = False) -> str:
    target = resolve_path(path)
    roots = [Path(os.path.expanduser(r)).resolve() for r in (settings_store.get("allowed_roots") or [])]
    if target in roots:
        raise ToolError("Нельзя удалить сам разрешённый корневой каталог.")

    if target.is_dir():
        if not recursive and any(target.iterdir()):
            raise ToolError(f"Каталог {target} не пуст. Нужен recursive=true.")
        shutil.rmtree(target) if recursive else target.rmdir()
        return f"Каталог удалён: {target}"
    target.unlink()
    return f"Файл удалён: {target}"
