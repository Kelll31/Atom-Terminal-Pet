import operator
from typing import Annotated, Sequence, TypedDict, Literal
import logging

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
# Note: In a real implementation, you'd use a ChatModel (e.g. ChatOpenAI, ChatAnthropic)
# from langchain_openai import ChatOpenAI

from monitor.pc_monitor import pc_monitor

logger = logging.getLogger("ai.agent")

# 1. Define State
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    pc_context: dict # Snapshot of current PC metrics
    next_action: str

# 2. Define Nodes
async def analyze_intent(state: AgentState) -> dict:
    """Analyze the user's input and decide whether to use a tool or just respond."""
    logger.info("Node: analyze_intent")
    messages = state['messages']
    last_msg = messages[-1].content
    
    # In a real app, an LLM call here would determine intent
    # Example logic: if "search" in last_msg, use tool.
    if "открой" in last_msg.lower() or "найди" in last_msg.lower() or "напомни" in last_msg.lower():
        return {"next_action": "execute_tool"}
    
    return {"next_action": "generate_response"}

async def execute_tool(state: AgentState) -> dict:
    """Execute a local PC tool (mcp_tools)"""
    logger.info("Node: execute_tool")
    # Execute tool logic here (e.g. opening a program)
    tool_result = "Tool executed successfully."
    
    # Append tool result to messages so LLM knows it was done
    return {"messages": [SystemMessage(content=f"Tool Result: {tool_result}")], "next_action": "generate_response"}

async def generate_response(state: AgentState) -> dict:
    """Generate the final response string using an LLM, given the PC context."""
    logger.info("Node: generate_response")
    
    pc_ctx = state.get("pc_context", {})
    sys_prompt = f"""You are a helpful AI desktop pet. 
Current PC State: CPU: {pc_ctx.get('cpu')}%, RAM: {pc_ctx.get('ram')}%, GPU: {pc_ctx.get('gpu')}%, Temp: {pc_ctx.get('temp')}C. 
Now playing: {pc_ctx.get('spotify', 'Nothing')}
"""
    
    # Mock LLM generation
    # real_llm = ChatOpenAI(temperature=0.7)
    # response = await real_llm.ainvoke([SystemMessage(content=sys_prompt)] + state['messages'])
    
    last_user_msg = state['messages'][0].content if state['messages'] else ""
    if "лагает" in last_user_msg.lower() and pc_ctx.get('cpu', 0) > 80:
        response_text = "Твой процессор загружен почти на сотку! Давай закроем лишние вкладки?"
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
    {
        "execute_tool": "execute_tool",
        "generate_response": "generate_response"
    }
)
workflow.add_edge("execute_tool", "generate_response")
workflow.add_edge("generate_response", END)

app_graph = workflow.compile()

async def process_user_input(text: str) -> str:
    """Entry point for the backend to pass STT text into the agent."""
    # Capture current PC state from monitor
    current_metrics = {
        "cpu": pc_monitor.get_gpu_usage(), # using as placeholder
        "ram": 50,
        "gpu": 10,
        "temp": pc_monitor.get_cpu_temp(),
        "spotify": "None"
    }
    
    # We could await collect_metrics, but it's fine to fetch latest known state
    state_input = {
        "messages": [HumanMessage(content=text)],
        "pc_context": current_metrics,
        "next_action": ""
    }
    
    # Run graph
    result = await app_graph.ainvoke(state_input)
    
    # Extract final AIMessage
    final_message = result['messages'][-1].content
    return final_message
