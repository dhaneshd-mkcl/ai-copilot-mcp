import os
import shutil
import fnmatch
import time
import logging
from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional

from config import config
from mcp_registry.registry import registry
from copilot.utils import safe_path, get_backup_path, get_project_doc_path
from services.embedding_service import embedding_service

# --- Pydantic Output Schemas ---

class FileItem(BaseModel):
    name: str
    type: str
    size: Optional[int] = None

class ListFilesOutput(BaseModel):
    path: str
    files: List[FileItem]
    count: int
    error: Optional[str] = None

class ReadFileOutput(BaseModel):
    path: str
    content: str
    size_bytes: int
    truncated: bool = False
    error: Optional[str] = None

class WriteFileOutput(BaseModel):
    path: str
    status: str
    size: int
    backup: Optional[str] = None
    diff: Optional[str] = None
    error: Optional[str] = None

class GenericStatusOutput(BaseModel):
    path: Optional[str] = None
    status: str
    error: Optional[str] = None
    backup: Optional[str] = None

class SearchResult(BaseModel):
    file: str
    line: int
    match: str

class SearchOutput(BaseModel):
    query: str
    results: List[SearchResult]
    count: Optional[int] = None
    truncated: bool = False
    error: Optional[str] = None

class ScanNode(BaseModel):
    name: str
    type: str
    size: Optional[int] = None
    children: Optional[List['ScanNode']] = None

class OutlineItem(BaseModel):
    line: int
    kind: str
    text: str

class OutlineOutput(BaseModel):
    path: str
    outline: List[OutlineItem]
    count: int
    error: Optional[str] = None

class ReplaceOutput(BaseModel):
    query: str
    replacement: str
    modified_count: int
    files: List[str]
    error: Optional[str] = None

class ReadDirectoryOutput(BaseModel):
    path: str
    files_processed: int
    content: str
    total_chars: int
    error: Optional[str] = None

class SemanticSearchOutput(BaseModel):
    query: str
    results: List[dict]
    count: int
    error: Optional[str] = None

class RepoMapOutput(BaseModel):
    path: str
    map: str
    status: str
    error: Optional[str] = None

logger = logging.getLogger(__name__)

def is_binary_file(filepath: Path) -> bool:
    """Check if a file is binary by looking for null bytes in the first 1024 bytes."""
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(1024)
            if b'\0' in chunk:
                return True
    except Exception:
        pass
    return False

@registry.register(
    name="list_files",
    description="List files in a directory within the workspace",
    parameters={
        "path": {"type": "string", "description": "Directory path relative to workspace", "default": "."},
        "pattern": {"type": "string", "description": "Glob pattern filter.", "default": "*"},
    },
    category="safe",
)
async def list_files(path: str = ".", pattern: str = "*") -> dict:
    logger.info(f"tool.list_files | START path='{path}' pattern='{pattern}'")
    target = safe_path(path)
    if not target.exists():
        return ListFilesOutput(path=str(path), files=[], count=0, error=f"Path '{path}' does not exist").model_dump(exclude_none=True)
    files = []
    for item in target.iterdir():
        if fnmatch.fnmatch(item.name, pattern):
            files.append(FileItem(
                name=item.name,
                type="dir" if item.is_dir() else "file",
                size=item.stat().st_size if item.is_file() else None,
            ))
    files.sort(key=lambda x: (x.type == "file", x.name))
    return ListFilesOutput(path=str(path), files=files, count=len(files)).model_dump(exclude_none=True)


@registry.register(
    name="read_file",
    description="Read the contents of a file in the workspace",
    parameters={
        "path": {"type": "string", "description": "File path relative to workspace"},
    },
    category="safe",
)
async def read_file(path: str) -> dict:
    logger.info(f"tool.read_file | START path='{path}'")
    target = safe_path(path)
    max_bytes = config.MAX_FILE_SIZE_MB * 1024 * 1024
    if not target.is_file():
        return ReadFileOutput(path=str(path), content="", size_bytes=0, error=f"Path '{path}' is not a file").model_dump(exclude_none=True)
        
    size = target.stat().st_size
    if size > max_bytes:
        return ReadFileOutput(path=str(path), content="", size_bytes=size, error=f"File exceeds {config.MAX_FILE_SIZE_MB}MB").model_dump(exclude_none=True)
        
    if is_binary_file(target):
        return ReadFileOutput(path=str(path), content="", size_bytes=size, error=f"File '{path}' appears to be a binary file").model_dump(exclude_none=True)

    try:
        content = target.read_text(encoding="utf-8")
        return ReadFileOutput(path=str(path), content=content, size_bytes=size).model_dump(exclude_none=True)
    except Exception as e:
        return ReadFileOutput(path=str(path), content="", size_bytes=size, error=str(e)).model_dump(exclude_none=True)


@registry.register(
    name="write_file",
    description="Write content to a file in the workspace. Creates a .bak copy if the file already exists.",
    parameters={
        "path": {"type": "string", "description": "File path relative to workspace"},
        "content": {"type": "string", "description": "Content to write"},
    },
    category="dangerous",
)
async def write_file(path: str, content: str) -> dict:
    logger.info(f"tool.write_file | START path='{path}' content_len={len(content)}")
    
    # Auto-Route Markdown files to project documentation
    if path.endswith(".md") and "/" not in path and "\\" not in path:
        target = get_project_doc_path(path)
        path = str(target.relative_to(Path(config.ALLOWED_BASE_PATH).resolve()))
    else:
        target = safe_path(path)
        
    target.parent.mkdir(parents=True, exist_ok=True)
    
    backup_name = None
    diff = None
    if target.exists() and target.is_file():
        # Calculate diff before update
        try:
            old_content = target.read_text(encoding="utf-8", errors="replace")
            import difflib
            diff_lines = difflib.unified_diff(
                old_content.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}"
            )
            diff = "".join(diff_lines)
        except Exception as e:
            logger.warning(f"Failed to generate diff for {path}: {e}")

        # Create centralized backup before overwrite
        try:
            backup_path = get_backup_path(target)
            import shutil
            shutil.copy2(target, backup_path)
            backup_name = str(backup_path) # Full path for traceability
            logger.info(f"backup_created: {backup_path}")
        except Exception as e:
            logger.warning(f"Failed to create backup for {path}: {e}")

    target.write_text(content, encoding="utf-8")
    
    return WriteFileOutput(
        path=str(path),
        size=len(content),
        status="written",
        backup=backup_name,
        diff=diff
    ).model_dump(exclude_none=True)


@registry.register(
    name="search_repository",
    description="Search for text patterns in repository files (Optimized).",
    parameters={
        "query": {"type": "string", "description": "Text to search for"},
        "path": {"type": "string", "description": "Directory to search in", "default": "."},
        "file_types": {"type": "array", "items": {"type": "string"}, "description": "File extensions to include", "default": []},
    },
    category="safe",
)
async def search_repository(query: str, path: str = ".", file_types: list = None) -> dict:
    logger.info(f"tool.search_repository | START query='{query}' path='{path}'")
    target = safe_path(path)
    if not target.exists():
        return {"error": f"Path '{path}' not found"}

    import subprocess
    import platform
    import asyncio

    results = []
    
    # Optimization 1: Try ripgrep (rg) - blazing fast, cross-platform
    try:
        rg_cmd = ["rg", "-n", "-i", query, str(target)]
        if file_types:
            for ext in file_types:
                clean_ext = ext.lstrip('.')
                rg_cmd.extend(["-g", f"*.{clean_ext}"])
        
        proc = await asyncio.create_subprocess_exec(
            *rg_cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        
        if stdout:
            for line in stdout.decode('utf-8', errors='ignore').splitlines():
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    try:
                        rel_path = str(Path(parts[0]).relative_to(target))
                        results.append(SearchResult(
                            file=rel_path if rel_path != "." else parts[0],
                            line=int(parts[1]),
                            match=parts[2].strip()
                        ))
                    except ValueError:
                        pass
                if len(results) >= 100:
                    return SearchOutput(query=query, results=results, truncated=True).model_dump(exclude_none=True)
        
        if proc.returncode in (0, 1): # 0 = found, 1 = no match (valid rg behavior)
            return SearchOutput(query=query, results=results, count=len(results)).model_dump(exclude_none=True)
            
    except Exception as e:
        logger.debug(f"search_repository: rg (ripgrep) not available or failed: {e}")

    # Optimization 2: Try findstr on Windows
    if not results and platform.system() == "Windows":
        try:
            ext_pattern = "*"
            if file_types:
                ext_pattern = " ".join([f"*{ext if ext.startswith('.') else '.'+ext}" for ext in file_types])
            
            cmd = f'findstr /S /N /I /C:"{query}" {ext_pattern}'
            proc = await asyncio.create_subprocess_shell(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                cwd=target
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            
            if stdout:
                import re
                # Pattern to handle: [optional drive]:\path\file.ext:lineno:content
                # findstr often outputs relative paths if run in the target dir
                for line in stdout.decode('utf-8', errors='ignore').splitlines():
                    # Look for the LAST two colons that follow a number to find lineno
                    # Better: regex that looks for path:number:
                    match = re.match(r"^(.*?):(\d+):(.*)$", line)
                    if match:
                        results.append(SearchResult(
                            file=match.group(1),
                            line=int(match.group(2)),
                            match=match.group(3).strip()
                        ))
                    if len(results) >= 100:
                        return SearchOutput(query=query, results=results, truncated=True).model_dump(exclude_none=True)
        except Exception as e:
            logger.warning(f"findstr_optimization_failed error={e}")

    # Optimization 3: Non-blocking Python fallback
    if not results:
        extensions = set(file_types or [])
        
        def _sync_search():
            sync_results = []
            for root, dirs, files in os.walk(target):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in config.GLOBAL_EXCLUDE_DIRS]
                for fname in files:
                    if extensions and not any(fname.endswith(ext) for ext in extensions):
                        continue
                    fpath = Path(root) / fname
                    if is_binary_file(fpath):
                        continue
                    try:
                        content = fpath.read_text(encoding="utf-8")
                        for i, line in enumerate(content.splitlines(), 1):
                            if query.lower() in line.lower():
                                rel = str(fpath.relative_to(target))
                                sync_results.append(SearchResult(file=rel, line=i, match=line.strip()))
                                if len(sync_results) >= 100:
                                    return sync_results, True
                    except Exception:
                        continue
            return sync_results, False

        sync_results, truncated = await asyncio.to_thread(_sync_search)
        results.extend(sync_results)
        if truncated:
            return SearchOutput(query=query, results=results, truncated=True).model_dump(exclude_none=True)

    return SearchOutput(query=query, results=results, count=len(results)).model_dump(exclude_none=True)


@registry.register(
    name="scan_directory",
    description="Recursively scan directory structure",
    parameters={
        "path": {"type": "string", "description": "Directory path", "default": "."},
        "max_depth": {"type": "integer", "description": "Maximum scan depth", "default": 3},
    },
    category="safe",
)
async def scan_directory(path: str = ".", max_depth: int = 3) -> dict:
    logger.info(f"tool.scan_directory | START path='{path}' depth={max_depth}")
    target = safe_path(path)
    if not target.exists() or not target.is_dir():
        return {"error": f"Path '{path}' not found or is not a directory"}

    def _scan(p: Path, depth: int) -> ScanNode:
        node = ScanNode(name=p.name, type="dir" if p.is_dir() else "file")
        if p.is_dir():
            if depth < max_depth:
                node.children = []
                try:
                    for child in sorted(p.iterdir()):
                        if child.name.startswith('.') or child.name in config.GLOBAL_EXCLUDE_DIRS:
                            continue
                        node.children.append(_scan(child, depth + 1))
                except PermissionError:
                    pass
        else:
            node.size = p.stat().st_size
        return node

    return _scan(target, 0).model_dump(exclude_none=True)
@registry.register(
    name="outline_file",
    description="Get a high-level structural outline of a code file (classes, methods, functions).",
    parameters={
        "path": {"type": "string", "description": "File path relative to workspace"},
    },
    category="safe",
    timeout=20,
)
async def outline_file(path: str) -> dict:
    logger.info(f"tool.outline_file | START path='{path}'")
    target = safe_path(path)
    if not target.is_file():
        return OutlineOutput(path=str(path), outline=[], count=0, error=f"File '{path}' not found").model_dump(exclude_none=True)
    
    if is_binary_file(target):
        return OutlineOutput(path=str(path), outline=[], count=0, error=f"File '{path}' appears to be a binary file").model_dump(exclude_none=True)
    
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return OutlineOutput(path=str(path), outline=[], count=0, error=f"File '{path}' is not valid UTF-8").model_dump(exclude_none=True)
    lines = content.splitlines()
    
    outline = []
    # Simple regex-based structure detection
    import re
    # Patterns for Python (class/def), JS/TS (class/function/const func/interface), etc.
    patterns = [
        (r'^\s*(class\s+\w+)', 'class'),
        (r'^\s*(async\s+)?def\s+(\w+)', 'function'),
        (r'^\s*(async\s+)?function\s+(\w+)', 'function'),
        (r'^\s*(export\s+)?(const|let|var)\s+(\w+)\s*=\s*(async\s*)?\([^)]*\)\s*=>', 'arrow_function'),
        (r'^\s*(export\s+)?interface\s+(\w+)', 'interface'),
        (r'^\s*(export\s+)?type\s+(\w+)', 'type'),
    ]
    
    for i, line in enumerate(lines, 1):
        for pattern, kind in patterns:
            match = re.search(pattern, line)
            if match:
                # Get the relevant part of the match (e.g. "class Foo" or "def bar")
                display = match.group(0).strip()
                outline.append(OutlineItem(line=i, kind=kind, text=display))
                break
                
    return OutlineOutput(path=str(path), outline=outline, count=len(outline)).model_dump(exclude_none=True)


@registry.register(
    name="delete_item",
    description="Delete a file or directory from the workspace.",
    parameters={
        "path": {"type": "string", "description": "Path relative to workspace"},
        "recursive": {"type": "boolean", "description": "Whether to delete non-empty directories", "default": False},
    },
    category="dangerous",
)
async def delete_item(path: str, recursive: bool = False) -> dict:
    logger.info(f"tool.delete_item | START path='{path}' recursive={recursive}")
    target = safe_path(path)
    if not target.exists():
        return {"error": f"Item '{path}' not found"}
    
    try:
        if target.is_dir():
            if recursive:
                shutil.rmtree(target)
            else:
                try:
                    target.rmdir()
                except OSError:
                    return GenericStatusOutput(status="error", error=f"Directory '{path}' is not empty. Use recursive=True to delete it.").model_dump(exclude_none=True)
        else:
            target.unlink()
        return GenericStatusOutput(path=str(path), status="deleted").model_dump(exclude_none=True)
    except Exception as e:
        return GenericStatusOutput(status="error", error=str(e)).model_dump(exclude_none=True)


@registry.register(
    name="move_item",
    description="Move or rename a file or directory within the workspace.",
    parameters={
        "source": {"type": "string", "description": "Original path relative to workspace"},
        "destination": {"type": "string", "description": "New path relative to workspace"},
    },
    category="dangerous",
)
async def move_item(source: str, destination: str) -> dict:
    logger.info(f"tool.move_item | START src='{source}' dest='{destination}'")
    src = safe_path(source)
    dest = safe_path(destination)
    try:
        if not src.exists():
            return GenericStatusOutput(status="error", error=f"Source '{source}' not found").model_dump(exclude_none=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dest)
        return GenericStatusOutput(status="moved", path=str(destination)).model_dump(exclude_none=True)
    except Exception as e:
        return GenericStatusOutput(status="error", error=str(e)).model_dump(exclude_none=True)


@registry.register(
    name="create_directory",
    description="Explicitly create a new directory in the workspace.",
    parameters={
        "path": {"type": "string", "description": "Directory path relative to workspace"},
    },
    category="dangerous",
)
async def create_directory(path: str) -> dict:
    logger.info(f"tool.create_directory | START path='{path}'")
    target = safe_path(path)
    try:
        target.mkdir(parents=True, exist_ok=True)
        return GenericStatusOutput(path=str(path), status="created").model_dump(exclude_none=True)
    except Exception as e:
        return GenericStatusOutput(status="error", error=str(e)).model_dump(exclude_none=True)


@registry.register(
    name="replace_in_repository",
    description="Search and replace text in multiple files within a directory.",
    parameters={
        "query": {"type": "string", "description": "Text to search for"},
        "replacement": {"type": "string", "description": "Text to replace with"},
        "path": {"type": "string", "description": "Directory to search in", "default": "."},
        "file_types": {"type": "array", "items": {"type": "string"}, "description": "File extensions to include", "default": []},
    },
    category="dangerous",
)
async def replace_in_repository(query: str, replacement: str, path: str = ".", file_types: list = None) -> dict:
    logger.info(f"tool.replace_in_repository | START query='{query}' path='{path}'")
    target = safe_path(path)
    if not target.is_dir():
        return ReplaceOutput(query=query, replacement=replacement, modified_count=0, files=[], error=f"Path '{path}' is not a directory").model_dump(exclude_none=True)
        
    extensions = set(file_types or [])
    modified_files = []
    
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in config.GLOBAL_EXCLUDE_DIRS]
        for fname in files:
            if extensions and not any(fname.endswith(ext) for ext in extensions):
                continue
            fpath = Path(root) / fname
            if is_binary_file(fpath):
                continue
            try:
                content = fpath.read_text(encoding="utf-8")
                if query in content:
                    new_content = content.replace(query, replacement)
                    fpath.write_text(new_content, encoding="utf-8")
                    modified_files.append(str(fpath.relative_to(target)))
            except UnicodeDecodeError:
                logger.warning(f"Skipping {fpath} due to decoding error.")
                continue
            except Exception as e:
                logger.error(f"Error processing {fpath}: {e}")
                continue
                
    return ReplaceOutput(
        query=query,
        replacement=replacement,
        modified_count=len(modified_files),
        files=modified_files
    ).model_dump(exclude_none=True)


@registry.register(
    name="read_directory",
    description="Read the contents of all code files in a directory (concatenated).",
    parameters={
        "path": {"type": "string", "description": "Directory path relative to workspace", "default": "."},
        "extensions": {"type": "array", "items": {"type": "string"}, "description": "Extensions to include (e.g. ['.py', '.js'])", "default": []},
    },
    category="safe",
    timeout=60,
)
async def read_directory(path: str = ".", extensions: list = None) -> dict:
    logger.info(f"tool.read_directory | START path='{path}' ext={extensions}")
    target = safe_path(path)
    if not target.is_dir():
        return ReadDirectoryOutput(path=str(path), files_processed=0, content="", total_chars=0, error=f"Path '{path}' is not a directory").model_dump(exclude_none=True)
    
    exts = set(extensions or ['.py', '.js', '.ts', '.vue', '.html', '.css', '.json', '.sh'])
    
    # Pre-scan check
    eligible_files = [
        item for item in target.iterdir() 
        if item.is_file() and (not exts or any(item.name.endswith(e) for e in exts))
    ]
    
    if len(eligible_files) > 50:
        return ReadDirectoryOutput(
            path=str(path), 
            files_processed=0, 
            content="", 
            total_chars=0, 
            error=f"Directory '{path}' contains too many eligible files ({len(eligible_files)}). Please use 'list_files' or 'get_repo_map' first, or read files individually."
        ).model_dump(exclude_none=True)

    combined = []
    file_count = 0
    total_chars = 0
    max_chars = 50000 # Safety limit for LLM context
    
    for item in sorted(eligible_files):
        if is_binary_file(item):
            continue
        try:
            content = item.read_text(encoding="utf-8")
            if total_chars + len(content) > max_chars:
                combined.append(f"\n--- FILE: {item.name} (TRUNCATED) ---\nFile too large to concatenate.")
                continue
                
            combined.append(f"\n--- FILE: {item.name} ---\n{content}")
            file_count += 1
            total_chars += len(content)
        except Exception:
            continue
                
    return ReadDirectoryOutput(
        path=str(path),
        files_processed=file_count,
        content="\n".join(combined),
        total_chars=total_chars
    ).model_dump(exclude_none=True)


@registry.register(
    name="semantic_search",
    description="Search for relevant code snippets using semantic embedding (vector search).",
    parameters={
        "query": {"type": "string", "description": "The search query (e.g. 'how does authentication work?')"},
        "top_k": {"type": "integer", "description": "Number of results to return", "default": 5},
    },
    category="safe",
)
async def semantic_search(query: str, top_k: int = 5) -> dict:
    logger.info(f"tool.semantic_search | query='{query}'")
    results = await embedding_service.search(query, top_k=top_k)
    return SemanticSearchOutput(query=query, results=results, count=len(results)).model_dump(exclude_none=True)


@registry.register(
    name="record_finding",
    description="Save a research finding or code snippet to a persistent research note file for long-term memory.",
    parameters={
        "finding": {"type": "string", "description": "The specific finding or code snippet to record"},
        "section": {"type": "string", "description": "The section name (e.g. 'Authentication', 'Database Schema')", "default": "General Findings"},
    },
    category="safe",
)
async def record_finding(finding: str, section: str = "General Findings") -> dict:
    """Save findings to a persistent markdown file to survive context pruning."""
    logger.info(f"tool.record_finding | section='{section}'")
    notes_path = get_project_doc_path("research_notes.md")
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"\n## {section} ({ts})\n{finding}\n"
    
    if not notes_path.exists():
        notes_path.write_text("# Research Notes\nPersistent findings from research to survive context pruning.\n", encoding="utf-8")
        
    with notes_path.open("a", encoding="utf-8") as f:
        f.write(entry)
        
    return {
        "status": "success", 
        "is_finding": True,
        "section": section,
        "content": finding,
        "message": f"Finding recorded in 'docs/research_notes.md'. [MANDATORY CHECKPOINT]: You have reached a research milestone. You MUST now stop and provide a summary of your findings to the user via chat before continuing with more tool calls."
    }


@registry.register(
    name="get_repo_map",
    description="Generate a high-level tree map of the repository structure to understand the architecture without context bloat.",
    parameters={
        "path": {"type": "string", "description": "Path to the directory to map", "default": "."},
        "max_depth": {"type": "integer", "description": "Maximum depth for the tree", "default": 2},
    },
    category="safe",
)
async def get_repo_map(path: str = ".", max_depth: int = 2) -> dict:
    """Returns a condensed directory tree to give the AI context without token bloat."""
    logger.info(f"tool.get_repo_map | path='{path}' depth={max_depth}")
    target = safe_path(path)
    if not target.is_dir():
        return RepoMapOutput(path=str(path), map="", status="error", error=f"Path '{path}' is not a directory").model_dump(exclude_none=True)
        
    tree = []
    
    def walk(curr_path: Path, depth: int, prefix: str = ""):
        if depth > max_depth:
            return
        
        items = sorted(curr_path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        for i, item in enumerate(items):
            if item.name.startswith('.') or item.name in config.GLOBAL_EXCLUDE_DIRS:
                continue
                
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            tree.append(f"{prefix}{connector}{item.name}{'/' if item.is_dir() else ''}")
            
            if item.is_dir():
                new_prefix = prefix + ("    " if is_last else "│   ")
                walk(item, depth + 1, new_prefix)

    tree.append(f"{target.name}/")
    walk(target, 1)
    
    return RepoMapOutput(
        status="success",
        path=str(path),
        map="\n".join(tree)
    ).model_dump(exclude_none=True)


@registry.register(
    name="index_workspace",
    description="Index or re-index the workspace for semantic search. Use this if many files have changed.",
    parameters={},
    category="safe",
)
async def index_workspace() -> dict:
    logger.info("tool.index_workspace | START")
    result = await embedding_service.index_workspace(force=True)
    return result
