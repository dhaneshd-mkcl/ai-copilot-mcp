"""
git_tools.py — Production-grade Git & GitHub tools with strong validation and resilience.
"""

import logging
import os
import shutil
import httpx
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from mcp_registry.registry import registry
from mcp_registry.tools.terminal_tools import run_command
from copilot.utils import safe_path
from config import config

logger = logging.getLogger(__name__)


# =========================
# Response Models
# =========================

class GitResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    output: Optional[str] = None
    stderr: Optional[str] = None
    commit_exists: Optional[bool] = None
    url: Optional[str] = None
    code: Optional[int] = None


# =========================
# Helpers
# =========================

async def exec_git(command: str, cwd: str) -> tuple[int, str, str]:
    """Run git command with logging + validation"""
    result = await run_command(command=command, cwd=cwd)

    stdout = result.get("stdout", "").strip()
    stderr = result.get("stderr", "").strip()
    code = result.get("returncode", -1)

    logger.info(f"[GIT CMD] {command} (RET: {code})")
    if stdout:
        logger.debug(f"[STDOUT] {stdout[:200]}...")
    if stderr:
        logger.warning(f"[STDERR] {stderr[:200]}...")

    return code, stdout, stderr


async def _ensure_main_branch(workspace: str):
    """Safely ensures the current branch is 'main' for GitHub compatibility."""
    code, out, err = await exec_git("git rev-parse --abbrev-ref HEAD", workspace)
    curr = out.strip()
    if curr == "master":
        logger.info("Normalizing branch: master -> main")
        await exec_git("git branch -M main", workspace)
    elif not curr or code != 0:
        # Initializing repo if no head or command failed
        await exec_git("git init", workspace)
        await exec_git("git branch -M main", workspace)


def ensure_git_installed():
    if not shutil.which("git"):
        raise RuntimeError("Git is not installed on system")


# =========================
# Git Status
# =========================

@registry.register(
    name="git_get_status",
    description="Get detailed git status",
    parameters={"cwd": {"type": "string", "default": "."}},
    category="safe",
)
async def git_get_status(cwd: str = "."):
    try:
        workspace = str(safe_path(cwd))
        code, out, err = await exec_git("git status -sb", workspace)

        return GitResponse(
            success=(code == 0),
            output=out,
            stderr=err if code != 0 else None,
            code=code
        ).model_dump(exclude_none=True)

    except Exception as e:
        return GitResponse(success=False, stderr=str(e)).model_dump()


# =========================
# Commit Code
# =========================

@registry.register(
    name="commit_code_v2",
    description="Stage and commit all changes with verification.",
    parameters={
        "message": {"type": "string", "description": "Commit message"},
        "cwd": {"type": "string", "default": "."},
    },
    category="dangerous",
)
async def commit_code_v2(message: str, cwd: str = "."):
    try:
        ensure_git_installed()
        workspace = str(safe_path(cwd))

        # 1. Identity fallback check
        name_check_code, name_out, _ = await exec_git("git config user.name", workspace)
        if not name_out.strip():
            logger.info("Setting fallback git user.name")
            await exec_git('git config user.name "AI Copilot"', workspace)
        
        # 2. Normalize branch
        await _ensure_main_branch(workspace)

        # 3. Stage all files
        await exec_git("git add -A", workspace)

        # 4. Commit
        code, out, err = await exec_git(f'git commit -m "{message}"', workspace)

        if code != 0 and "nothing to commit" in err.lower():
            # Check if commit exists even if "nothing to commit" now
            l_code, l_out, _ = await exec_git("git log -1 --oneline", workspace)
            return GitResponse(
                success=True,
                message="Working tree clean (nothing to commit).",
                commit_exists=(l_code == 0 and bool(l_out)),
                code=code
            ).model_dump()

        # 5. VERIFY commit actually exists
        l_code, l_out, _ = await exec_git("git log -1 --oneline", workspace)

        if l_code != 0 or not l_out.strip():
            return GitResponse(
                success=False,
                message="Commit failed or no commit history found.",
                stderr=err,
                code=l_code
            ).model_dump()

        return GitResponse(
            success=True,
            message="Commit created/verified successfully",
            output=l_out,
            commit_exists=True,
            code=code
        ).model_dump()

    except Exception as e:
        return GitResponse(success=False, stderr=str(e)).model_dump()


# =========================
# Git Pull
# =========================

@registry.register(
    name="git_pull",
    description="Pull changes from remote with authentication support.",
    parameters={
        "remote": {"type": "string", "default": "origin"},
        "branch": {"type": "string", "default": "main"},
        "cwd": {"type": "string", "default": "."},
        "token": {"type": "string", "default": ""},
    },
    category="dangerous",
)
async def git_pull(remote: str = "origin", branch: str = "main", cwd: str = ".", token: str = ""):
    try:
        workspace = str(safe_path(cwd))
        
        target_remote = remote
        if token:
            code, out, err = await exec_git(f"git remote get-url {remote}", workspace)
            if code == 0:
                url = out.strip()
                if "github.com" in url:
                    target_remote = url.replace("https://", f"https://{token}@")

        cmd = f"git pull {target_remote} {branch}"
        code, out, err = await exec_git(cmd, workspace)

        return GitResponse(
            success=(code == 0),
            output=out,
            stderr=err,
            code=code
        ).model_dump()

    except Exception as e:
        return GitResponse(success=False, stderr=str(e)).model_dump()


# =========================
# Git Push
# =========================

@registry.register(
    name="git_push",
    description="Push changes to GitHub with branch auto-normalization.",
    parameters={
        "remote": {"type": "string", "default": "origin"},
        "branch": {"type": "string", "default": "main"},
        "cwd": {"type": "string", "default": "."},
        "token": {"type": "string", "default": ""},
        "force": {"type": "boolean", "default": False},
    },
    category="dangerous",
)
async def git_push(remote: str = "origin", branch: str = "main", cwd: str = ".", token: str = "", force: bool = False):
    try:
        workspace = str(safe_path(cwd))
        
        # 1. Normalize local branch to match GitHub target if needed
        await _ensure_main_branch(workspace)
        
        target_remote = remote
        if token:
            code, out, err = await exec_git(f"git remote get-url {remote}", workspace)
            if code == 0:
                url = out.strip()
                if "github.com" in url:
                    target_remote = url.replace("https://", f"https://{token}@")

        f_flag = "--force" if force else ""
        # If branch is specified, use origin <branch>
        target_branch = branch if branch else "main"
        cmd = f"git push -u {target_remote} {target_branch} {f_flag}".strip()
        
        code, out, err = await exec_git(cmd, workspace)

        if code != 0:
            return GitResponse(success=False, message="Push failed", stderr=err, code=code).model_dump()

        return GitResponse(
            success=True,
            message="Push successful",
            output=out,
            code=code
        ).model_dump()

    except Exception as e:
        return GitResponse(success=False, stderr=str(e)).model_dump()


# =========================
# GitHub Tools
# =========================

@registry.register(
    name="github_create_repo",
    description="Create a new repository on GitHub.",
    parameters={
        "name": {"type": "string"},
        "token": {"type": "string"},
        "private": {"type": "boolean", "default": False},
    },
    category="dangerous",
)
async def github_create_repo(name: str, token: str, private: bool = False):
    try:
        url = "https://api.github.com/user/repos"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Antigravity-AI-Copilot"
        }
        data = {"name": name, "private": private}

        async with httpx.AsyncClient() as client:
            res = await client.post(url, headers=headers, json=data, timeout=10.0)

        if res.status_code == 201:
            repo = res.json()
            return {
                "success": True,
                "url": repo["html_url"],
                "clone_url": repo["clone_url"]
            }
        elif res.status_code == 422 and "already exists" in res.text:
            # Handle already exists gracefully
            async with httpx.AsyncClient() as c2:
                u_res = await c2.get("https://api.github.com/user", headers=headers)
                if u_res.status_code == 200:
                    login = u_res.json()["login"]
                    return {
                        "success": True,
                        "status": "already_exists",
                        "url": f"https://github.com/{login}/{name}",
                        "clone_url": f"https://github.com/{login}/{name}.git"
                    }
        
        return {"success": False, "error": res.text, "code": res.status_code}

    except Exception as e:
        return {"success": False, "error": str(e)}


@registry.register(
    name="github_setup_repository",
    description="Full pipeline: Create, Link, Commit, and Push.",
    parameters={
        "name": {"type": "string"},
        "token": {"type": "string"},
        "cwd": {"type": "string", "default": "."},
    },
    category="dangerous",
)
async def github_setup_repository(name: str, token: str, cwd: str = "."):
    try:
        workspace = str(safe_path(cwd))
        logger.info(f"tool.github_setup_repository | Resolved workspace: {workspace}")

        # 1. Create or Find Repo
        repo = await github_create_repo(name, token)
        if not repo.get("success"):
            return repo

        # 2. Initial Setup & Commit
        commit = await commit_code_v2("Initial commit via AI Copilot", cwd)
        if not commit.get("success"):
            return {"success": False, "error": "Commit failed", "details": commit}

        # 3. Add Remote with Token
        authed_url = repo["clone_url"].replace("https://", f"https://{token}@")
        
        # Check if remote exists
        r_code, r_out, _ = await exec_git("git remote get-url origin", workspace)
        if r_code == 0:
            await exec_git(f"git remote set-url origin {authed_url}", workspace)
        else:
            await exec_git(f"git remote add origin {authed_url}", workspace)

        # 4. Push to Main
        # We use force push for setup to overwrite any dummy files (like README from GitHub creation)
        push = await git_push(branch="main", cwd=cwd, token=token, force=True)

        return {
            "success": push.get("success"),
            "url": repo.get("url"),
            "commit_verified": commit.get("commit_exists"),
            "push_details": push
        }

    except Exception as e:
        return {"success": False, "error": str(e)}

# =========================
# Misc Tools
# =========================

@registry.register(
    name="git_branch",
    description="Branch management (list, create, switch).",
    parameters={
        "action": {"type": "string", "enum": ["list", "create", "switch"]},
        "name": {"type": "string", "default": ""},
        "cwd": {"type": "string", "default": "."},
    },
    category="dangerous",
)
async def git_branch(action: str, name: str = "", cwd: str = "."):
    workspace = str(safe_path(cwd))
    cmd_map = {
        "list": "git branch -a",
        "create": f"git branch {name}",
        "switch": f"git checkout {name}"
    }
    code, out, err = await exec_git(cmd_map[action], workspace)
    return GitResponse(success=(code == 0), output=out, stderr=err, code=code).model_dump()

@registry.register(
    name="git_log",
    description="View git history.",
    parameters={
        "max_count": {"type": "integer", "default": 5},
        "cwd": {"type": "string", "default": "."},
    },
    category="safe",
)
async def git_log(max_count: int = 5, cwd: str = "."):
    workspace = str(safe_path(cwd))
    code, out, err = await exec_git(f"git log -n {max_count} --oneline", workspace)
    return GitResponse(success=(code == 0), output=out, stderr=err, code=code).model_dump()

@registry.register(
    name="set_workspace_path",
    description="Dynamically set the allowed base path for the current session.",
    parameters={
        "path": {"type": "string", "description": "The new absolute path to allow as the workspace base."}
    },
    category="dangerous"
)
async def set_workspace_path(path: str) -> dict:
    try:
        if not os.path.isabs(path):
            return {"status": "error", "error": "Path must be absolute."}
        config.ALLOWED_BASE_PATH = path
        os.makedirs(path, exist_ok=True)
        return {"status": "success", "message": f"Workspace updated to: {path}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
