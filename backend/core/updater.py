"""Обновление установленного Патрика.

Программа ставится установщиком Inno Setup с постоянным AppId, поэтому новая
версия ставится поверх старой: настройки, заметки и память лежат в
%LOCALAPPDATA% и переустановку переживают. Здесь — всё, что нужно, чтобы
пользователю не пришлось ходить за этим установщиком руками:

    проверка    что за версия лежит в последнем релизе на GitHub;
    загрузка    setup.exe во временный каталог с проверкой размера и sha256;
    запуск      тихая установка и корректный выход приложения.

Источник по умолчанию — релизы репозитория. Его можно подменить настройкой
`update_url`: по этому адресу ожидается latest.json вида
{"version": "1.1.0", "url": "...setup.exe", "sha256": "…", "notes": "…"}.

Запущенная из исходников копия обновляется через git — установщика у неё нет,
и все операции ниже честно отвечают, что обновлять нечего.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import httpx

from core import paths
from core.settings import settings_store

logger = logging.getLogger("core.updater")

GITHUB_REPO = "Kelll31/Atom-Terminal-Pet"
GITHUB_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"

STATE_FILE = paths.data("update.json")

# Раз в сутки: чаще бессмысленно, а GitHub ограничивает анонимные запросы
CHECK_INTERVAL_SEC = 24 * 3600

DOWNLOAD_TIMEOUT_SEC = 600


@dataclass
class UpdateInfo:
    """Что известно про доступную версию."""

    version: str
    url: str = ""
    size: int = 0
    sha256: str = ""
    notes: str = ""
    published_at: str = ""
    page: str = RELEASES_PAGE

    def dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UpdateState:
    """Что показываем в панели и трее, не дёргая сеть."""

    current: str = ""
    available: UpdateInfo | None = None
    last_check: float = 0.0
    last_error: str = ""
    skipped: str = ""           # версия, от которой пользователь отказался
    downloading: bool = False
    progress: int = 0           # 0..100
    installable: bool = False   # есть чем обновлять (собранная копия + ссылка)

    def dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["available"] = self.available.dict() if self.available else None
        data["from_sources"] = not paths.is_frozen()
        return data


def parse_version(text: str) -> tuple[int, ...]:
    """«v1.2.3» → (1, 2, 3). Нечисловые хвосты вроде «-beta» отбрасываются."""
    cleaned = (text or "").strip().lstrip("vV")
    parts = re.findall(r"\d+", cleaned.split("-")[0].split("+")[0])
    return tuple(int(p) for p in parts[:4]) or (0,)


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


class Updater:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state = UpdateState(current=paths.version())
        self._quit_handler: Callable[[], None] | None = None
        self._load_state()

    # ── состояние на диске ─────────────────────────────────────────────────
    def _load_state(self) -> None:
        if not os.path.exists(STATE_FILE):
            return
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception as e:  # noqa: BLE001 — файл кэша, не настройки
            logger.warning(f"Не удалось прочитать {STATE_FILE}: {e}")
            return

        self.state.last_check = float(data.get("last_check", 0) or 0)
        self.state.skipped = str(data.get("skipped", "") or "")
        payload = data.get("available")
        if isinstance(payload, dict) and payload.get("version"):
            self.state.available = UpdateInfo(**{
                k: v for k, v in payload.items() if k in UpdateInfo.__dataclass_fields__
            })
        self._refresh_flags()

    def _save_state(self) -> None:
        payload = {
            "last_check": self.state.last_check,
            "skipped": self.state.skipped,
            "available": self.state.available.dict() if self.state.available else None,
        }
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            tmp = f"{STATE_FILE}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, STATE_FILE)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Не удалось сохранить {STATE_FILE}: {e}")

    def _refresh_flags(self) -> None:
        info = self.state.available
        self.state.installable = bool(paths.is_frozen() and info and info.url)

    # ── проверка ───────────────────────────────────────────────────────────
    @property
    def due(self) -> bool:
        """Пора ли проверять: раз в сутки."""
        return (time.time() - self.state.last_check) > CHECK_INTERVAL_SEC

    async def check(self, force: bool = False) -> UpdateState:
        """Спрашивает источник о последней версии."""
        if not force and not self.due:
            return self.state

        source = (settings_store.get("update_url") or "").strip()
        try:
            info = await (self._fetch_json_manifest(source) if source else self._fetch_github())
        except Exception as e:  # noqa: BLE001 — сеть, лимиты, формат
            self.state.last_error = str(e)
            self.state.last_check = time.time()
            self._save_state()
            logger.warning(f"Проверка обновлений не удалась: {e}")
            return self.state

        self.state.last_error = ""
        self.state.last_check = time.time()
        self.state.current = paths.version()
        self.state.available = info if info and is_newer(info.version, self.state.current) else None
        self._refresh_flags()
        self._save_state()

        if self.state.available:
            logger.info(f"Доступно обновление {self.state.available.version}")
        return self.state

    async def _fetch_github(self) -> UpdateInfo | None:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(GITHUB_LATEST, headers=headers)
            if response.status_code == 404:
                return None  # релизов ещё нет — это не ошибка
            response.raise_for_status()
            release = response.json()

        asset = next(
            (a for a in release.get("assets", []) if str(a.get("name", "")).lower().endswith("setup.exe")),
            None,
        )
        digest = str((asset or {}).get("digest", ""))
        return UpdateInfo(
            version=str(release.get("tag_name") or release.get("name") or "").lstrip("vV"),
            url=str((asset or {}).get("browser_download_url", "")),
            size=int((asset or {}).get("size", 0) or 0),
            sha256=digest.split(":", 1)[1] if digest.startswith("sha256:") else "",
            notes=str(release.get("body", "") or "")[:2000],
            published_at=str(release.get("published_at", "") or ""),
            page=str(release.get("html_url") or RELEASES_PAGE),
        )

    async def _fetch_json_manifest(self, url: str) -> UpdateInfo | None:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        if not isinstance(data, dict) or not data.get("version"):
            raise ValueError("В манифесте нет поля version")
        return UpdateInfo(
            version=str(data["version"]).lstrip("vV"),
            url=str(data.get("url", "")),
            size=int(data.get("size", 0) or 0),
            sha256=str(data.get("sha256", "")),
            notes=str(data.get("notes", ""))[:2000],
            page=str(data.get("page", url)),
        )

    def skip(self, version: str) -> UpdateState:
        """Больше не напоминать про эту версию."""
        self.state.skipped = version
        self._save_state()
        return self.state

    @property
    def should_notify(self) -> bool:
        info = self.state.available
        return bool(info and info.version != self.state.skipped)

    # ── установка ──────────────────────────────────────────────────────────
    async def install(self, progress: Callable[[int], Any] | None = None) -> str:
        """Скачивает установщик и запускает тихую установку.

        Возвращает путь к скачанному файлу. Приложение после этого завершается:
        установщик всё равно закрыл бы его сам, но уже грубо — через taskkill.
        """
        info = self.state.available
        if not info or not info.url:
            raise RuntimeError("Нечего устанавливать: обновление не найдено.")
        if not paths.is_frozen():
            raise RuntimeError(
                "Программа запущена из исходников — обновляйтесь через git pull и пересборку."
            )
        if self.state.downloading:
            raise RuntimeError("Загрузка уже идёт.")

        with self._lock:
            self.state.downloading = True
            self.state.progress = 0

        try:
            path = await self._download(info, progress)
        finally:
            with self._lock:
                self.state.downloading = False

        self._launch_installer(path)
        return path

    async def _download(self, info: UpdateInfo, progress: Callable[[int], Any] | None) -> str:
        target = os.path.join(tempfile.gettempdir(), f"AtomTerminalPet-{info.version}-setup.exe")
        digest = hashlib.sha256()
        received = 0

        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_SEC, follow_redirects=True) as client:
            async with client.stream("GET", info.url) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length") or info.size or 0)

                with open(target, "wb") as f:
                    async for chunk in response.aiter_bytes(256 * 1024):
                        f.write(chunk)
                        digest.update(chunk)
                        received += len(chunk)
                        if total:
                            percent = min(100, int(received * 100 / total))
                            if percent != self.state.progress:
                                self.state.progress = percent
                                if progress:
                                    await _maybe_await(progress(percent))

        if info.size and received != info.size:
            os.remove(target)
            raise RuntimeError(f"Размер не совпал: ждали {info.size} байт, получили {received}")

        if info.sha256 and digest.hexdigest().lower() != info.sha256.lower():
            os.remove(target)
            raise RuntimeError("Контрольная сумма не совпала — файл повреждён или подменён.")

        logger.info(f"Установщик скачан: {target} ({received} байт)")
        return target

    def _launch_installer(self, path: str) -> None:
        """Запускает установщик с повышением прав и просит приложение закрыться."""
        import ctypes

        params = "/SILENT /NOCANCEL /NORESTART /CLOSEAPPLICATIONS"
        # Установщику нужны права администратора (правило брандмауэра), поэтому
        # обычный CreateProcess вернул бы «требуется повышение прав» — только ShellExecute.
        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", path, params, None, 1)
        if int(result) <= 32:
            raise RuntimeError(
                "Не удалось запустить установщик (код %s). Возможно, вы отклонили запрос прав." % result
            )

        threading.Timer(1.5, self._quit).start()

    def set_quit_handler(self, handler: Callable[[], None]) -> None:
        """Трей сообщает, как себя корректно закрыть."""
        self._quit_handler = handler

    def _quit(self) -> None:
        if self._quit_handler is None:
            logger.info("Выход при обновлении не настроен — установщик закроет программу сам")
            return
        try:
            self._quit_handler()
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка при закрытии перед обновлением")


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


updater = Updater()
