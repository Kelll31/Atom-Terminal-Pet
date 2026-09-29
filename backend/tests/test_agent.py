"""Тесты агента: обращение по имени, системный промпт, цикл вызова инструментов."""

from langchain_core.messages import AIMessage

from ai.agent import AtomAgent, is_wake_word_present, load_system_prompt, tools_snapshot
from core.settings import settings_store


def test_wake_word_detection(monkeypatch):
    monkeypatch.setattr(settings_store.current, "require_wake_word", True)
    monkeypatch.setattr(settings_store.current, "pet_name", "Патрик")
    monkeypatch.setattr(settings_store.current, "wake_words", ["Патрик", "atom"])

    assert is_wake_word_present("Патрик, открой проект")
    assert is_wake_word_present("эй atom что там с диском")
    assert not is_wake_word_present("надо бы кофе выпить")


def test_wake_word_can_be_disabled(monkeypatch):
    monkeypatch.setattr(settings_store.current, "require_wake_word", False)
    assert is_wake_word_present("любая фраза")


def test_system_prompt_includes_context_and_autonomy(monkeypatch):
    monkeypatch.setattr(settings_store.current, "autonomy", "auto_safe")
    monkeypatch.setattr(settings_store.current, "allowed_roots", ["D:/projects"])

    prompt = load_system_prompt({"cpu": 77, "ram": 40, "gpu": 10, "temp": 65, "spotify": "тишина"})

    assert "77" in prompt
    assert "D:/projects" in prompt
    assert "РЕЖИМ АВТОНОМИИ" in prompt


def test_tools_snapshot_lists_local_tools():
    names = {tool["name"] for tool in tools_snapshot()}
    assert {"get_pc_status", "read_file", "run_command", "express_emotion"} <= names


class FakeLLM:
    """Модель, которая сначала зовёт инструмент, потом отвечает текстом."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return self.script.pop(0)


class RecordingContext:
    def __init__(self):
        self.task_id = "t1"
        self.steps = []

    async def emit(self, action, **payload):
        pass

    async def add_step(self, step_type, **payload):
        self.steps.append((step_type, payload))
        return f"s{len(self.steps)}"

    async def request_approval(self, tool, args, risk, description):
        return True


async def test_agent_executes_tool_then_answers(monkeypatch):
    tool_call = AIMessage(
        content="",
        tool_calls=[{"name": "express_emotion", "args": {"emotion": "happy"}, "id": "call_1"}],
    )
    final = AIMessage(content="Готово, показал радость.")
    fake = FakeLLM([tool_call, final])

    monkeypatch.setattr("ai.agent.build_llm", lambda with_tools=True: fake)

    emitted = []

    class FakeBus:
        async def emit(self, action, **payload):
            emitted.append(action)

        async def set_emotion(self, emotion, text=""):
            emitted.append(f"emotion:{emotion}")

    monkeypatch.setattr("core.events.bus", FakeBus())

    agent = AtomAgent()
    ctx = RecordingContext()
    result = await agent.run("порадуйся", ctx)

    assert result == "Готово, показал радость."
    assert [kind for kind, _ in ctx.steps] == ["tool_call", "tool_result"]
    assert ctx.steps[1][1]["ok"] is True
    assert len(agent.history) == 2


class StreamingLLM:
    """Модель, отдающая ответ по кускам, как настоящий провайдер."""

    def __init__(self, pieces):
        self.pieces = pieces

    async def astream(self, messages):
        from langchain_core.messages import AIMessageChunk

        for piece in self.pieces:
            yield AIMessageChunk(content=piece)

    async def ainvoke(self, messages):
        return AIMessage(content="".join(self.pieces))


async def test_agent_speaks_sentences_while_model_still_writes(monkeypatch):
    """Живой режим: первое предложение звучит до конца генерации."""
    llm = StreamingLLM(["Готово. ", "Нашёл два ", "процесса. ", "Что дальше?"])
    monkeypatch.setattr("ai.agent.build_llm", lambda with_tools=True: llm)

    spoken: list[str] = []

    async def speaker(sentence: str) -> None:
        spoken.append(sentence)

    agent = AtomAgent()
    result = await agent.run("что там с процессами", RecordingContext(), speaker=speaker)

    assert spoken[0] == "Готово."
    assert "Что дальше?" in spoken[-1]
    assert agent.spoken_while_streaming is True
    assert result.startswith("Готово.")


async def test_agent_does_not_speak_when_tools_are_called(monkeypatch):
    """Если модель решила вызвать инструмент — сначала дело, а не болтовня."""
    from langchain_core.messages import AIMessageChunk

    class ToolStreamLLM:
        async def astream(self, messages):
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {"name": "recall", "args": "{}", "id": "c1", "index": 0, "type": "tool_call_chunk"}
                ],
            )

        async def ainvoke(self, messages):
            return AIMessage(content="", tool_calls=[{"name": "recall", "args": {}, "id": "c1"}])

    monkeypatch.setattr("ai.agent.build_llm", lambda with_tools=True: ToolStreamLLM())
    monkeypatch.setattr(settings_store.current, "max_steps", 1)

    spoken: list[str] = []

    async def speaker(sentence: str) -> None:
        spoken.append(sentence)

    agent = AtomAgent()
    await agent.run("вспомни всё", RecordingContext(), speaker=speaker)
    assert spoken == []


async def test_agent_stops_on_step_limit(monkeypatch):
    looping = [
        AIMessage(content="", tool_calls=[{"name": "recall", "args": {}, "id": f"c{i}"}])
        for i in range(5)
    ]
    fake = FakeLLM(looping)
    monkeypatch.setattr("ai.agent.build_llm", lambda with_tools=True: fake)
    monkeypatch.setattr(settings_store.current, "max_steps", 3)

    agent = AtomAgent()
    result = await agent.run("зациклись", RecordingContext())
    assert "лимит" in result.lower()
