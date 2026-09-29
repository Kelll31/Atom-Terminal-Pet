"""Тесты окна панели: каким способом открывается и не плодятся ли окна."""

import panel_window


def test_existing_window_is_raised_instead_of_new_one(monkeypatch):
    monkeypatch.setattr(panel_window, "focus_existing", lambda: True)
    monkeypatch.setattr(
        panel_window, "_spawn_window_process", lambda url: pytest_fail("окно открыли дважды")
    )

    assert panel_window.open_panel("http://127.0.0.1:8000") == "focus"


def test_own_window_is_preferred(monkeypatch):
    monkeypatch.setattr(panel_window, "focus_existing", lambda: False)
    monkeypatch.setattr(panel_window, "_webview_available", lambda: True)

    launched = []
    monkeypatch.setattr(panel_window.subprocess, "Popen", lambda cmd, **kw: launched.append(cmd))

    assert panel_window.open_panel("http://127.0.0.1:8000") == "window"
    assert panel_window.PANEL_FLAG in launched[0]
    assert launched[0][-1] == "http://127.0.0.1:8000"


def test_falls_back_to_app_mode_without_pywebview(monkeypatch):
    monkeypatch.setattr(panel_window, "focus_existing", lambda: False)
    monkeypatch.setattr(panel_window, "_webview_available", lambda: False)
    monkeypatch.setattr(panel_window, "_app_mode_browsers", lambda: ["msedge.exe"])

    launched = []
    monkeypatch.setattr(panel_window.subprocess, "Popen", lambda cmd, **kw: launched.append(cmd))

    assert panel_window.open_panel("http://127.0.0.1:8000") == "app"
    # Режим приложения — это окно без вкладок и адресной строки
    assert "--app=http://127.0.0.1:8000" in launched[0]


def test_browser_is_the_last_resort(monkeypatch):
    monkeypatch.setattr(panel_window, "focus_existing", lambda: False)
    monkeypatch.setattr(panel_window, "_webview_available", lambda: False)
    monkeypatch.setattr(panel_window, "_app_mode_browsers", lambda: [])

    opened = []
    monkeypatch.setattr(panel_window.webbrowser, "open", lambda url: opened.append(url))

    assert panel_window.open_panel("http://127.0.0.1:8000") == "browser"
    assert opened == ["http://127.0.0.1:8000"]


def pytest_fail(message: str):
    raise AssertionError(message)
