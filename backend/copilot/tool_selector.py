"""
ToolSelector — detects, validates, and executes tool calls from LLM output.

Implements a permission layer separating safe (read-only) tools from
dangerous (write/exec) tools. Dangerous tools require explicit user opt-in.
"""

import asyncio
import json
import logging
import re
from typing import Optional

from mcp_registry.registry import registry
from services.policy_engine import policy_engine
from services.mcp_host import mcp_host

logger = logging.getLogger(__name__)

SAFE_TOOLS = frozenset({
    "list_files",
    "read_file",
    "search_repository",
    "scan_directory",
    "list_issues",
    "fix_file",        # self-contained: reads → LLM-fix → writes back
    "improve_code",    # inline code snippet improvement
    "outline_file",    # code structure mapping
    "read_directory",  # bulk analysis tool
    "write_file",      # restored to safe for autonomy
    "edit_file",       # restored to safe for autonomy
    "create_directory", # promote for autonomy
    "move_item",        # promote for autonomy
    "delete_item",      # promote for autonomy
    "read_resource",    # NEW: Hybrid MCP support
})

# Tools that require explicit confirmation / are high risk
DANGEROUS_TOOLS = frozenset({
    "commit_code",
    "create_github_issue",
    "create_jira_ticket",
})

TOOL_TIMEOUT = 30  # seconds


class ToolSelector:
    def extract_tool_calls(self, text: str) -> list[dict]:
        """Extract <tool>...</tool> JSON blocks from LLM response."""
        calls = []
        
        # 1. Handle standard closed tags
        for match in re.finditer(r"<tool>(.*?)</tool>", text, re.DOTALL):
            calls.append(self._parse_raw_call(match.group(1).strip()))

        # 2. Resiliency: Check for an unclosed <tool> tag at the VERY end
        # Sometimes the LLM cuts off before </tool>
        last_open = text.rfind("<tool>")
        last_close = text.rfind("</tool>")
        
        if last_open > last_close:
            raw = text[last_open + 6:].strip()
            # Only attempt to heal if there's actually some content after <tool>
            if raw:
                logger.info(f"tool_selector.extract | HEALING_UNCLOSED_TAG raw_start='{raw[:50]}...'")
                # Heuristic: Append closing brace if missing, but be careful not to double-close
                # Calculate balanced braces
                diff = raw.count('{') - raw.count('}')
                if diff > 0:
                    raw += '}' * diff
                
                healed_call = self._parse_raw_call(raw)
                if healed_call:
                    calls.append(healed_call)
                else:
                    # Deep healing: try to find the last key-value pair and close it
                    # This is specifically for when the JSON is truncated mid-string
                    if '"' in raw:
                        # Find index of last double quote
                        last_quote = raw.rfind('"')
                        # If odd number of quotes, close the last one
                        if raw.count('"') % 2 != 0:
                            raw = raw[:last_quote+1] + '"'
                        # Now try closing the object
                        if not raw.strip().endswith('}'):
                            raw += '}'
                        if '{' not in raw:
                            raw = '{' + raw
                            
                        healed_call = self._parse_raw_call(raw)
                        if healed_call:
                            calls.append(healed_call)

        # 3. Fallback: Search for raw JSON blocks if no tags were found
        # This is high-risk but necessary for models that ignore the tag instructions.
        if not calls:
            # Match likely JSON objects: starts with {"name":, contains "parameters":, ends with }
            # We use a non-greedy approach and try to parse.
            pattern = r'\{[^{}]*?"name"\s*:\s*".+?"\s*,\s*"parameters"\s*:\s*\{.*?\}[^{}]*?\}'
            for match in re.finditer(pattern, text, re.DOTALL):
                raw = match.group(0)
                parsed = self._parse_raw_call(raw)
                if parsed and "name" in parsed and "parameters" in parsed:
                    calls.append(parsed)

        return [c for c in calls if c]

    def _parse_raw_call(self, raw: str) -> Optional[dict]:
        """Parse raw content from inside tool tags, with ultra-robust recovery."""
        if not raw:
            return None

        # 1. Resiliency: Clean up outer noise
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
            raw = raw.strip()

        # 2. Resiliency: Normalize boundaries
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
             logger.warning(f"tool_selector.parse_failed | NO_BRACES_FOUND raw={raw[:100]!r}")
             return None
        
        raw_json = raw[start : end + 1]

        # 3. Standard parsing
        try:
            return json.loads(raw_json)
        except json.JSONDecodeError:
            pass

        # 4. Resiliency: Greedy Peeling (handles extra braces/garbage)
        # We try to find the SMALLEST valid JSON starting from the first {
        # This fixes cases where the model appends extra }} or garbage after the object.
        for i in range(len(raw_json), start, -1):
            char = raw_json[i-1]
            if char != '}':
                continue
            
            candidate = raw_json[:i]
            try:
                result = json.loads(candidate)
                # Success! But verify it has required tool call fields
                if isinstance(result, dict) and "name" in result:
                    logger.info(f"tool_selector.peeler | RECOVERED_JSON peeled={len(raw_json)-i} chars")
                    return result
            except json.JSONDecodeError:
                continue

        # 5. Fallback: Deep Recovery for unescaped quotes (common in write_file/edit_file)
        try:
            name_match = re.search(r'"name":\s*"([^"]+)"', raw)
            if name_match:
                name = name_match.group(1)
                params_start = raw.find('"parameters":')
                if params_start != -1:
                    # Find first { after parameters
                    obj_start = raw.find("{", params_start)
                    if obj_start != -1:
                        # Try to extract params by counting braces
                        count = 0
                        for j in range(obj_start, len(raw)):
                            if raw[j] == '{': count += 1
                            elif raw[j] == '}': count -= 1
                            
                            if count == 0:
                                params_raw = raw[obj_start : j + 1]
                                try:
                                    params = json.loads(params_raw)
                                    logger.info(f"tool_selector.brace_counter | RECOVERED_TOOL_CALL tool='{name}'")
                                    return {"name": name, "parameters": params}
                                except:
                                    break
        except Exception:
            pass

        logger.warning(f"tool_selector.parse_failed | ALL_METHODS_FAILED raw={raw!r}")
        return None

    def classify_call(self, call: dict) -> str:
        """Return 'safe', 'dangerous', or 'rejected' based on policy engine."""
        name = call.get("name", "")
        params = call.get("parameters", {})
        
        # New Policy-driven classification
        status, reason = policy_engine.validate_call(name, params)
        
        if status == "REJECTED":
            return "rejected"
        if status == "CONFIRM_REQUIRED":
            return "dangerous"
            
        classification = policy_engine.get_classification(name)
        if classification != "unknown":
            return classification
            
        return "unknown"

    async def execute_safe(self, calls: list[dict]) -> list[dict]:
        """Execute tool calls. Safe ones are run in parallel via asyncio.gather."""
        tasks = []
        
        for call in calls:
            classification = self.classify_call(call)
            name = call.get("name", "")
            params = call.get("parameters", {})

            if classification == "rejected":
                # Get the policy reason
                _, reason = policy_engine.validate_call(name, params)
                tasks.append(self._wrap_as_coro({
                    "tool": name,
                    "status": "error",
                    "error": f"Security Policy Violation: {reason}",
                    "hint": "Please adjust your parameters to stay within the allowed workspace and avoid protected files."
                }))
                continue

            if classification == "dangerous":
                logger.info(f"tool_selector.classify | DANGEROUS_TOOL_WAITING tool='{name}'")
                _, reason = policy_engine.validate_call(name, params)
                tasks.append(self._wrap_as_coro({
                    "tool": name,
                    "status": "requires_confirmation",
                    "reason": reason or "user_approval_required",
                    "parameters": params,
                    "message": f"Tool `{name}` requires confirmation. {reason}",
                }))
                continue

            if classification == "unknown":
                tasks.append(self._wrap_as_coro({
                    "tool": name,
                    "status": "error",
                    "error": f"Unknown tool: {name}",
                }))
                continue

            # Schedule safe tool for parallel execution
            tasks.append(self._execute_with_timeout(name, params))

        if not tasks:
            return []
            
        return list(await asyncio.gather(*tasks))

    async def _wrap_as_coro(self, val):
        return val

    async def execute_any(self, calls: list[dict]) -> list[dict]:
        """Execute all tool calls including dangerous ones (explicit user action)."""
        results = []
        for call in calls:
            name = call.get("name", "")
            params = call.get("parameters", {})
            result = await self._execute_with_timeout(name, params)
            results.append(result)
        return results

    async def _execute_with_timeout(self, name: str, params: dict) -> dict:
        """Execute a single tool call, respecting the tool's own registered timeout."""
        logger.info(
            f"🛠️ [STARTING TOOL] | tool='{name}' params={list(params.keys())}"
        )
        # Use the tool's own timeout if registered, else fall back to global TOOL_TIMEOUT
        tool_obj = registry.get_tool(name)
        timeout = tool_obj.timeout if tool_obj else TOOL_TIMEOUT

        try:
            # All execution now routes through mcp_host for O(1) lookup and remote support
            result = await asyncio.wait_for(
                mcp_host.execute(name, params),
                timeout=timeout,
            )
            
            logger.info("tool_selector.success", extra={"tool": name})
            return result
        except asyncio.TimeoutError:
            logger.error("tool_selector.timeout", extra={"tool": name})
            return {
                "tool": name,
                "status": "error",
                "error": f"Tool '{name}' timed out after {timeout}s",
            }
        except Exception as e:
            logger.error("tool_selector.error", extra={"tool": name, "error": str(e)})
            return {"tool": name, "status": "error", "error": str(e)}

    def get_tool_categories(self) -> dict:
        return {
            "safe": list(SAFE_TOOLS),
            "dangerous": list(DANGEROUS_TOOLS),
        }


# Singleton instance
tool_selector = ToolSelector()
