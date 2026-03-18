"""
mcp_host.py — Multi-Server MCP Host Orchestrator.

Aggregates tools from the internal registry and remote MCP servers,
providing a unified execution interface for the ChatService.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

from mcp_registry.registry import registry
from config import config

logger = logging.getLogger(__name__)

class McpHost:
    def __init__(self):
        self.remote_sessions: Dict[str, ClientSession] = {}
        self.remote_contexts = {} # Stores context managers to keep them alive
        self._tool_map: Dict[str, str] = {} # Map tool_name -> "internal" or remote_source_name
        self.initialized = False
        self._lock = asyncio.Lock()

    async def _ensure_initialized(self):
        async with self._lock:
            if self.initialized:
                return
            
            # 1. Connect to configured remote servers
            for server_conf in config.REMOTE_MCP_SERVERS:
                name = server_conf.get("name")
                stype = server_conf.get("type", "sse")
                url = server_conf.get("url")
                
                try:
                    logger.info("mcp_host.initializing_remote", extra={"name": name, "type": stype})
                    if stype == "sse":
                        # Note: sse_client is an async context manager
                        ctx = sse_client(url)
                        read, write = await ctx.__aenter__()
                        session = ClientSession(read, write)
                        await session.initialize()
                        
                        self.remote_sessions[name] = session
                        self.remote_contexts[name] = ctx
                        logger.info("mcp_host.remote_connected", extra={"name": name})
                    
                    elif stype == "stdio":
                        command = server_conf.get("command")
                        args = server_conf.get("args", [])
                        params = StdioServerParameters(command=command, args=args)
                        
                        ctx = stdio_client(params)
                        read, write = await ctx.__aenter__()
                        session = ClientSession(read, write)
                        await session.initialize()
                        
                        self.remote_sessions[name] = session
                        self.remote_contexts[name] = ctx
                        logger.info("mcp_host.remote_connected", extra={"name": name})

                except Exception as e:
                    logger.error("mcp_host.remote_connect_failed", extra={"name": name, "error": str(e)})
            
            # 2. Build Tool Map for O(1) routing
            self._tool_map = {}
            # Priority 1: Internal tools
            for t in registry.list_tools():
                self._tool_map[t["name"]] = "internal"
            
            # Priority 2: Remote tools
            for name, session in self.remote_sessions.items():
                try:
                    remote_tools_resp = await session.list_tools()
                    for t in remote_tools_resp.tools:
                        if t.name not in self._tool_map: # Prevent shadowing internal tools unless intended
                            self._tool_map[t.name] = name
                except Exception as e:
                    logger.error("mcp_host.build_map_error", extra={"name": name, "error": str(e)})
            
            logger.info("mcp_host.initialized", extra={"tools_mapped": len(self._tool_map)})
            self.initialized = True

    async def get_combined_tools(self) -> List[Dict[str, Any]]:
        """
        Merge registered internal tools with any discovered external tools.
        """
        await self._ensure_initialized()
        all_tools = []
        
        # Internal registry
        for t in registry.list_tools():
            all_tools.append({**t, "source": "internal"})
            
        # Remote servers
        for name, session in self.remote_sessions.items():
            try:
                remote_tools_resp = await session.list_tools()
                for t in remote_tools_resp.tools:
                    all_tools.append({
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.inputSchema,
                        "source": name,
                        "category": "unknown"
                    })
            except Exception as e:
                logger.error("mcp_host.remote_list_tools_error", extra={"name": name, "error": str(e)})
            
        return all_tools

    async def execute(self, tool_name: str, parameters: Dict[str, Any], bypass_security: bool = False) -> Dict[str, Any]:
        """
        Optimized execution with O(1) routing and centralized security.
        """
        await self._ensure_initialized()
        
        source = self._tool_map.get(tool_name)
        if not source:
            logger.warning("mcp_host.tool_not_found", extra={"tool": tool_name})
            return {
                "tool": tool_name,
                "status": "error",
                "error": f"Tool '{tool_name}' not found."
            }

        # Centralized Security Check (Integrating PolicyEngine)
        from services.policy_engine import policy_engine
        status, reason = policy_engine.validate_call(tool_name, parameters)
        
        if status == "REJECTED":
            logger.warning("mcp_host.security_rejected", extra={"tool": tool_name, "reason": reason})
            return {
                "tool": tool_name,
                "status": "error",
                "error": f"Security Rejection: {reason}"
            }
        
        if status == "CONFIRM_REQUIRED" and not bypass_security:
            logger.info("mcp_host.confirmation_required", extra={"tool": tool_name})
            return {
                "tool": tool_name,
                "status": "requires_confirmation",
                "message": reason,
                "parameters": parameters
            }

        # Optimized Routing
        logger.info("mcp_host.tool_execution", extra={"tool": tool_name, "source": source})
        
        if source == "internal":
            try:
                result = await registry.execute_tool(tool_name, parameters)
                logger.info(f"✅ [INTERNAL SUCCESS] | tool='{tool_name}'")
                return result
            except Exception as e:
                logger.error("mcp_host.internal_error", extra={"tool": tool_name, "error": str(e)})
                return {"tool": tool_name, "status": "error", "error": str(e)}
        
        # Remote Routing
        for attempt in [1, 2]:
            session = self.remote_sessions.get(source)
            if not session:
                if attempt == 1:
                    logger.info("mcp_host.remote_reconnect", extra={"source": source, "attempt": 1})
                    self.initialized = False
                    await self._ensure_initialized()
                    session = self.remote_sessions.get(source)
                
                if not session:
                    logger.error("mcp_host.remote_unavailable", extra={"tool": tool_name, "source": source})
                    return {"tool": tool_name, "status": "error", "error": f"Remote source '{source}' unavailable."}
            
            try:
                result = await session.call_tool(tool_name, parameters)
                text_results = [c.text for c in result.content if hasattr(c, 'text')]
                output = "\n".join(text_results)
                
                status_emoji = "✅" if not result.isError else "❌"
                logger.info("mcp_host.remote_execution", extra={"tool": tool_name, "source": source, "status": "success" if not result.isError else "error"})
                
                return {
                    "tool": tool_name,
                    "status": "error" if result.isError else "success",
                    "result": output,
                    "source": source
                }
            except Exception as e:
                logger.warning("mcp_host.remote_attempt_failed", extra={"tool": tool_name, "source": source, "attempt": attempt, "error": str(e)})
                if attempt == 1:
                    # Clear stale session and force re-init on next attempt
                    self.remote_sessions.pop(source, None)
                    self.remote_contexts.pop(source, None)
                    self.initialized = False
                    await asyncio.sleep(1) # Brief pause before retry
                    continue
                return {"tool": tool_name, "status": "error", "error": str(e)}

    async def shutdown(self):
        """Clean up all remote sessions."""
        for name, ctx in self.remote_contexts.items():
            try:
                await ctx.__aexit__(None, None, None)
            except Exception as e:
                logger.error("mcp_host.shutdown_error", extra={"name": name, "error": str(e)})
        self.remote_sessions.clear()
        self.remote_contexts.clear()
        self._tool_map.clear()
        self.initialized = False

# Singleton instance for the application
mcp_host = McpHost()
