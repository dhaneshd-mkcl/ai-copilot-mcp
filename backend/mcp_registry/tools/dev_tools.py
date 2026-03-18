import logging
import asyncio
import os
import shutil
from pathlib import Path
from datetime import datetime
from mcp_registry.registry import registry
from config import config
from copilot.utils import safe_path

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from mcp_registry.tools.terminal_tools import run_command

logger = logging.getLogger(__name__)

class DevStatusOutput(BaseModel):
    success: bool
    status: Optional[str] = None
    message: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None

class DevShellOutput(BaseModel):
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error: Optional[str] = None

class DevDepsOutput(BaseModel):
    node: Dict[str, str]
    python: List[str]


@registry.register(
    name="inspect_dependencies",
    description="Detect and list all project dependencies (npm, pip) and their versions.",
    parameters={},
    category="safe",
)
async def inspect_dependencies() -> dict:
    logger.info("tool.inspect_dependencies | START")
    base = Path(config.ALLOWED_BASE_PATH).resolve()
    deps = {"node": {}, "python": []}
    
    # Node
    pkg_json = base / "package.json"
    if pkg_json.exists():
        import json
        try:
            data = json.loads(pkg_json.read_text())
            deps["node"] = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        except: pass
        
    # Python
    reqs = base / "requirements.txt"
    if reqs.exists():
        deps["python"] = reqs.read_text().splitlines()
        
    return DevDepsOutput(**deps).model_dump(exclude_none=True)
