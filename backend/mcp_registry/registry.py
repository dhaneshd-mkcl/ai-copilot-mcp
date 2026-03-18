"""
MCPRegistry — MCP tool registry with structured metadata and safety classification.
"""

import logging
from typing import Any, Callable, Optional, Union
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class MCPTool:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Callable,
        category: str = "safe",
        timeout: int = 30,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler
        self.category = category   # "safe" | "dangerous"
        self.timeout = timeout

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "category": self.category,
            "timeout": self.timeout,
        }


class MCPResource:
    def __init__(
        self,
        uri: str,
        name: str,
        description: str,
        handler: Callable,
        mime_type: str = "text/plain",
    ):
        self.uri = uri
        self.name = name
        self.description = description
        self.handler = handler
        self.mime_type = mime_type

    def to_dict(self) -> dict:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mime_type": self.mime_type,
        }


class MCPRegistry:
    def __init__(self):
        self._tools: dict[str, MCPTool] = {}
        self._resources: dict[str, MCPResource] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        category: str = "safe",
        timeout: int = 30,
    ):
        """Decorator to register a tool with full metadata."""
        def decorator(func: Callable):
            self._tools[name] = MCPTool(
                name=name,
                description=description,
                parameters=parameters,
                handler=func,
                category=category,
                timeout=timeout,
            )
            # Make tool registration stand out as a header in the logs
            header_str = f"=== REGISTERED TOOL: {name.upper()} ==="
            logger.info(f"\n{'=' * len(header_str)}\n{header_str}\n{'=' * len(header_str)}\nCategory: {category} | Timeout: {timeout}s\n")
            return func
        return decorator

    def register_resource(
        self,
        uri: str,
        name: str,
        description: str,
        mime_type: str = "text/plain",
    ):
        """Decorator to register a read-only resource."""
        def decorator(func: Callable):
            self._resources[uri] = MCPResource(
                uri=uri,
                name=name,
                description=description,
                handler=func,
                mime_type=mime_type,
            )
            logger.info(f"mcp.registry.register_resource | SUCCESS uri='{uri}'")
            return func
        return decorator

    def get_tool(self, name: str) -> Optional[MCPTool]:
        return self._tools.get(name)

    def get_resource(self, uri: str) -> Optional[MCPResource]:
        return self._resources.get(uri)

    def list_tools(self) -> list[dict]:
        return [t.to_dict() for t in self._tools.values()]

    def list_resources(self) -> list[dict]:
        return [r.to_dict() for r in self._resources.values()]

    async def execute_tool(self, name: str, parameters: dict) -> Any:
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found in registry")
        
        logger.info(f"mcp_registry.execute_tool tool='{name}' params={parameters}")
        try:
            # Most tools return a dict with status/result/error
            # We call the handler with parameters
            # Handle both sync and async handlers if necessary, though all our tools are async now
            result = await tool.handler(**parameters)
            
            # Standardize output for the host orchestrator without redundant wrapping
            if isinstance(result, dict):
                result["tool"] = name
                if "status" not in result:
                    result["status"] = "success" if "error" not in result or not result["error"] else "error"
                return result
            
            return {
                "tool": name,
                "status": "success",
                "result": result
            }
        except Exception as e:
            logger.error(f"mcp_registry.tool_error tool='{name}' error='{str(e)}'")
            return {
                "tool": name,
                "status": "error",
                "error": f"Internal tool execution failed: {str(e)}"
            }

    async def read_resource(self, uri: str) -> Any:
        resource = self.get_resource(uri)
        if not resource:
            raise ValueError(f"Resource '{uri}' not found in registry")

        logger.info(f"mcp_registry.read_resource uri='{uri}'")
        try:
            result = await resource.handler()
            return {"uri": uri, "status": "success", "content": result, "mime_type": resource.mime_type}
        except Exception as e:
            logger.error("mcp_registry.resource_error", extra={"uri": uri, "error": str(e)})
            return {"uri": uri, "status": "error", "error": str(e)}

    def get_system_prompt_tools(self) -> str:
        """Format tools and resources for LLM system prompt."""
        lines = ["## Available MCP Tools (Actions)\n"]
        for t in self._tools.values():
            lines.append(f"- **{t.name}** [{t.category}]: {t.description}")
            if t.parameters:
                lines.append(f"  Parameters: {t.parameters}")
        
        if self._resources:
            lines.append("\n## Available MCP Resources (Read-Only Data)\n")
            for r in self._resources.values():
                lines.append(f"- **{r.name}** ({r.uri}): {r.description}")

        lines.append(
            "\nTo call a tool, you MUST use this exact format and ALWAYS include the closing tag:\n"
            "<tool>\n"
            "{\n"
            "  \"name\": \"tool_name\",\n"
            "  \"parameters\": {...}\n"
            "}\n"
            "</tool>\n"
            "\n"
            "To read a resource, use the same format but with the \"read_resource\" tool name."
        )
        return "\n".join(lines)


registry = MCPRegistry()
