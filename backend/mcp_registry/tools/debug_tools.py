"""
debug_tools.py — Advanced debugging and API client generation tools.

Provides:
  - debug_with_breakpoint: Temporarily inject a pdb trace at a line and capture output.
  - generate_api_client: Generate a typed Python or JS client from an OpenAPI spec.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel

from mcp_registry.registry import registry
from copilot.utils import safe_path
from config import config

logger = logging.getLogger(__name__)


# ─── Output Models ─────────────────────────────────────────────────────────────

class BreakpointOutput(BaseModel):
    status: str
    file: str
    line: int
    output: Optional[str] = None
    error: Optional[str] = None


class ApiEndpoint(BaseModel):
    method: str
    path: str
    operation_id: Optional[str] = None
    summary: Optional[str] = None
    parameters: List[str] = []
    request_body: Optional[str] = None
    response_type: Optional[str] = None


class ApiClientOutput(BaseModel):
    status: str
    language: str
    source: str
    endpoints_count: int
    client_code: Optional[str] = None
    error: Optional[str] = None


# ─── debug_with_breakpoint ──────────────────────────────────────────────────────

@registry.register(
    name="debug_with_breakpoint",
    description=(
        "Temporarily inject a Python pdb breakpoint at a specific line in a file, "
        "run the file, capture the first N lines of debugger output, then restore the file. "
        "Great for inspecting variable state mid-execution. Requires Python file. "
        "Dangerous — confirms before use."
    ),
    parameters={
        "path": {"type": "string", "description": "Path to the Python file (relative to workspace)."},
        "line": {"type": "integer", "description": "Line number to inject the breakpoint after (1-indexed)."},
        "capture_lines": {
            "type": "integer",
            "description": "Number of debugger output lines to capture (default: 20).",
            "default": 20,
        },
    },
    category="dangerous",
    timeout=30,
)
async def debug_with_breakpoint(path: str, line: int, capture_lines: int = 20) -> dict:
    logger.info(f"tool.debug_with_breakpoint | START path='{path}' line={line}")

    target = safe_path(path)
    if not target.is_file() or target.suffix != ".py":
        return BreakpointOutput(
            status="error", file=path, line=line,
            error="Only Python (.py) files are supported."
        ).model_dump(exclude_none=True)

    original_content = target.read_text(encoding="utf-8")
    lines = original_content.splitlines(keepends=True)

    if line < 1 or line > len(lines):
        return BreakpointOutput(
            status="error", file=path, line=line,
            error=f"Line {line} is out of range (file has {len(lines)} lines)."
        ).model_dump(exclude_none=True)

    # Detect indentation at target line
    target_line = lines[line - 1]
    indent = len(target_line) - len(target_line.lstrip())
    indent_str = " " * indent

    # Inject pdb trace
    breakpoint_line = f"{indent_str}import pdb; pdb.set_trace()  # AUTO-INJECTED BY TITAN\n"
    patched_lines = lines[:line - 1] + [breakpoint_line] + lines[line - 1:]
    patched_content = "".join(patched_lines)

    try:
        target.write_text(patched_content, encoding="utf-8")
        logger.info(f"tool.debug_with_breakpoint | INJECTED at line {line}")

        # Run with pdb in batch mode (non-interactive: quit immediately after trace)
        cmds = "n\n" * capture_lines + "q\n"
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pdb", str(target),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout_bytes, _ = await asyncio.wait_for(
                proc.communicate(input=cmds.encode()), timeout=15
            )
        except asyncio.TimeoutError:
            proc.kill()
            stdout_bytes = b"[pdb session timed out after 15s]"

        output = stdout_bytes.decode("utf-8", errors="replace")

    finally:
        # Always restore original file
        target.write_text(original_content, encoding="utf-8")
        logger.info(f"tool.debug_with_breakpoint | RESTORED original file")

    return BreakpointOutput(
        status="success",
        file=path,
        line=line,
        output=output[:3000],  # Cap to avoid flooding context
    ).model_dump(exclude_none=True)


# ─── generate_api_client ────────────────────────────────────────────────────────

async def _fetch_spec(source: str) -> dict:
    """Fetch and parse an OpenAPI spec from a URL or local file path."""
    import aiohttp

    if source.startswith("http://") or source.startswith("https://"):
        async with aiohttp.ClientSession() as session:
            async with session.get(source, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                resp.raise_for_status()
                text = await resp.text()
    else:
        file_path = safe_path(source)
        text = file_path.read_text(encoding="utf-8")

    # Try JSON first, then YAML
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml
            return yaml.safe_load(text)
        except Exception:
            raise ValueError("Could not parse spec as JSON or YAML.")


def _extract_endpoints(spec: dict) -> List[ApiEndpoint]:
    """Extract endpoint info from an OpenAPI 3.x or Swagger 2.x spec."""
    endpoints = []
    paths = spec.get("paths", {})

    for path, path_item in paths.items():
        for method in ["get", "post", "put", "patch", "delete", "head", "options"]:
            operation = path_item.get(method)
            if not operation:
                continue

            params = [
                p.get("name", "?") for p in operation.get("parameters", [])
            ]
            body = None
            if "requestBody" in operation:
                content = operation["requestBody"].get("content", {})
                body = list(content.keys())[0] if content else "body"

            endpoints.append(ApiEndpoint(
                method=method.upper(),
                path=path,
                operation_id=operation.get("operationId"),
                summary=operation.get("summary"),
                parameters=params,
                request_body=body,
            ))

    return endpoints


def _generate_python_client(endpoints: List[ApiEndpoint], base_url: str, api_title: str) -> str:
    """Generate a typed Python httpx client."""
    lines = [
        '"""',
        f'Auto-generated Python client for: {api_title}',
        'Generated by Titan MKCL AI — debug_tools.generate_api_client',
        '"""',
        "",
        "import httpx",
        "from typing import Any, Optional, Dict",
        "",
        "",
        "class APIClient:",
        f'    BASE_URL = "{base_url}"',
        "",
        "    def __init__(self, api_key: Optional[str] = None):",
        "        headers = {'Content-Type': 'application/json'}",
        "        if api_key:",
        "            headers['Authorization'] = f'Bearer {api_key}'",
        "        self.client = httpx.AsyncClient(base_url=self.BASE_URL, headers=headers)",
        "",
        "    async def close(self):",
        "        await self.client.aclose()",
        "",
    ]

    for ep in endpoints:
        fn_name = ep.operation_id or f"{ep.method.lower()}_{ep.path.strip('/').replace('/', '_').replace('{', '').replace('}', '')}"
        fn_name = fn_name.replace("-", "_").lower()

        args = ["self"]
        for p in ep.parameters:
            args.append(f"{p}: Any")
        if ep.request_body:
            args.append("body: Dict[str, Any] = None")

        path_formatted = ep.path
        for p in ep.parameters:
            if "{" + p + "}" in ep.path:
                path_formatted = path_formatted.replace("{" + p + "}", "{" + p + "}")

        lines.append(f"    async def {fn_name}({', '.join(args)}) -> Any:")
        if ep.summary:
            lines.append(f'        """{ep.summary}"""')
        if ep.request_body:
            lines.append(f"        resp = await self.client.{ep.method.lower()}(f\"{path_formatted}\", json=body)")
        else:
            lines.append(f"        resp = await self.client.{ep.method.lower()}(f\"{path_formatted}\")")
        lines.append("        resp.raise_for_status()")
        lines.append("        return resp.json()")
        lines.append("")

    return "\n".join(lines)


def _generate_js_client(endpoints: List[ApiEndpoint], base_url: str, api_title: str) -> str:
    """Generate a typed JavaScript fetch-based client."""
    lines = [
        "/**",
        f" * Auto-generated JS client for: {api_title}",
        " * Generated by Titan MKCL AI — generate_api_client",
        " */",
        "",
        f'const BASE_URL = "{base_url}";',
        "",
        "async function apiFetch(method, path, body = null, headers = {}) {",
        "  const res = await fetch(`${BASE_URL}${path}`, {",
        "    method,",
        "    headers: { 'Content-Type': 'application/json', ...headers },",
        "    body: body ? JSON.stringify(body) : undefined,",
        "  });",
        "  if (!res.ok) throw new Error(`API Error: ${res.status} ${res.statusText}`);",
        "  return res.json();",
        "}",
        "",
        "const api = {",
    ]

    for ep in endpoints:
        fn_name = ep.operation_id or f"{ep.method.lower()}{ep.path.strip('/').replace('/', '_').title().replace('{', '').replace('}', '')}"
        fn_name = fn_name.replace("-", "_")

        params = list(ep.parameters)
        path_js = ep.path
        for p in params:
            path_js = path_js.replace("{" + p + "}", "${" + p + "}")

        fn_params = params[:]
        if ep.request_body:
            fn_params.append("body = {}")

        args_str = ", ".join(fn_params)
        lines.append(f"  /** {ep.summary or ep.path} */")
        if ep.request_body:
            lines.append(f"  {fn_name}: ({args_str}) => apiFetch('{ep.method}', `{path_js}`, body),")
        else:
            lines.append(f"  {fn_name}: ({args_str}) => apiFetch('{ep.method}', `{path_js}`),")

    lines += ["};", "", "export default api;"]
    return "\n".join(lines)


@registry.register(
    name="generate_api_client",
    description=(
        "Generate a fully typed API client from an OpenAPI 3.x or Swagger 2.x spec. "
        "Accepts a URL (https://...) or a local file path (.json/.yaml). "
        "Outputs a Python (httpx-based) or JavaScript (fetch-based) client. "
        "Safe — reads spec and generates code, does not write files automatically."
    ),
    parameters={
        "source": {
            "type": "string",
            "description": "URL or local file path to the OpenAPI spec (JSON or YAML)."
        },
        "language": {
            "type": "string",
            "description": "Output language: 'python' (default) or 'javascript'.",
            "default": "python",
        },
        "base_url": {
            "type": "string",
            "description": "Override the base URL for the API (e.g. 'http://localhost:8000').",
            "default": "",
        },
    },
    category="safe",
    timeout=30,
)
async def generate_api_client(source: str, language: str = "python", base_url: str = "") -> dict:
    logger.info(f"tool.generate_api_client | START source='{source}' lang='{language}'")

    try:
        spec = await _fetch_spec(source)
    except Exception as e:
        return ApiClientOutput(
            status="error", language=language, source=source,
            endpoints_count=0, error=f"Failed to load spec: {str(e)}"
        ).model_dump(exclude_none=True)

    # Extract metadata
    info = spec.get("info", {})
    api_title = info.get("title", "API")
    api_version = info.get("version", "1.0")

    # Resolve base URL
    if not base_url:
        servers = spec.get("servers", [])
        base_url = servers[0].get("url", "http://localhost") if servers else "http://localhost"

    endpoints = _extract_endpoints(spec)

    if not endpoints:
        return ApiClientOutput(
            status="error", language=language, source=source,
            endpoints_count=0, error="No endpoints found in the spec."
        ).model_dump(exclude_none=True)

    # Generate client code
    if language == "python":
        client_code = _generate_python_client(endpoints, base_url, api_title)
    elif language == "javascript":
        client_code = _generate_js_client(endpoints, base_url, api_title)
    else:
        return ApiClientOutput(
            status="error", language=language, source=source,
            endpoints_count=0, error=f"Unsupported language '{language}'. Use 'python' or 'javascript'."
        ).model_dump(exclude_none=True)

    logger.info(f"tool.generate_api_client | SUCCESS endpoints={len(endpoints)} lang={language}")
    return ApiClientOutput(
        status="success",
        language=language,
        source=source,
        endpoints_count=len(endpoints),
        client_code=client_code,
    ).model_dump(exclude_none=True)
