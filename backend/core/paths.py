"""Где что лежит — при запуске из исходников и в собранном приложении.

Режимов два, и различаются они ровно одним:

    из исходников     ресурсы и данные лежат в репозитории, как и раньше;
    собранная сборка  ресурсы — внутри установленной программы (только чтение),
                      данные  — в %LOCALAPPDATA%\\AtomTerminalPet.

Разделение обязательное, а не косметическое: программа ставится в Program Files,
куда обычный пользователь писать не может. Раньше каждый модуль вычислял путь от
своего __file__ и складывал settings.json, журналы и заметки прямо рядом с кодом —
в упакованном виде первая же попытка сохранить настройки падала бы с отказом
в доступе.

Каталог данных можно переопределить переменной ATOM_DATA_DIR — это нужно тестам
и портативному режиму.
"""

from __future__ import annotations

import os
import shutil
import sys

APP_NAME = "AtomTerminalPet"

# Версия, которую показываем, если файл packaging/VERSION недоступен. Ноли
# выбраны намеренно: в отчёте о состоянии сервера сразу видно, что версию
# прочитать не удалось, и это не спутать с настоящим релизом.
FALLBACK_VERSION = "0.0.0"

_version_cache: str | None = None


def is_frozen() -> bool:
    """True, если код выполняется внутри сборки PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def _resource_root() -> str:
    if is_frozen():
        # В сборке onedir данные из spec попадают в _internal рядом с exe,
        # и именно на неё указывает _MEIPASS.
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    # backend/core/paths.py → backend/core → backend → корень репозитория
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _data_root() -> str:
    override = os.environ.get("ATOM_DATA_DIR")
    if override:
        return os.path.abspath(override)
    if is_frozen():
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP_NAME)
    # Из исходников ничего не переезжает: настройки, журналы и заметки
    # остаются там же, где лежали всегда, — в backend/.
    return os.path.join(_resource_root(), "backend")


RESOURCE_ROOT = _resource_root()
DATA_ROOT = _data_root()


def resource(*parts: str) -> str:
    """Файл из поставки. Только для чтения."""
    return os.path.join(RESOURCE_ROOT, *parts)


def data(*parts: str) -> str:
    """Файл пользователя. Доступен на запись."""
    return os.path.join(DATA_ROOT, *parts)


def seeded(*parts: str) -> str:
    """Путь в каталоге данных, при первом обращении копируемый из поставки.

    Так правки пользователя (список MCP-серверов, правила реакции) переживают
    обновление программы, но из коробки файл уже не пустой.
    """
    target = data(*parts)
    if os.path.exists(target):
        return target

    source = resource("backend", *parts)
    if os.path.abspath(source) == os.path.abspath(target):
        return target   # запуск из исходников: это один и тот же файл

    if os.path.exists(source):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(source, target)
    return target


def version() -> str:
    """Версия сборки из packaging/VERSION.

    Единственный источник правды о версии на весь проект: тот же файл читает
    установщик и скрипт сборки, поэтому цифры в заголовке FastAPI, в ответе
    /api/status и в «Программах и компонентах» Windows гарантированно совпадают.

    Любая ошибка чтения (файл не попал в сборку, нет прав, пустое содержимое)
    гасится запасным значением: версия — справочная информация, из-за неё
    сервер стартовать не откажется. Результат кэшируется, потому что дёргать
    диск на каждый запрос /api/status незачем — в работающем процессе файл
    измениться не может.
    """
    global _version_cache
    if _version_cache is not None:
        return _version_cache

    try:
        with open(resource("packaging", "VERSION"), "r", encoding="utf-8") as f:
            value = f.read().strip()
    except Exception:
        value = ""

    _version_cache = value or FALLBACK_VERSION
    return _version_cache


def model_dir(name: str) -> str:
    """Модель распознавания: сначала докачанная пользователем, потом штатная."""
    local = data("models", name)
    if os.path.isdir(local):
        return local
    return resource("backend", "models", name)


def ensure_dirs() -> None:
    """Создаёт каталог данных со всей структурой. Идемпотентно.

    Подкаталоги нужны заранее: сохранение правил и настроек из панели пишет
    файл напрямую, без создания родительской папки, и на чистой установке
    первая же попытка сохранить падала бы.
    """
    for sub in ("logs", "data", "config", "models", "rules"):
        os.makedirs(data(sub), exist_ok=True)
