"""После сборки раскладывает образы в web/public/firmware и обновляет манифест.

Манифест читает esp-web-tools во вкладке «Прошивка», поэтому набор файлов и
смещения должны совпадать с тем, что делает `esptool write_flash`. Раньше в
манифесте не было boot_app0.bin по адресу 0xE000: у таблицы разделов с двумя
областями под прошивку нет factory-раздела, и загрузчик после прошивки с нуля
выбирал область по неинициализированным данным otadata.
"""

import json
import os
import re
import shutil

Import("env")

# Смещения для ESP32-S3 (у ESP32 загрузчик лежит по 0x1000, у S3 — по 0x0)
PARTS = [
    ("bootloader.bin", 0x0000),
    ("partitions.bin", 0x8000),
    ("boot_app0.bin", 0xE000),
    ("firmware.bin", 0x10000),
]


def read_version(project_dir):
    config = os.path.join(project_dir, "src", "Config.h")
    try:
        with open(config, "r", encoding="utf-8") as handle:
            match = re.search(r'#define\s+FW_VERSION\s+"([^"]+)"', handle.read())
            if match:
                return match.group(1)
    except OSError:
        pass
    return "0.0.0"


def after_build(source, target, env):
    build_dir = env.subst("$BUILD_DIR")
    project_dir = env.subst("$PROJECT_DIR")
    target_dir = os.path.join(project_dir, "..", "web", "public", "firmware")
    os.makedirs(target_dir, exist_ok=True)

    framework_dir = env.PioPlatform().get_package_dir("framework-arduinoespressif32")
    boot_app0 = os.path.join(framework_dir, "tools", "partitions", "boot_app0.bin")

    sources = {
        "bootloader.bin": os.path.join(build_dir, "bootloader.bin"),
        "partitions.bin": os.path.join(build_dir, "partitions.bin"),
        "firmware.bin": os.path.join(build_dir, "firmware.bin"),
        "boot_app0.bin": boot_app0,
    }

    missing = []
    for name, path in sources.items():
        if not os.path.exists(path):
            missing.append(name)
            continue
        shutil.copy(path, os.path.join(target_dir, name))

    if missing:
        print(f"\033[91mcopy_bins: не найдены образы: {', '.join(missing)}\033[0m")
        return

    manifest = {
        "name": "Atom Terminal Pet",
        "version": read_version(project_dir),
        "new_install_prompt_erase": True,
        "builds": [
            {
                "chipFamily": "ESP32-S3",
                "parts": [{"path": name, "offset": offset} for name, offset in PARTS],
            }
        ],
    }
    with open(os.path.join(target_dir, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    print(f"\033[92mcopy_bins: образы и манифест обновлены в {target_dir}\033[0m")


env.AddPostAction("buildprog", after_build)
