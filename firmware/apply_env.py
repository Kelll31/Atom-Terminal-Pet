"""Подставляет значения из ../.env в прошивку как значения по умолчанию.

Адрес сервера зашивается всегда — он не секрет и экономит одну настройку.

Пароль от Wi-Fi по умолчанию НЕ зашивается. Собранный firmware.bin копируется
в web/public/firmware и раздаётся панелью по HTTP, а сам файл лежит в git, —
то есть строка пароля внутри прошивки утекает всем, у кого есть доступ к панели
или к репозиторию. Достать её из бинарника можно обычным `strings`.

Штатный путь передачи Wi-Fi — по USB из вкладки «Прошивка»: устройство
сохраняет сеть в NVS, и в образе её нет.

Если для отладки всё же нужно зашить сеть в образ, добавьте в .env строку:

    EMBED_WIFI=1
"""

import os

Import("env")

env_file = os.path.join(env.get("PROJECT_DIR"), "..", ".env")

if not os.path.exists(env_file):
    print(f"apply_env: .env не найден ({env_file}), беру значения по умолчанию")
else:
    values = {}
    with open(env_file, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()

    server_ip = values.get("SERVER_IP")
    if server_ip:
        env.Append(CPPDEFINES=[("DEFAULT_SERVER_IP", f'\\"{server_ip}\\"')])

    embed_wifi = values.get("EMBED_WIFI", "").lower() in ("1", "true", "yes")
    ssid = values.get("WIFI_SSID")
    password = values.get("WIFI_PASS")

    if embed_wifi and ssid:
        env.Append(CPPDEFINES=[("DEFAULT_WIFI_SSID", f'\\"{ssid}\\"')])
        if password:
            env.Append(CPPDEFINES=[("DEFAULT_WIFI_PASS", f'\\"{password}\\"')])
        print(
            "\033[91mapply_env: EMBED_WIFI=1 — пароль от Wi-Fi попадёт в firmware.bin "
            "в открытом виде. Не коммитьте этот образ и не раздавайте его панелью.\033[0m"
        )
    elif ssid:
        print(
            "apply_env: Wi-Fi в образ не зашит (так безопаснее). "
            "Передайте сеть устройству по USB на вкладке «Прошивка» "
            "или поставьте EMBED_WIFI=1 в .env."
        )
