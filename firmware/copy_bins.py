Import("env")
import os
import shutil

def after_build(source, target, env):
    print("Running copy_bins.py...")
    
    # Пути к скомпилированным бинарникам
    build_dir = env.subst("$BUILD_DIR")
    firmware_bin = os.path.join(build_dir, "firmware.bin")
    partitions_bin = os.path.join(build_dir, "partitions.bin")
    bootloader_bin = os.path.join(build_dir, "bootloader.bin")
    
    # Целевая папка веб-сервера
    project_dir = env.subst("$PROJECT_DIR")
    target_dir = os.path.join(project_dir, "..", "web", "public", "firmware")
    
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    # Копирование
    try:
        shutil.copy(firmware_bin, os.path.join(target_dir, "firmware.bin"))
        shutil.copy(partitions_bin, os.path.join(target_dir, "partitions.bin"))
        shutil.copy(bootloader_bin, os.path.join(target_dir, "bootloader.bin"))
        print(f"\033[92mSuccessfully copied .bin files to {target_dir}\033[0m")
    except Exception as e:
        print(f"\033[91mError copying .bin files: {e}\033[0m")

# Привязываем выполнение функции после успешной сборки
env.AddPostAction("buildprog", after_build)
