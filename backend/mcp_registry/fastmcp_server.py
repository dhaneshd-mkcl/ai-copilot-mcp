"""
fastmcp_server.py — Independent FastMCP wrapper around the legacy registry.
This file ensures FastMCP can be used natively without modifying the legacy SSE server.
"""

import logging
from mcp.server.fastmcp import FastMCP
from mcp_registry.registry import registry

logger = logging.getLogger(__name__)

fastmcp = FastMCP("ai-copilot-fastmcp", version="1.0.0")

_bridged = False

def bridge_legacy_tools():
    """Initializes the FastMCP tool registry from the legacy registry."""
    global _bridged
    if _bridged: return
    _bridged = True
    
    # 1. Bridge legacy tools dynamically
    for t_dict in registry.list_tools():
        tool_name = t_dict["name"]
        tool_obj = registry.get_tool(tool_name)
        if tool_obj and tool_obj.handler:
            logger.info(f"fastmcp_server | Bridging legacy tool: {tool_name}")
            fastmcp.tool(name=tool_obj.name, description=tool_obj.description)(tool_obj.handler)

    # 2. Bridge legacy resources dynamically
    for r_dict in registry.list_resources():
        uri = r_dict["uri"]
        res_obj = registry.get_resource(uri)
        if res_obj and res_obj.handler:
            logger.info(f"fastmcp_server | Bridging legacy resource: {res_obj.name}")
            fastmcp.resource(uri=res_obj.uri, name=res_obj.name, description=res_obj.description)(res_obj.handler)

# Optionally call `bridge_legacy_tools()` after all tools are imported.
