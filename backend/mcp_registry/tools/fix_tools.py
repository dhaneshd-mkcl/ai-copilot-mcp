"""
fix_tools.py — MCP tools for AI-powered code fixing and improvement.

The `fix_file` tool is self-contained:
  1. Reads the file from the workspace
  2. Calls the Ollama LLM directly (with a generous timeout)
  3. Writes the fixed code back to the same file
  4. Returns a summary of what was changed

This avoids the problem of the LLM needing to OUTPUT the entire fixed file
through the chat SSE stream (which hits token limits and timeouts).
"""

import logging
import re
import aiohttp
from pathlib import Path
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)

class FixFileOutput(BaseModel):
    status: str
    file: Optional[str] = None
    backup: Optional[str] = None
    original_lines: Optional[int] = None
    fixed_lines: Optional[int] = None
    size_original: Optional[int] = None
    size_fixed: Optional[int] = None
    summary: Optional[str] = None
    error: Optional[str] = None

class ImproveCodeOutput(BaseModel):
    status: str
    improved_code: Optional[str] = None
    language: Optional[str] = None
    error: Optional[str] = None

from config import config
from mcp_registry.registry import registry

# ── safety ──────────────────────────────────────────────────────────────────

from copilot.utils import safe_path, get_backup_path


# ── helpers ──────────────────────────────────────────────────────────────────

def _strip_markdown_fences(text: str) -> str:
    """Remove ```lang ... ``` fences the LLM wraps code in."""
    # Try to extract a fenced code block
    m = re.search(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    # Remove any leading/trailing fence lines without content match
    text = re.sub(r"^```\w*\n?", "", text.strip())
    text = re.sub(r"```\s*$", "", text.strip())
    return text.strip()


async def _call_llm(prompt: str, timeout_s: int = 300) -> str:
    """Call Ollama directly with a long timeout. Returns raw text response."""
    payload = {
        "model": config.LLM_MODEL,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert software engineer. When asked to fix or improve code, "
                    "output ONLY the complete, corrected source code with NO explanations, "
                    "NO markdown fences, NO commentary — just the raw code."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    url = f"{config.LLM_BASE_URL}/api/chat"
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data.get("message", {}).get("content", "").strip()


# ── registered tools ─────────────────────────────────────────────────────────

@registry.register(
    name="fix_file",
    description=(
        "Read a code file from the workspace, ask the LLM to fix ALL bugs and improve it, "
        "then write the corrected version back. Returns a summary of changes. "
        "IMPORTANT: Uploaded files are usually in the workspace root. If you aren't sure of the path, check list_files first."
    ),
    parameters={
        "path": {
            "type": "string",
            "description": "File path relative to workspace root (e.g. 'chat_service.py')",
        },
        "instructions": {
            "type": "string",
            "description": "What to fix/improve (e.g. 'fix all bugs and add type hints')",
            "default": "Fix all bugs, remove duplicate imports, improve error handling, add type hints",
        },
    },
    category="safe",
    timeout=360,   # generous: LLM may take several minutes for large files
)
async def fix_file(path: str, instructions: str = "Fix all bugs, remove duplicate imports, improve error handling, add type hints") -> dict:
    logger.info(f"tool.fix_file | START path='{path}' instr='{instructions[:50]}...'")
    """Read → LLM-fix → write back. Returns summary of changes."""
    # Attempt 1: Exact path
    try:
        target = safe_path(path)
    except Exception:
        target = None

    # Attempt 2: Auto-discovery. If path is "dir/file.py" but it only exists in root as "file.py"
    if not target or not target.exists():
        filename = Path(path).name
        root_target = safe_path(filename)
        if root_target.exists():
            target = root_target
            path = filename # update path for logging
            
    if not target or not target.exists():
        return FixFileOutput(
            status="error", 
            error=f"File not found: {path}. Try calling list_files('.') to see available files."
        ).model_dump(exclude_none=True)
    if not target.is_file():
        return FixFileOutput(status="error", error=f"Not a file: {path}").model_dump(exclude_none=True)

    original = target.read_text(encoding="utf-8", errors="replace")
    size = len(original)

    # Warn if file is very large (> 500 lines) — LLM may struggle
    line_count = original.count("\n")
    if line_count > 800:
        return FixFileOutput(
            status="error",
            error=(
                f"File too large ({line_count} lines). Split it into smaller modules first, "
                "then run fix_file on each part."
            ),
        ).model_dump(exclude_none=True)

    prompt = (
        f"Here is the file `{path}` ({line_count} lines).\n\n"
        f"Task: {instructions}\n\n"
        "Rules:\n"
        "- Output ONLY the complete fixed source code\n"
        "- Do NOT add any explanation, comments about changes, or markdown fences\n"
        "- Preserve all existing functionality\n"
        "- Keep all existing imports that are actually used\n"
        "- **STRICT**: Do NOT add new features, irrelevant libraries, or architectural components (like SQL/Charts) unless explicitly requested.\n"
        "- **STRICT**: Focus only on fixing bugs, improving existing logic, and code quality.\n\n"
        f"--- BEGIN FILE ---\n{original}\n--- END FILE ---\n\n"
        "Now output the complete fixed code:"
    )

    fixed_raw = await _call_llm(prompt, timeout_s=300)
    fixed_code = _strip_markdown_fences(fixed_raw)

    if not fixed_code or len(fixed_code) < 10:
        return FixFileOutput(status="error", error="LLM returned empty or invalid response").model_dump(exclude_none=True)

    # Create centralized backup
    backup_path = get_backup_path(target)
    import shutil
    shutil.copy2(target, backup_path)
    logger.info(f"fixed.backup_created: {backup_path}")
    
    target.write_text(fixed_code, encoding="utf-8")

    orig_lines = original.count("\n") + 1
    fixed_lines = fixed_code.count("\n") + 1

    return FixFileOutput(
        status="success",
        file=path,
        backup=str(backup_path),
        original_lines=orig_lines,
        fixed_lines=fixed_lines,
        size_original=size,
        size_fixed=len(fixed_code),
        summary=(
            f"Fixed `{path}`: {orig_lines} → {fixed_lines} lines. "
            f"Original backed up in `others/backups/`."
        ),
    ).model_dump(exclude_none=True)


@registry.register(
    name="improve_code",
    description=(
        "Take a snippet of code (as text), fix bugs and improve it, "
        "then return the improved version directly in chat. "
        "Use this for short code snippets (<200 lines) pasted by the user."
    ),
    parameters={
        "code": {
            "type": "string",
            "description": "The code snippet to fix and improve",
        },
        "language": {
            "type": "string",
            "description": "Programming language",
            "default": "python",
        },
        "instructions": {
            "type": "string",
            "description": "What to fix/improve",
            "default": "Fix all bugs and improve code quality",
        },
    },
    category="safe",
    timeout=120,
)
async def improve_code(code: str, language: str = "python", instructions: str = "Fix all bugs and improve code quality") -> dict:
    logger.info(f"tool.improve_code | START lang='{language}' instr='{instructions[:50]}...' code_len={len(code)}")
    """Fix and improve a code snippet, returning the result directly."""
    prompt = (
        f"Language: {language}\n"
        f"Task: {instructions}\n\n"
        "Rules:\n"
        "- Output ONLY the complete improved code (no explanations)\n"
        "- Add a brief comment at the top listing the key changes made\n\n"
        f"Code to fix:\n```{language}\n{code}\n```\n\n"
        "Output the improved code:"
    )

    fixed_raw = await _call_llm(prompt, timeout_s=120)
    fixed_code = _strip_markdown_fences(fixed_raw)

    return ImproveCodeOutput(
        status="success",
        improved_code=fixed_code,
        language=language,
    ).model_dump(exclude_none=True)
