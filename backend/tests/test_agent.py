import pytest
from langchain_core.messages import HumanMessage

from ai.agent import AgentState, analyze_intent, generate_response


@pytest.mark.asyncio
async def test_analyze_intent():
    # Test intent parsing
    state = AgentState(
        messages=[HumanMessage(content="открой блокнот")], pc_context={}, next_action=""
    )
    result = await analyze_intent(state)
    assert result["next_action"] == "execute_tool"

    state = AgentState(
        messages=[HumanMessage(content="как дела")], pc_context={}, next_action=""
    )
    result = await analyze_intent(state)
    assert result["next_action"] == "generate_response"


@pytest.mark.asyncio
async def test_generate_response():
    # Test wake word and bot name mapping
    state = AgentState(
        messages=[HumanMessage(content="как дела атом")], pc_context={}, next_action=""
    )
    result = await generate_response(state)
    msg = result["messages"][0].content
    assert "на связи" in msg or "Атом" in msg

    # Test lag handling
    state = AgentState(
        messages=[HumanMessage(content="лагает")],
        pc_context={"cpu": 95},
        next_action="",
    )
    result = await generate_response(state)
    msg = result["messages"][0].content
    assert "загружен почти на сотку" in msg
