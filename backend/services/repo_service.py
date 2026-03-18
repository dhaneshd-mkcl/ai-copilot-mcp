"""
RepoService — business logic for repository operations.

Wraps the MCP tool registry and repo_analyzer to provide a clean API
consumed by route handlers.
"""

import logging
from typing import Optional

from mcp_registry.registry import registry
from services.repo_analyzer import repo_analyzer

logger = logging.getLogger(__name__)


class RepoService:
    async def list_files(self, path: str = ".") -> dict:
        logger.info("repo_service.list_files", extra={"path": path})
        return await registry.execute_tool("list_files", {"path": path})

    async def read_file(self, path: str) -> dict:
        logger.info("repo_service.read_file", extra={"path": path})
        return await registry.execute_tool("read_file", {"path": path})

    async def write_file(self, path: str, content: str) -> dict:
        logger.info("repo_service.write_file", extra={"path": path})
        return await registry.execute_tool("write_file", {"path": path, "content": content})

    async def search(
        self,
        query: str,
        path: str = ".",
        file_types: Optional[list] = None,
    ) -> dict:
        logger.info("repo_service.search", extra={"query": query, "path": path})
        return await registry.execute_tool(
            "search_repository",
            {"query": query, "path": path, "file_types": file_types or []},
        )

    async def scan(self, path: str = ".", max_depth: int = 3) -> dict:
        logger.info("repo_service.scan", extra={"path": path, "max_depth": max_depth})
        return await registry.execute_tool("scan_directory", {"path": path, "max_depth": max_depth})

    def analyze(self) -> dict:
        logger.info("repo_service.analyze")
        return repo_analyzer.analyze()


# Singleton instance
repo_service = RepoService()
