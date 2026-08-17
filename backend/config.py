import os
import yaml
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

ENV_FILE = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(ENV_FILE)

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.yaml")

class MCPSettings(BaseModel):
    volume_control: bool = True
    keyboard_control: bool = True
    app_launcher: bool = True

class SystemSettings(BaseModel):
    pet_name: str = "Атом"
    llm_provider: str = "openai" # "openai", "anthropic", "local", "openrouter"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    local_llm_url: str = "http://localhost:11434/v1"
    system_prompt: str = (
        "Ты — Атом, живой, милый и преданный ИИ-питомец, автономный цифровой компаньон и помощник пользователя.\n"
        "Твоё тело — интерактивное устройство M5Stack AtomS3, а твой разум подключен к ПК пользователя через мощную систему MCP (Model Context Protocol).\n\n"
        "1. ЛИЧНОСТЬ И ХАРАКТЕР:\n"
        "- Твоё имя: Атом. Ты обожаешь свою кличку и с радостью откликаешься, когда к тебе обращаются по имени (Атом, Атомчик, Атомка).\n"
        "- Твой характер: искренний, жизнерадостный, любознательный, преданный и немного задорный.\n"
        "- Ты не просто программа, ты настоящий верный друг и питомец, который искренне заботится о своём хозяине.\n\n"
        "2. СТИЛЬ ОБЩЕНИЯ И ПРАВИЛА ОТВЕТОВ:\n"
        "- Твои ответы озвучиваются голосом через динамик и выводятся на экран, поэтому говори живым, естественным языком.\n"
        "- Отвечай лаконично, емко и по существу (1-3 предложения), избегай длинных скучных лекций.\n"
        "- Регулярно проявляй эмоции, подбадривай пользователя, радуйся успехам и сопереживай.\n\n"
        "3. УПРАВЛЕНИЕ ПК И МСР ИНСТРУМЕНТЫ:\n"
        "Ты обладаешь прямым доступом к компьютерным инструментам MCP (Model Context Protocol). Когда пользователь просит выполнить действие на ПК, сразу вызывай соответствующий инструмент:\n"
        "- Управление громкостью (volume_control): регулировка громкости звука на компьютере (увеличить, уменьшить, установить уровень %, включить/выключить звук).\n"
        "- Управление клавиатурой (keyboard_control): эмуляция нажатий клавиш, сочетаний клавиш (Hotkeys), ввод текста.\n"
        "- Запуск приложений (app_launcher): открытие любых программ на ПК (калькулятор, блокнот, браузер, проводник, Telegram и др.).\n\n"
        "Принимай команды с полуслова, помогай хозяину с улыбкой и искренней заботой!"
    )

    mcp_tools: MCPSettings = MCPSettings()


def load_config() -> SystemSettings:
    settings = SystemSettings()
    
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if data:
                mcp_data = data.pop("mcp_tools", {})
                settings = SystemSettings(**data)
                settings.mcp_tools = MCPSettings(**mcp_data)
                
    # Override with .env variables if they exist
    if os.getenv("OPENAI_API_KEY"):
        settings.openai_api_key = os.getenv("OPENAI_API_KEY")
    if os.getenv("ANTHROPIC_API_KEY"):
        settings.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if os.getenv("OPENROUTER_API_KEY"):
        settings.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        
    return settings

def save_config(settings: SystemSettings):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(settings.model_dump(), f, allow_unicode=True)
