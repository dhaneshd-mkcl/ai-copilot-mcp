"""
PromptBuilder — builds structured prompts from templates.

Loads prompt templates from the /prompts directory and formats them
with dynamic context. Keeps all prompt logic out of the engine.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from mcp_registry.registry import registry
from services.mcp_host import mcp_host
from config import config

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

TASK_PROMPTS = {
    "generate": (
        "Generate clean, production-ready {language} code for: {prompt}\n\n"
        "Include error handling, type hints (if applicable), and comments."
    ),
    "explain": (
        "Explain this {language} code clearly, covering: purpose, inputs/outputs, "
        "algorithm, edge cases, and potential improvements:\n\n"
        "```{language}\n{code}\n```"
    ),
    "debug": (
        "Debug this {language} code and fix the error:\n\n"
        "```{language}\n{code}\n```\n\nError: {error}"
    ),
    "refactor": (
        "Refactor this {language} code for better readability, performance, "
        "and maintainability:\n\n```{language}\n{code}\n```"
    ),
    "test": (
        "Generate comprehensive unit tests for this {language} code. "
        "Include edge cases, happy paths, and error cases:\n\n"
        "```{language}\n{code}\n```"
    ),
    "analyze": (
        "Analyze this {language} code for: bugs, security issues, performance, "
        "code smells, and improvements:\n\n```{language}\n{code}\n```"
    ),
}


# Module-level template cache — loaded once, reused for all subsequent calls
_template_cache: dict = {}


def _load_template(name: str) -> str:
    if name in _template_cache:
        return _template_cache[name]
    path = PROMPTS_DIR / f"{name}.txt"
    if path.exists():
        content = path.read_text(encoding="utf-8")
        _template_cache[name] = content
        return content
    logger.warning("prompt_builder.template_missing", extra={"name": name})
    _template_cache[name] = ""
    return ""


class PromptBuilder:
    async def build_system_prompt(self, query: str = "") -> str:
        """Build the main system prompt with available tools and workspace context injected."""
        base = _load_template("system_prompt")
        tool_section = await self._build_tool_section()
        workspace_context = self._get_workspace_context(query)
        
        # Use .replace() instead of .format() to avoid Python treating
        # JSON braces like {"name": ...} inside the template as format fields.
        rendered = base.replace("{tools}", tool_section)
        rendered = rendered.replace("{workspace_context}", workspace_context)
        
        # Injection: Pinned Context (Fundamental files)
        pinned = self._get_pinned_context()
        rendered = rendered.replace("{pinned_context}", pinned) if "{pinned_context}" in rendered else rendered + pinned
        
        # Injection: Background Indexing Status
        indexing_context = self._get_indexing_context()
        if indexing_context:
            rendered = rendered + "\n\n" + indexing_context
            
        return rendered

    def _get_pinned_context(self) -> str:
        """Always include core file outlines to prevent 'forgetting' base architecture."""
        root = Path(config.ALLOWED_BASE_PATH)
        critical_files = ["config.py", "routes.py", "app.py"]
        
        lines = ["\n\n### PINNED ARCHITECTURAL CONTEXT (Core Files Outline)\n"]
        for fname in critical_files:
            fpath = root / fname
            if fpath.exists():
                try:
                    # We only take the first 15 lines (imports + constants) as a 'skeleton'
                    content = fpath.read_text(encoding="utf-8").splitlines()[:15]
                    lines.append(f"• {fname} (Header):\n```python\n" + "\n".join(content) + "\n...\n```")
                except: pass
        return "\n".join(lines)

    def _get_indexing_context(self) -> str:
        """Informs the LLM if background indexing is active or completed for certain paths."""
        from services.embedding_service import embedding_service
        status_map = embedding_service.get_status()
        
        active_paths = [path for path, stats in status_map.items() if stats.get("status") == "indexing"]
        completed_paths = [path for path, stats in status_map.items() if stats.get("status") == "completed"]
        
        if not active_paths and not completed_paths:
            return ""
            
        ctx = "### 📂 EMBEDDING STATUS\n"
        if active_paths:
            ctx += "⚠️ **BACKGROUND INDEXING IN PROGRESS**:\n"
            for path in active_paths:
                stats = status_map[path]
                ctx += f"- {path}: {stats['indexed']}/{stats['total_files']} files. Current: `{stats['current_file']}`\n"
            ctx += "\nNOTE: Semantic search results for these paths may be incomplete. Use manual tools if needed.\n\n"
        
        if completed_paths:
            ctx += "✅ **INDEXED PROJECTS (Ready for RAG)**:\n"
            for path in completed_paths:
                ctx += f"- {path} (Fully indexed and available via semantic search)\n"
        
        return ctx

    def _get_workspace_context(self, query: str = "") -> str:
        """Get a sample of the workspace, prioritizing files relevant to the query."""
        base_path = Path(config.ALLOWED_BASE_PATH)
        if not base_path.exists():
            return "Workspace root is empty."
        
        # Extract keywords for smart prioritization
        keywords = set(re.findall(r'\w+', query.lower())) if query else set()
        
        lines = []
        try:
            all_items = []
            for item in base_path.iterdir():
                if item.name.startswith('.') or item.name in config.GLOBAL_EXCLUDE_DIRS:
                    continue
                all_items.append(item)
            
            # Sort: Prioritize files that match keywords, then direct matches, then alphabetical
            def priority_score(item):
                score = 0
                name_lower = item.name.lower()
                if any(kw in name_lower for kw in keywords):
                    score -= 10
                if item.is_dir():
                    score += 1 # Files slightly higher than dirs for immediate context
                return score

            sorted_items = sorted(all_items, key=lambda x: (priority_score(x), x.name))

            for item in sorted_items[:20]: # limit top level
                if item.is_file():
                    size = f"{round(item.stat().st_size / 1024, 1)} KB"
                    lines.append(f"- {item.name} ({size})")
                elif item.is_dir():
                    lines.append(f"- {item.name}/")
                    try:
                        # Prioritize repo/ folder contents
                        max_subs = 10 if item.name == config.REPO_DIR else 5
                        sub_items = sorted(item.iterdir(), key=lambda x: (priority_score(x), x.name))
                        for sub in sub_items[:max_subs]:
                            if sub.name.startswith('.'): continue
                            symbol = "📄" if sub.is_file() else "📁"
                            lines.append(f"  {symbol} {sub.name}")
                        if len(sub_items) > max_subs:
                            lines.append(f"  ... ({len(sub_items) - max_subs} more items)")
                    except: pass

        except Exception as e:
            return f"Error reading workspace: {e}"

        ctx = "WORKSPACE TOPOGRAPHY (Smart Sample):\n" + "\n".join(lines[:60])
        return ctx

    async def _build_tool_section(self) -> str:
        tool_template = _load_template("tool_prompt")
        
        # Build tool list from the Multi-Server Host Manager
        # This includes BOTH internal tools and detected external tools.
        tools = await mcp_host.get_combined_tools()
        
        lines = ["## Available MCP Tools (Internal & External)\n"]
        for t in tools:
            source = t.get("source", "unknown")
            lines.append(f"  • **{t['name']}** [{source}] — {t['description']}")
            params_str = json.dumps(t.get("parameters", {}), separators=(',', ':')) # ultra-compact
            lines.append(f"    Parameters: {params_str}")
            
        tool_list = "\n".join(lines) if lines else "No tools registered."
        return tool_template.replace("{tool_list}", tool_list)

    def build_task_prompt(
        self,
        task: str,
        *,
        language: str = "python",
        code: str = "",
        prompt: str = "",
        error: str = "",
    ) -> str:
        template = TASK_PROMPTS.get(task, TASK_PROMPTS["analyze"])
        return template.format(language=language, code=code, prompt=prompt, error=error)

    def build_repo_analysis_prompt(self, stats: dict) -> str:
        template = _load_template("repo_analysis")
        top_files = json.dumps(stats.get("largest_files", [])[:5], indent=2)
        languages = json.dumps(stats.get("languages", {}), indent=2)
        dependencies = json.dumps(stats.get("dependencies", {}), indent=2)
        summary = {
            "file_count": stats.get("file_count", 0),
            "total_lines": stats.get("total_lines", 0),
        }
        return template.format(
            stats=json.dumps(summary, indent=2),
            top_files=top_files,
            languages=languages,
            dependencies=dependencies,
        )

    def build_user_message(
        self,
        message: str,
        context_code: Optional[str] = None,
        language: Optional[str] = None,
        repo_context: Optional[str] = None,
    ) -> str:
        parts = [message]
        if repo_context:
            parts.append(f"\n\n[Repo Context]\n{repo_context}")
        if context_code:
            lang = language or "code"
            parts.append(f"\n\n[Code Context]\n```{lang}\n{context_code}\n```")
        return "".join(parts)

    def build_task_decomposition_prompt(self, user_goal: str) -> str:
        """Adds a strict decomposition mandate for complex user goals."""
        return (
            f"\n\n### TASK DECOMPOSITION MANDATE\n"
            f"GOAL: '{user_goal}'\n"
            "This is a complex request. You MUST:\n"
            "1. Analyze exactly what is needed (libraries, files, architecture).\n"
            "2. DECOMPOSE the work into logical PHASES (e.g., Phase 1: Holistic Exploration, Phase 2: Core Logic Implementation, etc.).\n"
            "3. State this Phase-based plan to the user in the chat.\n"
            "4. IMMEDIATELY execute tools for the first phase. Use `scan_directory` or `get_repo_map` for holistic exploration to avoid turn exhaustion.\n"
            "5. **STRICT CHECKPOINT**: You MUST provide an interactive update every 10 turns. Do NOT continue a research loop beyond 10 actions without user validation."
        )


# Singleton instance
prompt_builder = PromptBuilder()
