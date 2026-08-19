import asyncio
import logging
import os
import yaml
from typing import List, Dict, Any, Callable

# LangChain tool binding
from langchain_core.tools import StructuredTool
from pydantic import create_model, Field

# MCP SDK
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
import mcp.types as types

logger = logging.getLogger("core.mcp_client")

class MCPManager:
    def __init__(self):
        self.config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "mcp_servers.yaml")
        self.sessions: Dict[str, ClientSession] = {}
        self.stop_events: Dict[str, asyncio.Event] = {}
        self.server_tasks: Dict[str, asyncio.Task] = {}
        self.langchain_tools: List[StructuredTool] = []

    async def _run_server(self, server_name: str, server_params: StdioServerParameters, ready_event: asyncio.Event):
        stop_event = asyncio.Event()
        self.stop_events[server_name] = stop_event
        
        try:
            async with stdio_client(server_params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    self.sessions[server_name] = session
                    
                    # Load tools from this server
                    await self._load_server_tools(server_name, session)
                    
                    # Signal that initialization is complete
                    ready_event.set()
                    
                    # Wait for shutdown signal
                    await stop_event.wait()
        except Exception as e:
            logger.error(f"Failed in MCP server {server_name}: {e}")
            ready_event.set() # Unblock if failed

    async def initialize(self):
        if not os.path.exists(self.config_path):
            logger.warning(f"MCP servers config not found at {self.config_path}")
            return
            
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            return

        servers = config.get("mcpServers", {})
        if not servers:
            return

        for server_name, server_config in servers.items():
            command = server_config.get("command")
            args = server_config.get("args", [])
            
            logger.info(f"Starting MCP Server '{server_name}': {command} {' '.join(args)}")
            
            server_params = StdioServerParameters(command=command, args=args)
            ready_event = asyncio.Event()
            
            task = asyncio.create_task(self._run_server(server_name, server_params, ready_event))
            self.server_tasks[server_name] = task
            
            # Wait for this server to be ready before moving to next
            await ready_event.wait()

    async def _load_server_tools(self, server_name: str, session: ClientSession):
        try:
            tools_response = await session.list_tools()
            for tool in tools_response.tools:
                logger.info(f"Loaded tool '{tool.name}' from '{server_name}'")
                
                # Convert JSON Schema to Pydantic Model for LangChain
                raw_schema = getattr(tool, 'input_schema', getattr(tool, 'inputSchema', {}))
                if hasattr(raw_schema, 'model_dump'):
                    schema = raw_schema.model_dump()
                elif hasattr(raw_schema, 'dict'):
                    schema = raw_schema.dict()
                elif isinstance(raw_schema, dict):
                    schema = raw_schema
                else:
                    schema = {}

                fields = {}
                properties = schema.get("properties", {})
                required = schema.get("required", [])
                
                for prop_name, prop_info in properties.items():
                    prop_type = Any
                    if prop_info.get("type") == "string":
                        prop_type = str
                    elif prop_info.get("type") == "integer":
                        prop_type = int
                    elif prop_info.get("type") == "boolean":
                        prop_type = bool
                    elif prop_info.get("type") == "number":
                        prop_type = float
                        
                    default = ... if prop_name in required else None
                    description = prop_info.get("description", "")
                    fields[prop_name] = (prop_type, Field(default=default, description=description))
                    
                InputModel = create_model(f"{server_name}_{tool.name}Input", **fields)
                
                # Create a closure to capture the correct session and tool name
                def create_tool_func(sess: ClientSession, t_name: str) -> Callable:
                    async def async_tool_func(**kwargs) -> str:
                        try:
                            res = await sess.call_tool(t_name, arguments=kwargs)
                            if res.isError:
                                return f"Error: {res.content}"
                            # Extract text from content blocks
                            texts = [c.text for c in res.content if hasattr(c, 'text')]
                            return "\n".join(texts)
                        except Exception as e:
                            return f"Tool execution failed: {e}"
                    return async_tool_func

                langchain_tool = StructuredTool.from_function(
                    coroutine=create_tool_func(session, tool.name),
                    name=tool.name,
                    description=f"[{server_name}] {tool.description or tool.name}",
                    args_schema=InputModel
                )
                self.langchain_tools.append(langchain_tool)
        except Exception as e:
            logger.error(f"Failed to load tools for {server_name}: {e}")

    async def cleanup(self):
        for server_name, stop_event in self.stop_events.items():
            logger.info(f"Shutting down MCP server '{server_name}'")
            stop_event.set()
        
        # Wait for all tasks to finish
        if self.server_tasks:
            await asyncio.gather(*self.server_tasks.values(), return_exceptions=True)
            
        self.sessions.clear()
        self.stop_events.clear()
        self.server_tasks.clear()
        self.langchain_tools.clear()

mcp_manager = MCPManager()
