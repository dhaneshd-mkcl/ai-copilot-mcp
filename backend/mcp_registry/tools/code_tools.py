import asyncio
import shutil
import tempfile
import os
import logging
from pathlib import Path
from mcp_registry.registry import registry
from config import config

from pydantic import BaseModel
from typing import Optional, List

logger = logging.getLogger(__name__)

class CommandOutput(BaseModel):
    returncode: int
    stdout: str
    stderr: str
    error: Optional[str] = None

class FormatOutput(BaseModel):
    formatted_code: str
    changed: bool
    note: Optional[str] = None
    error: Optional[str] = None

class EditOutput(BaseModel):
    path: str
    status: str
    backup: Optional[str] = None
    matches: int
    size_delta: int
    error: Optional[str] = None


from copilot.utils import safe_path

def _safe_path(path: str) -> Path:
    return safe_path(path)


async def _run_command(cmd: list[str], cwd: str = None, timeout: int = 30) -> CommandOutput:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return CommandOutput(
            returncode=proc.returncode,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )
    except asyncio.TimeoutError:
        return CommandOutput(returncode=-1, stdout="", stderr=f"Command timed out after {timeout}s")
    except FileNotFoundError as e:
        return CommandOutput(returncode=-1, stdout="", stderr=f"Command not found: {e}")


@registry.register(
    name="run_linter",
    description="Run a linter on code (pylint for Python, eslint for JS/TS)",
    parameters={
        "path": {"type": "string", "description": "File or directory to lint"},
        "language": {"type": "string", "description": "Language: python, javascript, typescript", "default": "python"},
    },
    category="dangerous",
    timeout=45,
)
async def run_linter(path: str, language: str = "python") -> dict:
    logger.info(f"tool.run_linter | START path='{path}' lang='{language}'")
    target = _safe_path(path)
    res = None
    if language == "python":
        if shutil.which("pylint"):
            res = await _run_command(["pylint", "--output-format=json", str(target)], timeout=45)
        elif shutil.which("flake8"):
            res = await _run_command(["flake8", str(target)], timeout=45)
        else:
            res = CommandOutput(returncode=-1, stdout="", stderr="No Python linter found (install pylint or flake8)")
    elif language in ("javascript", "typescript"):
        if shutil.which("eslint"):
            res = await _run_command(["eslint", "--format=json", str(target)], timeout=45)
        else:
            res = CommandOutput(returncode=-1, stdout="", stderr="eslint not found")
    else:
        res = CommandOutput(returncode=-1, stdout="", stderr=f"Unsupported language: {language}")
    
    return res.model_dump(exclude_none=True)


@registry.register(
    name="run_tests",
    description="Run test suite for a project",
    parameters={
        "path": {"type": "string", "description": "Project path", "default": "."},
        "framework": {"type": "string", "description": "Test framework: pytest, jest, unittest", "default": "pytest"},
    },
    category="dangerous",
    timeout=60,
)
async def run_tests(path: str = ".", framework: str = "pytest") -> dict:
    logger.info(f"tool.run_tests | START path='{path}' framework='{framework}'")
    target = _safe_path(path)
    res = None
    if framework == "pytest":
        res = await _run_command(["python", "-m", "pytest", "--tb=short", "-q"], cwd=str(target), timeout=60)
    elif framework == "jest":
        res = await _run_command(["npx", "jest", "--passWithNoTests"], cwd=str(target), timeout=60)
    elif framework == "unittest":
        res = await _run_command(["python", "-m", "unittest", "discover", "-v"], cwd=str(target), timeout=60)
    else:
        res = CommandOutput(returncode=-1, stdout="", stderr=f"Unknown framework: {framework}")
    
    # Ensure meaningfully failed results are marked as error for registry.py
    out_dict = res.model_dump(exclude_none=True)
    if out_dict.get("returncode") != 0:
        error_msg = out_dict.get("stderr") or out_dict.get("stdout") or f"Command failed (code {out_dict.get('returncode')})"
        out_dict["error"] = error_msg
    
    return out_dict


@registry.register(
    name="format_code",
    description="Format code using appropriate formatter (black for Python, prettier for JS/TS)",
    parameters={
        "code": {"type": "string", "description": "Code content to format"},
        "language": {"type": "string", "description": "Language: python, javascript, typescript", "default": "python"},
    },
    category="dangerous",
    timeout=20,
)
async def format_code(code: str, language: str = "python") -> dict:
    logger.info(f"tool.format_code | START lang='{language}' code_len={len(code)}")
    suffix = {
        "python": ".py", "javascript": ".js", "typescript": ".ts",
        "html": ".html", "css": ".css",
    }.get(language, ".txt")

    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp_path = f.name

    try:
        if language == "python" and shutil.which("black"):
            result = await _run_command(["black", "--quiet", tmp_path], timeout=20)
            if result.returncode == 0:
                formatted = Path(tmp_path).read_text(encoding="utf-8")
                return FormatOutput(formatted_code=formatted, changed=formatted != code).model_dump(exclude_none=True)
        elif language in ("javascript", "typescript") and shutil.which("prettier"):
            result = await _run_command(["prettier", "--write", tmp_path], timeout=20)
            if result.returncode == 0:
                formatted = Path(tmp_path).read_text(encoding="utf-8")
                return FormatOutput(formatted_code=formatted, changed=formatted != code).model_dump(exclude_none=True)
        return FormatOutput(formatted_code=code, changed=False, note="No formatter available or failed").model_dump(exclude_none=True)
    except Exception as e:
        return FormatOutput(formatted_code=code, changed=False, error=str(e)).model_dump(exclude_none=True)
    finally:
        os.unlink(tmp_path)
@registry.register(
    name="edit_file",
    description=(
        "Surgically edit a file by replacing a specific search string with a new string. "
        "The search string MUST be unique within the file. Returns the number of changes made."
    ),
    parameters={
        "path": {"type": "string", "description": "File path relative to workspace"},
        "search_str": {"type": "string", "description": "The exact block of code to search for"},
        "replace_str": {"type": "string", "description": "The new block of code to replace it with"},
    },
    category="dangerous",
    timeout=30,
)
async def edit_file(path: str, search_str: str, replace_str: str) -> dict:
    logger.info(f"tool.edit_file | START path='{path}' search_len={len(search_str)}")
    target = _safe_path(path)
    if not target.is_file():
        return EditOutput(path=str(path), status="error", error=f"File '{path}' not found", matches=0, size_delta=0).model_dump(exclude_none=True)
    
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        
        # Safety: check uniqueness
        count = content.count(search_str)
        if count == 0:
            return EditOutput(path=str(path), status="error", error="Search string not found. Ensure you provided the exact text, including whitespace.", matches=0, size_delta=0).model_dump(exclude_none=True)
        if count > 1:
            return EditOutput(path=str(path), status="error", error=f"Search string found {count} times. Please provide a more specific/unique block of code.", matches=count, size_delta=0).model_dump(exclude_none=True)
        
        # Create a backup before editing
        backup = target.with_suffix(target.suffix + ".bak")
        backup.write_text(content, encoding="utf-8")
        
        new_content = content.replace(search_str, replace_str)
        target.write_text(new_content, encoding="utf-8")
        
        return EditOutput(
            path=str(path),
            status="edited",
            backup=str(backup.name),
            matches=count,
            size_delta=len(new_content) - len(content)
        ).model_dump(exclude_none=True)
    except Exception as e:
        return EditOutput(path=str(path), status="error", error=str(e), matches=0, size_delta=0).model_dump(exclude_none=True)
