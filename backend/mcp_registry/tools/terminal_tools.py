"""
terminal_tools.py — Shell execution tools with live streaming output.

Provides:
  - run_in_terminal: Execute any shell command and capture streaming output.
  - install_package: Auto-detect pip/npm and install a package.
"""

import asyncio
import logging
import shutil
import sys
from pathlib import Path
from typing import Optional
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
    Run a shell command, streaming stdout+stderr and capturing all output.
    Returns a structured result with combined output.
    """
    import time
    start = time.monotonic()

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            shell=True,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            elapsed = int((time.monotonic() - start) * 1000)
            return TerminalOutput(
                status="error",
                command=cmd,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                returncode=-1,
                duration_ms=elapsed,
                error=f"Timeout after {timeout}s",
            )

        elapsed = int((time.monotonic() - start) * 1000)
        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
        ok = proc.returncode == 0

        return TerminalOutput(
            status="success" if ok else "error",
            command=cmd,
            stdout=stdout[:8000],  # Cap output to prevent flooding context
            stderr=stderr[:2000],
            returncode=proc.returncode,
            duration_ms=elapsed,
            error=stderr[:500] if not ok and stderr else None,
        )

    except FileNotFoundError as e:
        return TerminalOutput(
            status="error", command=cmd, stdout="", stderr=str(e),
            returncode=-1, duration_ms=0, error=f"Command not found: {e}"
        )
    except Exception as e:
        return TerminalOutput(
            status="error", command=cmd, stdout="", stderr=str(e),
            returncode=-1, duration_ms=0, error=str(e)
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
    logger.info(f"tool.run_in_terminal | START cmd='{command[:80]}' cwd='{cwd}'")

    # Resolve working directory within workspace
    try:
        resolved_cwd = str(safe_path(cwd))
    except Exception:
        resolved_cwd = str(Path(config.ALLOWED_BASE_PATH).resolve())

    result = await _stream_command(command, cwd=resolved_cwd, timeout=timeout)
    logger.info(
        f"tool.run_in_terminal | DONE returncode={result.returncode} "
        f"duration={result.duration_ms}ms"
    )
    return result.model_dump(exclude_none=True)


@registry.register(
    name="install_package",
    description=(
        "Install a Python or Node.js package. Auto-detects the package manager: "
        "uses 'pip install' for Python packages and 'npm install' for Node.js packages. "
        "Detects .venv if present and activates it. Dangerous — requires confirmation."
    ),
    parameters={
        "package": {
            "type": "string",
            "description": "Package name (e.g. 'requests', 'fastapi', 'axios')."
        },
        "manager": {
            "type": "string",
            "description": "Package manager: 'auto' (default), 'pip', 'npm', 'yarn'.",
            "default": "auto"
        },
        "cwd": {
            "type": "string",
            "description": "Working directory relative to workspace.",
            "default": "."
        },
    },
    category="dangerous",
    timeout=120,
)
async def install_package(package: str, manager: str = "auto", cwd: str = ".") -> dict:
    logger.info(f"tool.install_package | START pkg='{package}' manager='{manager}'")

    try:
        resolved_cwd = str(safe_path(cwd))
    except Exception:
        resolved_cwd = str(Path(config.ALLOWED_BASE_PATH).resolve())

    cwd_path = Path(resolved_cwd)

    # Auto-detect manager
    if manager == "auto":
        if (cwd_path / "package.json").exists():
            manager = "npm"
        else:
            manager = "pip"

    # Build the install command
    if manager == "pip":
        # Use the current Python interpreter to ensure correct env
        python_exec = sys.executable
        cmd = f'"{python_exec}" -m pip install {package}'
    elif manager == "npm":
        cmd = f"npm install {package}"
    elif manager == "yarn":
        cmd = f"yarn add {package}"
    else:
        return InstallOutput(
            status="error", package=package, manager=manager,
            stdout="", stderr="", returncode=-1,
            error=f"Unknown manager '{manager}'. Use: pip, npm, yarn, or auto."
        ).model_dump(exclude_none=True)

    logger.info(f"tool.install_package | RUNNING cmd='{cmd}'")
    result = await _stream_command(cmd, cwd=resolved_cwd, timeout=120)

    return InstallOutput(
        status=result.status,
        package=package,
        manager=manager,
        stdout=result.stdout,
        stderr=result.stderr,
        returncode=result.returncode,
        error=result.error,
    ).model_dump(exclude_none=True)
