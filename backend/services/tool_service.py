"""
ToolService — business logic for MCP tool management and execution.

Provides a service boundary between route handlers and the MCP registry,
enforcing the permission layer via ToolSelector.
"""

import logging

from mcp_registry.registry import registry
from services.mcp_host import mcp_host
from services.policy_engine import policy_engine

logger = logging.getLogger(__name__)


class ToolService:
    async def list_tools(self) -> list[dict]:
        """Return all internal and remote tools with safety classifications."""
        tools = await mcp_host.get_combined_tools()
        for t in tools:
            # Classification is now centralized in PolicyEngine
            t["category"] = policy_engine.get_classification(t["name"])
        return tools

    async def execute(self, tool_name: str, parameters: dict, *, force: bool = False, session_id: str = None) -> dict:
        """
        Execute a tool via the McpHost orchestrator.
        Handles both internal and remote routing with centralized security.
        """
        logger.info(
            "tool_service.execute",
            extra={"tool": tool_name, "force": force, "session_id": session_id},
        )

        # All logic (Routing + Security) is now in mcp_host.execute
        # For 'force' execution (UI actions), we pass it to bypass security confirmations.
        
        result = await mcp_host.execute(tool_name, parameters, bypass_security=force)
        
        if session_id and result.get("status") == "success":
            from copilot.conversation_manager import conversation_manager
            conversation_manager.add_tool_result(session_id, result)
            
        return result

    def get_categories(self) -> dict:
        """Return lists of safe and dangerous tools from the source of truth."""
        from services.policy_engine import SAFE_TOOLS, DANGEROUS_TOOLS
        return {
            "safe": list(SAFE_TOOLS),
            "dangerous": list(DANGEROUS_TOOLS),
        }


# Singleton instance
tool_service = ToolService()
