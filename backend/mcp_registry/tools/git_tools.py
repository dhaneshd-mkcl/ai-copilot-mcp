"""
git_tools.py — Advanced Git and GitHub integration for MCP.
"""

import logging
import asyncio
import os
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from mcp_registry.registry import registry
from mcp_registry.tools.terminal_tools import run_command
from config import config
from copilot.utils import safe_path

logger = logging.getLogger(__name__)

class GitStatusOutput(BaseModel):
    success: bool
    status: Optional[str] = None
    message: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None

@registry.register(
    name="git_get_status",
    description="Check the current Git status (staged, unstaged, branch info).",
    parameters={},
    category="safe",
)
async def git_get_status() -> dict:
    logger.info("tool.git_get_status | START")
    workspace = config.ALLOWED_BASE_PATH
    try:
        result = await run_command(command="git status --porcelain=v2 --branch", cwd=workspace)
        return GitStatusOutput(
            success=result.get("returncode") == 0,
            status=result.get("stdout"),
            error=result.get("stderr") if result.get("returncode") != 0 else None
        ).model_dump(exclude_none=True)
    except Exception as e:
        return GitStatusOutput(success=False, error=str(e)).model_dump(exclude_none=True)

@registry.register(
    name="git_diff_file",
    description="Get the diff of a specific file to see what has changed since the last commit.",
    parameters={
        "path": {"type": "string", "description": "File path relative to workspace"},
    },
    category="safe",
)
async def git_diff_file(path: str) -> dict:
    logger.info(f"tool.git_diff_file | START path='{path}'")
    workspace = config.ALLOWED_BASE_PATH
    try:
        safe_path(path)
        result = await run_command(command=f"git diff {path}", cwd=workspace)
        return GitStatusOutput(
            success=result.get("returncode") == 0,
            message=path,
            output=result.get("stdout"),
            error=result.get("stderr") if result.get("returncode") != 0 else None
        ).model_dump(exclude_none=True)
    except Exception as e:
        return GitStatusOutput(success=False, error=str(e)).model_dump(exclude_none=True)

@registry.register(
    name="commit_code_v2",
    description="Stage and commit code changes in the workspace",
    parameters={
        "message": {"type": "string", "description": "Commit message"},
        "files": {"type": "array", "items": {"type": "string"}, "description": "List of files to stage (empty = all)", "default": []},
    },
    category="dangerous",
)
async def commit_code(message: str, files: list = None) -> dict:
    logger.info(f"tool.commit_code | START msg='{message}' files={files}")
    workspace = config.ALLOWED_BASE_PATH
    if not shutil.which("git"):
        return GitStatusOutput(success=False, error="git not installed").model_dump(exclude_none=True)

    # Initialize git if not already initialized
    await run_command(command="git init", cwd=workspace)

    if files:
        for f in files:
            await run_command(command=f"git add {f}", cwd=workspace)
    else:
        await run_command(command="git add -A", cwd=workspace)

    result = await run_command(command=f'git commit -m "{message}"', cwd=workspace)
    return GitStatusOutput(
        success=result.get("returncode") == 0,
        message=message,
        output=result.get("stdout"),
        error=result.get("stderr") if result.get("returncode") != 0 else None,
    ).model_dump(exclude_none=True)

@registry.register(
    name="git_pull",
    description="Pull changes from a remote repository.",
    parameters={
        "remote": {"type": "string", "description": "Remote name (default: origin)", "default": "origin"},
        "branch": {"type": "string", "description": "Branch name (optional)"}
    },
    category="dangerous",
)
async def git_pull(remote: str = "origin", branch: str = "") -> dict:
    logger.info(f"tool.git_pull | remote='{remote}' branch='{branch}'")
    cmd = f"git pull {remote} {branch}".strip()
    result = await run_command(command=cmd, cwd=config.ALLOWED_BASE_PATH)
    return GitStatusOutput(
        success=result.get("returncode") == 0,
        output=result.get("stdout"),
        error=result.get("stderr")
    ).model_dump(exclude_none=True)

@registry.register(
    name="git_push",
    description="Push changes to a remote repository.",
    parameters={
        "remote": {"type": "string", "description": "Remote name (default: origin)", "default": "origin"},
        "branch": {"type": "string", "description": "Branch name (optional)"}
    },
    category="dangerous",
)
async def git_push(remote: str = "origin", branch: str = "") -> dict:
    logger.info(f"tool.git_push | remote='{remote}' branch='{branch}'")
    cmd = f"git push {remote} {branch}".strip()
    result = await run_command(command=cmd, cwd=config.ALLOWED_BASE_PATH)
    return GitStatusOutput(
        success=result.get("returncode") == 0,
        output=result.get("stdout"),
        error=result.get("stderr")
    ).model_dump(exclude_none=True)

@registry.register(
    name="git_branch",
    description="List, create, or switch branches.",
    parameters={
        "action": {"type": "string", "description": "Action: list, create, switch", "enum": ["list", "create", "switch"]},
        "name": {"type": "string", "description": "Branch name (required for create/switch)"}
    },
    category="dangerous",
)
async def git_branch(action: str, name: str = "") -> dict:
    logger.info(f"tool.git_branch | action='{action}' name='{name}'")
    workspace = config.ALLOWED_BASE_PATH
    if action == "list":
        result = await run_command(command="git branch -a", cwd=workspace)
    elif action == "create":
        result = await run_command(command=f"git branch {name}", cwd=workspace)
    elif action == "switch":
        result = await run_command(command=f"git checkout {name}", cwd=workspace)
    
    return GitStatusOutput(
        success=result.get("returncode") == 0,
        output=result.get("stdout"),
        error=result.get("stderr")
    ).model_dump(exclude_none=True)

@registry.register(
    name="git_log",
    description="View git commit history.",
    parameters={
        "max_count": {"type": "integer", "description": "Number of commits to show (default 5)", "default": 5}
    },
    category="safe",
)
async def git_log(max_count: int = 5) -> dict:
    logger.info(f"tool.git_log | max_count={max_count}")
    result = await run_command(command=f"git log -n {max_count} --oneline --graph --decorate", cwd=config.ALLOWED_BASE_PATH)
    return GitStatusOutput(
        success=result.get("returncode") == 0,
        output=result.get("stdout"),
        error=result.get("stderr")
    ).model_dump(exclude_none=True)
