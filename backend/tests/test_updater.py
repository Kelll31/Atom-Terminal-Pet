"""Тесты обновления: сравнение версий, разбор релиза, состояние."""

import pytest

from core import paths, updater as updater_module
from core.updater import UpdateInfo, Updater, is_newer, parse_version


def test_version_parsing_ignores_prefix_and_suffix():
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("1.2.3-beta.2") == (1, 2, 3)
    assert parse_version("2.0") == (2, 0)
    assert parse_version("") == (0,)


def test_newer_version_detection():
    assert is_newer("1.1.0", "1.0.0")
    assert is_newer("1.0.1", "1.0.0")
    assert is_newer("2.0", "1.9.9")
    assert not is_newer("1.0.0", "1.0.0")
    assert not is_newer("0.9.9", "1.0.0")
    # Собранная копия без файла VERSION считает себя 0.0.0 — иначе обновление
    # предлагалось бы бесконечно
    assert is_newer("1.0.0", "0.0.0")


def test_same_version_is_not_offered(tmp_path, monkeypatch):
    monkeypatch.setattr(updater_module, "STATE_FILE", str(tmp_path / "update.json"))
    instance = Updater()
    instance.state.current = "1.0.0"

    async def fake_fetch():
        return UpdateInfo(version="1.0.0", url="http://example/setup.exe")

    monkeypatch.setattr(instance, "_fetch_github", fake_fetch)
    state = _run(instance.check(force=True))

    assert state.available is None
    assert state.last_error == ""


def test_newer_version_is_offered_and_remembered(tmp_path, monkeypatch):
    state_file = tmp_path / "update.json"
    monkeypatch.setattr(updater_module, "STATE_FILE", str(state_file))
    instance = Updater()
    instance.state.current = "1.0.0"
    monkeypatch.setattr(paths, "version", lambda: "1.0.0")

    async def fake_fetch():
        return UpdateInfo(version="1.4.0", url="http://example/setup.exe", size=10)

    monkeypatch.setattr(instance, "_fetch_github", fake_fetch)
    state = _run(instance.check(force=True))

    assert state.available is not None
    assert state.available.version == "1.4.0"
    assert instance.should_notify
    # Состояние переживает перезапуск: трей показывает обновление сразу
    assert state_file.exists()


def test_skipped_version_stops_nagging(tmp_path, monkeypatch):
    monkeypatch.setattr(updater_module, "STATE_FILE", str(tmp_path / "update.json"))
    instance = Updater()
    instance.state.available = UpdateInfo(version="1.4.0", url="http://example/setup.exe")

    assert instance.should_notify
    instance.skip("1.4.0")
    assert not instance.should_notify


def test_install_refuses_from_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(updater_module, "STATE_FILE", str(tmp_path / "update.json"))
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    instance = Updater()
    instance.state.available = UpdateInfo(version="1.4.0", url="http://example/setup.exe")

    with pytest.raises(RuntimeError, match="из исходников"):
        _run(instance.install())


def test_install_refuses_without_update(tmp_path, monkeypatch):
    monkeypatch.setattr(updater_module, "STATE_FILE", str(tmp_path / "update.json"))
    instance = Updater()

    with pytest.raises(RuntimeError, match="Нечего устанавливать"):
        _run(instance.install())


def test_state_is_json_serializable(tmp_path, monkeypatch):
    monkeypatch.setattr(updater_module, "STATE_FILE", str(tmp_path / "update.json"))
    instance = Updater()
    instance.state.available = UpdateInfo(version="1.4.0", url="http://example/setup.exe")

    data = instance.state.dict()
    assert data["available"]["version"] == "1.4.0"
    assert "from_sources" in data


def _run(coro):
    import asyncio

    return asyncio.run(coro)
