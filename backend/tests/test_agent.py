"""Тесты агента: обращение по имени, системный промпт, цикл вызова инструментов."""

from langchain_core.messages import AIMessage

from ai.agent import AtomAgent, is_wake_word_present, load_system_prompt, tools_snapshot
from core.settings import settings_store


def test_wake_word_detection(monkeypatch):
    monkeypatch.setattr(settings_store.current, "require_wake_word", True)
    monkeypatch.setattr(settings_store.current, "pet_name", "Атом")
    monkeypatch.setattr(settings_store.current, "wake_words", ["атом", "atom"])

    assert is_wake_word_present("Атом, открой проект")
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
