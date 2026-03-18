"""
mcp/server.py — Official MCP Server bridge for Tool and Resource management.
Exposes the internal registry over the official MCP protocol.
"""

import logging
import asyncio
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import (
    Tool,
    Resource,
    TextContent,
    ImageContent,
    EmbeddedResource,
    Prompt,
    GetPromptResult,
    PromptMessage,
)
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport
from starlette.responses import Response, JSONResponse
from starlette.requests import Request

from mcp_registry.registry import registry

logger = logging.getLogger(__name__)

# Create the official MCP Server instance
server = Server("ai-copilot-hybrid-server")

# Global SSE transport instance for sharing between routes
sse_transport = None

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List all registered tools from our internal registry."""
    tools = []
    for t in registry.list_tools():
        # Wrap raw properties into a full JSON Schema object
        properties = {}
        for param_name, details in t["parameters"].items():
            param_copy = details.copy()
            # Safety: MCP/JSON-Schema requires 'items' for 'array' type
            if param_copy.get("type") == "array" and "items" not in param_copy:
                param_copy["items"] = {"type": "string"}
            properties[param_name] = param_copy

        required = [name for name, details in properties.items() if "default" not in details]
        
        schema = {
            "type": "object",
            "properties": properties,
            "required": required
        }
        
        logger.info(f"mcp.server.list_tools | PROCESSED '{t['name']}' with schema")
        tools.append(Tool(
            name=t["name"],
            description=t["description"],
            inputSchema=schema
        ))
    return tools

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent | ImageContent | EmbeddedResource]:
    """Bridge official tool calls to our internal execute_tool logic."""
    logger.info(f"mcp.server.call_tool | name='{name}'")
    try:
        result = await registry.execute_tool(name, arguments or {})
        # Flatten the result for MCP protocol compatibility
        return [TextContent(type="text", text=str(result.get("result", result)))]
    except Exception as e:
        logger.error(f"mcp.server.call_tool | ERROR: {str(e)}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]

@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List all registered resources from our internal registry."""
    resources = []
    for r in registry.list_resources():
        resources.append(Resource(
            uri=r["uri"],
            name=r["name"],
            description=r.get("description"),
            mimeType=r.get("mime_type")
        ))
    return resources

@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read a specific resource from our internal registry."""
    logger.info(f"mcp.server.read_resource | uri='{uri}'")
    result = await registry.read_resource(uri)
    if result.get("status") == "success":
        return str(result.get("content"))
    raise Exception(result.get("error", "Failed to read resource"))

async def run_stdio():
    """Run the server using Stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="ai-copilot",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

# SSE Handlers for mounting in FastAPI/Starlette
async def handle_sse(request):
    """SSE endpoint handler."""
    global sse_transport
    sse_transport = SseServerTransport("/mcp/messages")
    try:
        async with sse_transport.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="ai-copilot-sse",
                    server_version="1.0.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    except RuntimeError as e:
        # Suppress common ASGI disconnect/reload errors
        if "Expected ASGI message" in str(e) or "contextlib.AsyncExitStack" in str(e):
            logger.debug(f"mcp.server.sse | Suppressed ASGI RuntimeError: {e}")
        else:
            raise

@server.list_prompts()
async def handle_list_prompts() -> list[Prompt]:
    """List available MCP prompts."""
    from mcp.types import Prompt
    return [
        Prompt(
            name="strict-research",
            description="Protocol for deep historical and technical research."
        )
    ]

@server.get_prompt()
async def handle_get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
    """Get a specific MCP prompt."""
    from mcp.types import GetPromptResult, PromptMessage
    if name == "strict-research":
        return GetPromptResult(
            description="Strict Research Protocol",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text="For historical or complex technical tasks, ALWAYS perform at least 2-3 searches using web_search_smart and use fetch_web_page to read the top results before writing your report. Do not rely solely on your internal knowledge for specific facts."
                    )
                )
            ]
        )
    raise ValueError(f"Prompt not found: {name}")

async def handle_messages(request: Request):
    """Messages endpoint handler for SSE transport."""
    global sse_transport
    if not sse_transport:
        return Response("No active SSE session", status_code=400)
    
    # We use a silent_send wrapper to prevent sse_transport from sending 
    # its own HTTP response, which conflicts with FastAPI's handler return.
    async def silent_send(message):
        if message["type"] in ("http.response.start", "http.response.body"):
            return
        await request._send(message)

    try:
        await sse_transport.handle_post_message(request.scope, request.receive, silent_send)
    except RuntimeError as e:
        if "Expected ASGI message" in str(e):
             logger.debug(f"mcp.server.messages | Suppressed ASGI RuntimeError: {e}")
        else:
            raise
    return Response("Accepted", status_code=202)

if __name__ == "__main__":
    asyncio.run(run_stdio())
