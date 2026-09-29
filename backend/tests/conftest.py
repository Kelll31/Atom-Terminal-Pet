"""Изоляция тестов от настоящих данных пользователя.

Зачем это вообще нужно. core/paths.py вычисляет DATA_ROOT ОДИН РАЗ, на этапе
импорта модуля, и при запуске из исходников (без ATOM_DATA_DIR) он равен
каталогу backend. То есть любой тест, который трогает settings_store,
инструменты или журнал аудита, писал прямо в рабочие файлы разработчика:
backend/settings.json перезаписывался значениями по умолчанию — вместе с
API-ключом, — а backend/logs/audit.jsonl рос от каждого прогона.

Отсюда два требования к этому файлу:

1. ATOM_DATA_DIR выставляется на уровне модуля, а не в фикстуре. Фикстура,
   даже сессионная с autouse, отрабатывает уже после того, как pytest
   импортировал тестовые модули, а те тянут за собой core.paths — и DATA_ROOT
   успел бы вычислиться от backend. Модуль conftest.py импортируется раньше
   любого теста, поэтому переменная попадает в окружение вовремя.

2. Ничего из проекта нельзя импортировать выше строк, которые правят
   окружение. Один преждевременный `from core import paths` в шапке файла
   свёл бы всю защиту на нет.

Каталог создаётся временный, на сессию, и удаляется в конце. Настройки в него
кладём из settings.example.json: так тесты видят осмысленную конфигурацию
из коробки, а не пустышку, и при этом не зависят от того, что у разработчика
накручено в личном settings.json.
"""

from __future__ import annotations

import os
import shutil
import tempfile

# ── Всё, что ниже, должно выполниться ДО первого импорта проекта ────────────
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_TESTS_DIR)

# Каталог держим до конца сессии: часть модулей запоминает пути при импорте
# и пересоздать их между тестами уже нельзя.
_DATA_DIR = tempfile.mkdtemp(prefix="atompet-tests-")

os.environ["ATOM_DATA_DIR"] = _DATA_DIR

# Структуру создаём сразу: settings_store и журнал аудита открывают файлы
# на запись, не создавая родительскую папку.
for _sub in ("logs", "data", "config", "models", "rules"):
    os.makedirs(os.path.join(_DATA_DIR, _sub), exist_ok=True)

_EXAMPLE = os.path.join(_BACKEND_DIR, "settings.example.json")
if os.path.exists(_EXAMPLE):
    shutil.copyfile(_EXAMPLE, os.path.join(_DATA_DIR, "settings.json"))

# Порт по умолчанию тесты не занимают, но переменную фиксируем, чтобы прогон
# не зависел от того, что экспортировано в оболочке разработчика.
os.environ.setdefault("ATOM_PORT", "8000")

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def isolated_data_dir():
    """Страховка от регресса плюс уборка временного каталога.

    Проверка нужна не ради красоты: если кто-нибудь добавит импорт проекта
    в шапку conftest.py или в pytest.ini появится плагин, тянущий core.paths,
    DATA_ROOT снова укажет на backend — и тесты молча начнут затирать
    настоящие настройки. Пусть лучше сразу падает вся сессия.
    """
    from core import paths

    assert os.path.abspath(paths.DATA_ROOT) == os.path.abspath(_DATA_DIR), (
        "Тесты пишут не во временный каталог, а в "
        f"{paths.DATA_ROOT}. Скорее всего, core.paths импортировали раньше, "
        "чем conftest.py успел выставить ATOM_DATA_DIR."
    )

    yield _DATA_DIR

    # Журналы и модели могут быть заняты не закрытым файлом — падать из-за
    # уборки временной папки не стоит, ОС подчистит её сама.
    shutil.rmtree(_DATA_DIR, ignore_errors=True)
