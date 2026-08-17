import os
Import("env")

env_file = os.path.join(env.get("PROJECT_DIR"), "..", ".env")

if os.path.exists(env_file):
    print(f"Loading environment variables from {env_file}")
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k == "WIFI_SSID":
                    env.Append(CPPDEFINES=[("DEFAULT_WIFI_SSID", f'\\"{v}\\"')])
                elif k == "WIFI_PASS":
                    env.Append(CPPDEFINES=[("DEFAULT_WIFI_PASS", f'\\"{v}\\"')])
                elif k == "SERVER_IP":
                    env.Append(CPPDEFINES=[("DEFAULT_SERVER_IP", f'\\"{v}\\"')])
else:
    print(f"Warning: .env file not found at {env_file}. Using defaults.")
