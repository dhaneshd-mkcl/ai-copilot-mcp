"""
policy_engine.py — The Security Gatekeeper.
Validates tool calls against security policies and user constraints.
"""

import os
import logging
from typing import Dict, Any, Tuple, Optional
from pathlib import Path
from config import config

logger = logging.getLogger(__name__)

SAFE_TOOLS = frozenset({
    "list_files", "read_file", "search_repository", "scan_directory",
    "list_issues", "fix_file", "improve_code", "outline_file",
    "read_directory", "read_resource",
    "list_mcp_tools", "get_combined_tools",
    "web_search_smart", "search_web", "web_search", "web_search_ddg",
    "web_search_news", "web_search_images", "web_search_videos",
    # Aliases & Missing Safes
    "read_file_content", "list_dir", "ls", "list_dir_recursive", "grep_search", 
    "semantic_search", "get_repo_map", "index_workspace",
    "fetch_web_page", "read_url", "fetch", "get_clipboard_text"
})

DANGEROUS_TOOLS = frozenset({
    "commit_code", "create_github_issue", "create_jira_ticket", "execute_command",
    "write_file", "edit_file", "create_directory", "move_item", "delete_item", 
    "replace_in_repository", "focus_window", "take_screenshot", "gui_scroll",
    "web_search_google_gui"
})

class ToolPolicy:
    # Directories that should NEVER be touched via MCP tools
    BLOCKED_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".system_generated"}
    
    # Files that require explicit manual confirmation even if tool is 'safe'
    @property
    def SENSITIVE_FILES(self):
        return config.SENSITIVE_FILES

class PolicyEngine:
    def __init__(self):
        self.workspace_root = Path(config.ALLOWED_BASE_PATH).resolve()

    def get_classification(self, tool_name: str) -> str:
        if tool_name in SAFE_TOOLS:
            return "safe"
        if tool_name in DANGEROUS_TOOLS:
            return "dangerous"
        return "unknown"

    def validate_call(self, tool_name: str, parameters: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        """
        Validates a tool call.
        Returns: (status, reason)
        status: "APPROVED" | "CONFIRM_REQUIRED" | "REJECTED"
        """
        logger.info(f"policy_engine.validate | tool='{tool_name}'")

        # 1. Path-based validation (CRITICAL)
        path_param = (
            parameters.get("path") or 
            parameters.get("TargetFile") or 
            parameters.get("TargetDirectory") or
            parameters.get("directory") or
            parameters.get("target")
        )
        if path_param:
            is_safe, reason = self._is_path_safe(path_param)
            if not is_safe:
                return "REJECTED", reason

        # 2. Classification-based validation
        classification = self.get_classification(tool_name)
        
        # 3. High-risk specific tools (Confirmation required)
        gui_tools = {"type_text", "press_key", "hotkey", "move_and_click"}
        if tool_name in gui_tools or classification == "dangerous":
            return "CONFIRM_REQUIRED", f"Tool '{tool_name}' requires explicit user confirmation."

        # 4. Sensitive file modification check
        if path_param:
            filename = Path(path_param).name
            if filename in ToolPolicy().SENSITIVE_FILES:
                # RELAXATION: Allow reading sensitive files without confirmation
                READ_ONLY_TOOLS = {
                    "read_file", "list_files", "scan_directory", "search_repository", "outline_file",
                    "read_file_content", "list_dir", "ls", "grep_search", "list_dir_recursive", "read_directory"
                }
                if tool_name not in READ_ONLY_TOOLS:
                    return "CONFIRM_REQUIRED", f"Modifying sensitive file '{filename}' requires confirmation."

        # 5. Unknown tools (Remote MCP tools)
        if classification == "unknown":
            # Err on the side of caution for external tools
            return "CONFIRM_REQUIRED", f"External tool '{tool_name}' requires manual approval."

        return "APPROVED", None

    def _is_path_safe(self, provided_path: str) -> Tuple[bool, str]:
        """Enforces workspace boundaries and blocks restricted directories."""
        try:
            # Handle both absolute and relative paths
            target = Path(provided_path)
            if not target.is_absolute():
                target = (self.workspace_root / target).resolve()
            else:
                target = target.resolve()

            # Boundary Check
            if not str(target).startswith(str(self.workspace_root)):
                return False, f"Access Denied: Path is outside the allowed workspace ({self.workspace_root})."

            # Restricted Directory Check
            for part in target.parts:
                if part in ToolPolicy.BLOCKED_DIRS:
                    return False, f"Access Denied: The directory '{part}' is protected."

            return True, ""
        except Exception as e:
            return False, f"Invalid Path Error: {str(e)}"

# Singleton instance
policy_engine = PolicyEngine()
