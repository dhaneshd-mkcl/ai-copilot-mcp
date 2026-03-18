import os
import re
import logging
from pathlib import Path
from collections import defaultdict
from config import config

logger = logging.getLogger(__name__)

LANGUAGE_MAP = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".vue": "Vue", ".jsx": "JSX", ".tsx": "TSX",
    ".go": "Go", ".rs": "Rust", ".java": "Java",
    ".cpp": "C++", ".c": "C", ".cs": "C#",
    ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
    ".kt": "Kotlin", ".sh": "Shell", ".yaml": "YAML",
    ".json": "JSON", ".html": "HTML", ".css": "CSS",
    ".md": "Markdown", ".sql": "SQL",
}

IGNORE_DIRS = config.GLOBAL_EXCLUDE_DIRS


class RepoAnalyzer:
    def analyze(self, sub_path: str = None) -> dict:
        logger.info("repo_analyzer.analyze", extra={"path": sub_path or "."})
        from copilot.utils import safe_path
        
        # Use sub_path if provided, otherwise default to context base path
        try:
            root = safe_path(sub_path or ".")
        except Exception as e:
            return {"error": str(e)}

        if not root.exists() or not root.is_dir():
            return {"error": f"Directory '{sub_path}' not found or is not a directory"}
        stats = {
            "languages": defaultdict(int),
            "file_count": 0,
            "total_lines": 0,
            "largest_files": [],
            "dependencies": {},
        }

        files_info = []
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for fname in files:
                fpath = Path(dirpath) / fname
                ext = fpath.suffix.lower()
                lang = LANGUAGE_MAP.get(ext)
                if lang:
                    stats["languages"][lang] += 1
                stats["file_count"] += 1
                try:
                    size = fpath.stat().st_size
                    lines = 0
                    if size < 1024 * 1024:
                        content = fpath.read_text(errors="ignore")
                        lines = content.count("\n")
                        stats["total_lines"] += lines
                    files_info.append({"path": str(fpath.relative_to(root)), "size": size, "lines": lines})
                except Exception:
                    pass

        files_info.sort(key=lambda x: x["size"], reverse=True)
        stats["largest_files"] = files_info[:10]

        # Detect dependencies
        req_file = root / "requirements.txt"
        pkg_file = root / "package.json"
        if req_file.exists():
            stats["dependencies"]["python"] = req_file.read_text().splitlines()
        if pkg_file.exists():
            import json
            try:
                pkg = json.loads(pkg_file.read_text())
                stats["dependencies"]["node"] = list(pkg.get("dependencies", {}).keys())
            except Exception:
                pass

        stats["languages"] = dict(stats["languages"])
        return stats


repo_analyzer = RepoAnalyzer()
