import os
import asyncio
import io
import speech_recognition as sr
import edge_tts
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

from config import SystemSettings, MCPSettings
from mcp_tools import get_active_tools

class AICompanionAgent:
    def __init__(self, settings: SystemSettings):
        self.settings = settings
        self.chat_history = []
        self.recognizer = sr.Recognizer()
        self._init_llm()

    def _init_llm(self):
        tools = get_active_tools(self.settings.mcp_tools)
        self.tools_dict = {tool.name: tool for tool in tools}
        
        if self.settings.llm_provider == "openai" and self.settings.openai_api_key:
            llm = ChatOpenAI(
                model="gpt-3.5-turbo", 
                temperature=0.7, 
                api_key=self.settings.openai_api_key
            )
        elif self.settings.llm_provider == "openrouter" and self.settings.openrouter_api_key:
            llm = ChatOpenAI(
                model=self.settings.openrouter_model or "openai/gpt-4o-mini",
                base_url="https://openrouter.ai/api/v1",
                api_key=self.settings.openrouter_api_key,
                temperature=0.7
            )
        elif self.settings.llm_provider == "local":
            llm = ChatOllama(
                base_url=self.settings.local_llm_url,
                model="llama3",
                temperature=0.7
            )
        else:
            llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7, api_key="dummy")

        if tools and hasattr(llm, "bind_tools"):
            self.llm_with_tools = llm.bind_tools(tools)
        else:
            self.llm_with_tools = llm

        full_system_prompt = (
            f"Тебя зовут {self.settings.pet_name}. Ты живой, умный и верный ИИ-питомец и цифровой компаньон.\n"
            f"ВАЖНО: Твоя кличка — '{self.settings.pet_name}'. Когда пользователь зовёт тебя по имени (Атом, Атомчик, Привет Атом), "
            f"ты ВСЕГДА реагируешь с радостью, энергией и готовностью помочь! Отвечай коротко, емко и дружелюбно."
        )
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", full_system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("user", "{input}"),
        ])

    def update_settings(self, settings: SystemSettings):
        self.settings = settings
        self._init_llm()

    async def process_audio(self, audio_data: bytes) -> tuple:
        """
        1. STT (Audio bytes -> Text)
        2. LLM (Text -> Reply + Emotion)
        3. TTS (Reply -> Audio filepath)
        Returns (output_file, reply_text, emotion).
        """
        text = self._stt(audio_data)
        if not text:
            return None, "Не удалось распознать речь.", "sad"

        reply, emotion = await self._get_llm_response(text)
        output_file = await self._tts(reply)
        return output_file, reply, emotion

    async def process_text(self, text: str) -> tuple:
        """Process text input directly (from PC Microphone / Web UI)."""
        reply, emotion = await self._get_llm_response(text)
        output_file = await self._tts(reply)
        return output_file, reply, emotion

    def _stt(self, audio_data: bytes) -> str:
        """STT using SpeechRecognition with Google Web Speech API."""
        try:
            # Incoming audio is 16kHz 16-bit PCM
            audio = sr.AudioData(audio_data, 16000, 2)
            text = self.recognizer.recognize_google(audio, language="ru-RU")
            print(f"[STT RECOGNIZED]: {text}")
            return text
        except sr.UnknownValueError:
            return ""
        except Exception as e:
            print(f"STT Error: {e}")
            return ""

    def _is_name_called(self, text: str) -> bool:
        if not text:
            return False
        t = text.lower()
        p = self.settings.pet_name.lower().strip()
        variations = [p, p + "чик", p + "ка", p + "а", p + "у", p + "ом", "атон", "автом", "этом", "пэт", "пет", "atom"]
        for v in variations:
            if re.search(r'\b' + re.escape(v) + r'\b', t) or v in t:
                return True
        return False

    async def _get_llm_response(self, text: str) -> tuple:
        messages = self.prompt.format_messages(
            chat_history=self.chat_history,
            input=text
        )
        
        response = await self.llm_with_tools.ainvoke(messages)
        emotion = "happy"
        
        name_called = self._is_name_called(text)
        if name_called:
            emotion = "love"

        # Check if LLM requested tool execution (MCP tools)
        if hasattr(response, "tool_calls") and response.tool_calls:
            emotion = "tool"  # Emotion when MCP tools are executed!
            tool_outputs = []
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                if tool_name in self.tools_dict:
                    try:
                        tool_result = self.tools_dict[tool_name].invoke(tool_args)
                        tool_outputs.append(f"[{tool_name}]: {tool_result}")
                    except Exception as e:
                        tool_outputs.append(f"[{tool_name} error]: {e}")
            
            reply_text = response.content or "Выполняю команду!"
            if tool_outputs:
                reply = (reply_text + "\n" + "\n".join(tool_outputs)).strip()
            else:
                reply = reply_text
        else:
            reply = response.content
            if not name_called:
                txt = (text + " " + reply).lower()
                if any(word in txt for word in ["зл", "бес", "гнев", "ненави", "ярост"]):
                    emotion = "angry"
                elif any(word in txt for word in ["крут", "стиль", "очки", "йоу"]):
                    emotion = "cool"
                elif any(word in txt for word in ["спать", "сон", "устал", "зева", "ночь", "спокойн"]):
                    emotion = "sleepy"
                elif any(word in txt for word in ["вечерин", "праздн", "тусов", "танц", "пати"]):
                    emotion = "party"
                elif any(word in txt for word in ["голов", "круж", "непон", "сложн", "странн"]):
                    emotion = "dizzy"
                elif any(word in txt for word in ["ешь", "еда", "вкусн", "ням", "куша"]):
                    emotion = "eating"
                elif any(word in txt for word in ["груст", "плохо", "печаль", "ошибк", "жаль"]):
                    emotion = "sad"
                elif any(word in txt for word in ["люб", "мил", "сердц", "целу"]):
                    emotion = "love"
                else:
                    emotion = "talking"

        # Keep history short
        self.chat_history.append(HumanMessage(content=text))
        self.chat_history.append(AIMessage(content=reply))
        if len(self.chat_history) > 10:
            self.chat_history = self.chat_history[-10:]
            
        return reply, emotion

    async def _tts(self, text: str) -> str:
        """Convert text to speech using edge-tts."""
        output_filename = "response.mp3"
        communicate = edge_tts.Communicate(text, "ru-RU-SvetlanaNeural")
        await communicate.save(output_filename)
        return output_filename

