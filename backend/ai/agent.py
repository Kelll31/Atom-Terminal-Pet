import logging
import operator
from collections.abc import Sequence
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
import yaml
from core.mcp_client import mcp_manager
from mcp_tools import get_active_tools

# from langchain_openai import ChatOpenAI
from langchain_openai import ChatOpenAI
from monitor.pc_monitor import pc_monitor

logger = logging.getLogger("ai.agent")


# 1. Define State
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    pc_context: dict  # Snapshot of current PC metrics
    next_action: str


# 2. Define Nodes
async def analyze_intent(state: AgentState) -> dict:
    """Analyze the user's input and decide whether to use a tool or just respond."""
    logger.info("Node: analyze_intent")
    messages = state["messages"]
    last_msg = messages[-1].content

    # In a real app, an LLM call here would determine intent
    # Example logic: if "search" in last_msg, use tool.
    if (
        "открой" in last_msg.lower()
        or "найди" in last_msg.lower()
        or "напомни" in last_msg.lower()
    ):
        return {"next_action": "execute_tool"}

    return {"next_action": "generate_response"}


async def execute_tool(state: AgentState) -> dict:
    """Execute a local PC tool (mcp_tools)"""
    logger.info("Node: execute_tool")
    # Execute tool logic here (e.g. opening a program)
    tool_result = "Tool executed successfully."

    # Append tool result to messages so LLM knows it was done
    return {
        "messages": [SystemMessage(content=f"Tool Result: {tool_result}")],
        "next_action": "generate_response",
    }


import json
import os

SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "settings.json"
)


def get_pet_name():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("pet_name", "Атом")
        except Exception:
            pass
    return "Атом"


async def generate_response(state: AgentState) -> dict:
    """Generate the final response string using an LLM, given the PC context."""
    logger.info("Node: generate_response")

    pc_ctx = state.get("pc_context", {})
    # Load system prompt from config
    prompt_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "prompts.yaml")
    sys_prompt = "You are a helpful AI."
    if os.path.exists(prompt_file):
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                prompt_data = yaml.safe_load(f)
                sys_prompt = prompt_data.get("system_prompt", sys_prompt)
        except Exception as e:
            logger.error(f"Failed to load prompts.yaml: {e}")

    # Inject variables
    sys_prompt = sys_prompt.format(
        cpu=pc_ctx.get("cpu", 0),
        ram=pc_ctx.get("ram", 0),
        gpu=pc_ctx.get("gpu", 0),
        temp=pc_ctx.get("temp", 0)
    )

    settings = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except Exception:
            pass

    api_key = settings.get("api_key")
    if api_key:
        try:
            headers = {}
            base_url = settings.get("base_url")
            if base_url and "openrouter.ai" in base_url.lower():
                headers = {
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "Atom-Terminal-Pet"
                }

            llm = ChatOpenAI(
                api_key=api_key,
                base_url=base_url or None,
                model=settings.get("model_name") or "gpt-3.5-turbo",
                default_headers=headers
            )
            
            # Bind tools
            all_tools = get_active_tools() + mcp_manager.langchain_tools
            if all_tools:
                llm = llm.bind_tools(all_tools)

            # Make sure we only pass the most recent messages to prevent context overflow
            messages_to_send = [SystemMessage(content=sys_prompt)] + list(state['messages'])[-5:]
            response = await llm.ainvoke(messages_to_send)
            return {"messages": [AIMessage(content=response.content)]}
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            # Fallback to mock if API fails

    last_user_msg = state["messages"][0].content if state["messages"] else ""
    msg_lower = last_user_msg.lower()

    pet_name = get_pet_name()
    pet_name_lower = pet_name.lower()

    # Check for wake word / pet name calls
    if any(
        name in msg_lower
        for name in [pet_name_lower, "атом", "atom", "петя", "pet", "микро", "micro"]
    ):
        bot_name = (
            pet_name
            if pet_name_lower in msg_lower
            else ("Микро" if "микро" in msg_lower or "micro" in msg_lower else "Атом")
        )
        if "как дела" in msg_lower or "как ты" in msg_lower:
            response_text = f"{bot_name} на связи! Отлично себя чувствую, системные показатели в норме!"
        elif "кто ты" in msg_lower or "как тебя зовут" in msg_lower:
            response_text = f"Привет! Я {bot_name} — твой верный ИИ-питомец и помощник!"
        else:
            response_text = f"Да! {bot_name} на связи! Я готов к работе."
    elif "лагает" in msg_lower and pc_ctx.get("cpu", 0) > 80:
        response_text = (
            "Твой процессор загружен почти на сотку! Давай закроем лишние вкладки?"
        )
    else:
        response_text = "Я тебя понял! Все системы работают в штатном режиме."

    return {"messages": [AIMessage(content=response_text)]}


# 3. Define routing function
def route_action(state: AgentState) -> Literal["execute_tool", "generate_response"]:
    if state.get("next_action") == "execute_tool":
        return "execute_tool"
    return "generate_response"


# 4. Build Graph
workflow = StateGraph(AgentState)

workflow.add_node("analyze_intent", analyze_intent)
workflow.add_node("execute_tool", execute_tool)
workflow.add_node("generate_response", generate_response)

workflow.set_entry_point("analyze_intent")

workflow.add_conditional_edges(
    "analyze_intent",
    route_action,
    {"execute_tool": "execute_tool", "generate_response": "generate_response"},
)
workflow.add_edge("execute_tool", "generate_response")
workflow.add_edge("generate_response", END)

app_graph = workflow.compile()


async def process_user_input(text: str) -> str | None:
    """Entry point for the backend to pass STT text into the agent."""
    
    # Wake word check
    msg_lower = text.lower()
    pet_name_lower = get_pet_name().lower()
    wake_words = [pet_name_lower, "атом", "atom", "петя", "pet", "микро", "micro", "а там", "о том", "потом"]
    
    if not any(w in msg_lower for w in wake_words):
        logger.info(f"Ignored speech (no wake word): {text}")
        return None

    # Capture current PC state from monitor
    current_metrics = {
        "cpu": pc_monitor.get_gpu_usage(),  # using as placeholder
        "ram": 50,
        "gpu": 10,
        "temp": pc_monitor.get_cpu_temp(),
        "spotify": "None",
    }

    # We could await collect_metrics, but it's fine to fetch latest known state
    state_input = {
        "messages": [HumanMessage(content=text)],
        "pc_context": current_metrics,
        "next_action": "",
    }

    # Run graph
    result = await app_graph.ainvoke(state_input)

    # Extract final AIMessage
    final_message = result["messages"][-1].content
    return final_message
