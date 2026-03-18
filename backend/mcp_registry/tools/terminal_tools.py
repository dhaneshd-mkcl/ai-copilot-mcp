"""
terminal_tools.py — Shell execution tools with Windows-safe thread-based execution.
"""

import asyncio
import logging
import shutil
import sys
import subprocess
import time
import platform
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel

from mcp_registry.registry import registry
from copilot.utils import safe_path
from config import config

logger = logging.getLogger(__name__)


class TerminalOutput(BaseModel):
    status: str
    command: str
    stdout: str
    stderr: str
    returncode: int
    duration_ms: int
    error: Optional[str] = None


class InstallOutput(BaseModel):
    status: str
    package: str
    manager: str
    stdout: str
    stderr: str
    returncode: int
    error: Optional[str] = None


async def _stream_command(cmd: str, cwd: str = None, timeout: int = 60) -> TerminalOutput:
    """
    Reliable cross-platform command runner (Windows safe).
    Uses thread-based execution to avoid Windows asyncio subprocess limitations.
    """
    start = time.time()

    def execute():
        try:
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            stdout, stderr = process.communicate(timeout=timeout)
            duration = int((time.time() - start) * 1000)

            return {
                "stdout": stdout.strip(),
                "stderr": stderr.strip(),
                "returncode": process.returncode,
                "duration_ms": duration
            }

        except subprocess.TimeoutExpired:
            process.kill()
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "returncode": -1,
                "duration_ms": int((time.time() - start) * 1000)
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": f"Execution error: {str(e)}",
                "returncode": -1,
                "duration_ms": 0
            }

    # Execute in a thread to keep the event loop unblocked
    result = await asyncio.to_thread(execute)

    logger.info(f"[CMD] {cmd[:100]}...")
    logger.info(f"[RET] {result['returncode']} ({result['duration_ms']}ms)")
    if result["stdout"]:
        logger.debug(f"[OUT] {result['stdout'][:100]}...")
    if result["stderr"]:
        logger.error(f"[ERR] {result['stderr'][:200]}...")

    ok = result["returncode"] == 0

    return TerminalOutput(
        status="success" if ok else "error",
        command=cmd,
        stdout=result["stdout"][:8000],
        stderr=result["stderr"][:2000],
        returncode=result["returncode"],
        duration_ms=result["duration_ms"],
        error=result["stderr"][:500] if not ok and result["stderr"] else None
    )


@registry.register(
    name="run_command",
    description=(
        "Execute ANY shell command (bash/cmd) and return full stdout/stderr output. "
        "Use this for builds, testing, or system operations. WARNING: Host is Windows. "
        "Favors PowerShell/CMD syntax."
    ),
    parameters={
        "command": {"type": "string", "description": "The shell command to execute."},
        "cwd": {
            "type": "string",
            "description": "Working directory relative to workspace root.",
            "default": "."
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds (default: 60).",
            "default": 60
        },
    },
    category="dangerous",
    timeout=70,
)
async def run_command(command: str, cwd: str = ".", timeout: int = 60) -> dict:
    logger.info(f"tool.run_command | START cmd='{command[:80]}'")

    # Resolve working directory within workspace
    try:
        resolved_cwd = str(safe_path(cwd))
    except Exception:
        resolved_cwd = str(Path(config.ALLOWED_BASE_PATH).resolve())

    result = await _stream_command(command, cwd=resolved_cwd, timeout=timeout)
    return result.model_dump(exclude_none=True)


@registry.register(
    name="install_package",
    description=(
        "Install a Python or Node.js package. Auto-detects the package manager. "
        "Supports pip, npm, and yarn. Activated for .venv in the current project."
    ),
    parameters={
        "package": {"type": "string", "description": "Package name."},
        "manager": {
            "type": "string", 
            "description": "auto (default), pip, npm, yarn.",
            "default": "auto"
        },
        "cwd": {"type": "string", "description": "Working directory.", "default": "."},
    },
    category="dangerous",
    timeout=120,
)
async def install_package(package: str, manager: str = "auto", cwd: str = ".") -> dict:
    logger.info(f"tool.install_package | START pkg='{package}'")

    try:
        resolved_cwd = str(safe_path(cwd))
    except Exception:
        resolved_cwd = str(Path(config.ALLOWED_BASE_PATH).resolve())

    cwd_path = Path(resolved_cwd)

    if manager == "auto":
        manager = "npm" if (cwd_path / "package.json").exists() else "pip"

    if manager == "pip":
        cmd = f'"{sys.executable}" -m pip install {package}'
    elif manager == "npm":
        cmd = f"npm install {package}"
    elif manager == "yarn":
        cmd = f"yarn add {package}"
    else:
        return InstallOutput(
            status="error", package=package, manager=manager,
            stdout="", stderr="", returncode=-1,
            error=f"Unknown manager '{manager}'"
        ).model_dump(exclude_none=True)

    result = await _stream_command(cmd, cwd=resolved_cwd, timeout=120)

    return InstallOutput(
        status=result.status,
        package=package,
        manager=manager,
        stdout=result.stdout,
        stderr=result.stderr,
        returncode=result.returncode,
        error=result.error
    ).model_dump(exclude_none=True)
