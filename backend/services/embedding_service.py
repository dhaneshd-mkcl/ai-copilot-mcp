import os
import json
import logging
import asyncio
import httpx
import numpy as np
from typing import List, Dict, Any, Optional
from pathlib import Path

from pgvector.asyncpg import register_vector
import asyncpg

from config import config

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self):
        self.initialized = False
        self.indexing_status: Dict[str, Any] = {} # path -> {current_file, total_files, indexed, skipped, status}
        self._client = httpx.AsyncClient(timeout=30)
        
        if config.USE_EMBEDDING and config.USE_PGVECTOR:
            # We'll initialize lazily or via a setup call since __init__ can't be async
            pass

    async def close(self):
        await self._client.aclose()

    async def _get_conn(self):
        """Get a raw asyncpg connection."""
        dsn = config.PG_URL.replace("postgresql+asyncpg", "postgresql")
        return await asyncpg.connect(dsn)

    async def _get_vector_conn(self):
        """Get a connection with pgvector support registered."""
        conn = await self._get_conn()
        try:
            await register_vector(conn)
            return conn
        except Exception:
            await conn.close()
            raise

    async def ensure_initialized(self):
        """Creates the table and extension if they don't exist."""
        if self.initialized:
            return
            
        try:
            # 1. Detect dynamic dimension from the model
            sample_emb = await self._get_embedding("ping")
            if not sample_emb:
                logger.error("embedding.pgvector | Failed to get sample embedding for dimension detection")
                return
            dim = len(sample_emb)
            logger.info(f"embedding.pgvector | Detected {dim} dimensions from {config.EMBEDDING_MODEL}")

            # 2. Use RAW connection to enable extension and create tables
            conn = await self._get_conn()
            try:
                # Enable pgvector extension
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                
                # Check if table exists and has wrong dimension
                table_info = await conn.fetchrow("""
                    SELECT atttypmod FROM pg_attribute 
                    WHERE attrelid = 'embeddings'::regclass AND attname = 'embedding'
                """)
                if table_info and table_info['atttypmod'] != dim:
                    logger.warning(f"embedding.pgvector | Dimension mismatch (db={table_info['atttypmod']}, model={dim}). Recreating table.")
                    await conn.execute("DROP TABLE IF EXISTS embeddings")

                # Create embeddings table with correct dimension
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS embeddings (
                        id SERIAL PRIMARY KEY,
                        path TEXT,
                        snippet TEXT,
                        start_char INTEGER,
                        hash TEXT,
                        embedding vector({dim})
                    )
                """)
                
                # 3. Create HNSW index for faster search
                await conn.execute("CREATE INDEX IF NOT EXISTS embeddings_vector_idx ON embeddings USING hnsw (embedding vector_l2_ops)")
                
                self.initialized = True
                logger.info(f"embedding.pgvector | Initialized PostgreSQL database with dimension {dim}")
            finally:
                await conn.close()
        except Exception as e:
            logger.error(f"embedding.pgvector | Initialization failed: {str(e)}")

    async def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Calls the MSCIT Ollama API to get embedding for a text using async httpx."""
        try:
            url = f"{config.EMBED_BASE_URL}/api/embeddings"
            payload = {
                "model": config.EMBEDDING_MODEL,
                "prompt": text
            }
            headers = {
                "Authorization": f"Bearer {config.EMBED_API_KEY}",
                "Content-Type": "application/json"
            }
            
            response = await self._client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get("embedding")
        except Exception as e:
            logger.error(f"embedding.get_api | FAILED: {str(e)}")
            return None

    def _get_file_hash(self, path: Path) -> str:
        """Calculate SHA-256 hash of a file."""
        import hashlib
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    async def index_workspace(self, force: bool = False):
        """Scans the entire workspace and indexes it."""
        return await self.index_directory(".", force=force)

    async def index_directory(self, rel_path: str, force: bool = False):
        """Scans a specific directory and indexes it in the background."""
        await self.ensure_initialized()
        
        root = Path(config.ALLOWED_BASE_PATH).resolve()
        target_dir = (root / rel_path).resolve()
        
        if not target_dir.exists() or not target_dir.is_dir():
            logger.error(f"embedding.index | Path does not exist or is not a directory: {target_dir}")
            return {"status": "error", "message": "Invalid path"}

        # Initialize status
        self.indexing_status[rel_path] = {
            "status": "indexing",
            "current_file": "",
            "indexed": 0,
            "skipped": 0,
            "total_files": 0
        }

        logger.info(f"embedding.index | STARTING scanning {target_dir}")
        conn = await self._get_vector_conn()
        
        try:
            # 1. Collect all valid files first
            files_to_process = []
            for path in target_dir.rglob("*"):
                if path.is_dir() or any(p in path.parts for p in config.GLOBAL_EXCLUDE_DIRS):
                    continue
                if path.suffix.lower() in config.GLOBAL_EXCLUDE_EXTS:
                    continue
                # Existing allow-list for code files
                if path.suffix.lower() in {".py", ".js", ".vue", ".ts", ".html", ".css", ".md", ".txt", ".json"}:
                    files_to_process.append(path)
            
            self.indexing_status[rel_path]["total_files"] = len(files_to_process)

            # Get existing file hashes
            if rel_path == ".":
                rows = await conn.fetch("SELECT DISTINCT path, hash FROM embeddings")
            else:
                rows = await conn.fetch("SELECT DISTINCT path, hash FROM embeddings WHERE path LIKE $1 || '%'", rel_path)
            
            file_hashes = {r["path"]: r["hash"] for r in rows}

            for path in files_to_process:
                rel_p_root = str(path.relative_to(root))
                self.indexing_status[rel_path]["current_file"] = rel_p_root
                logger.info(f"[INDEXING] {rel_p_root}")
                
                try:
                    current_hash = self._get_file_hash(path)
                    if not force and rel_p_root in file_hashes and file_hashes[rel_p_root] == current_hash:
                        self.indexing_status[rel_path]["skipped"] += 1
                        continue

                    content = path.read_text(encoding="utf-8", errors="replace").replace("\x00", "")
                    if not content.strip():
                        continue
                    
                    await conn.execute("DELETE FROM embeddings WHERE path = $1", rel_p_root)
                    
                    # Serialization: asyncpg connection doesn't support concurrent use
                    for i, chunk in enumerate(range(0, len(content), 1000)):
                        section = content[chunk:chunk + 1000]
                        emb = await self._get_embedding(section)
                        if emb:
                            await conn.execute("""
                                INSERT INTO embeddings (path, snippet, start_char, hash, embedding)
                                VALUES ($1, $2, $3, $4, $5)
                            """, rel_p_root, section[:500], chunk, current_hash, emb)
                    
                    self.indexing_status[rel_path]["indexed"] += 1
                except Exception as ex:
                    logger.warning(f"embedding.index | SKIPPED {path}: {str(ex)}")

            stats = self.indexing_status[rel_path]
            logger.info(f"[COMPLETED] Indexing finished for {rel_path}. Indexed: {stats['indexed']}, Skipped: {stats['skipped']}")
            self.indexing_status[rel_path]["status"] = "completed"
            return {"status": "success", "indexed": stats['indexed'], "skipped": stats['skipped']}
        finally:
            await conn.close()

    def get_status(self) -> Dict[str, Any]:
        """Returns the current indexing status."""
        return self.indexing_status

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Searches pgvector for the most relevant code snippets."""
        if not config.USE_PGVECTOR:
            return []
            
        await self.ensure_initialized()
        query_emb = await self._get_embedding(query)
        if not query_emb:
            return []
            
        conn = await self._get_vector_conn()
        try:
            # Vector <-> operator is L2 distance
            rows = await conn.fetch("""
                SELECT path, snippet, start_char, (embedding <-> $1) AS distance
                FROM embeddings
                ORDER BY distance
                LIMIT $2
            """, query_emb, top_k)
            
            results = []
            for r in rows:
                results.append({
                    "path": r["path"],
                    "snippet": r["snippet"],
                    "start_char": r["start_char"],
                    "score": float(r["distance"])
                })
            return results
        finally:
            await conn.close()

# Singleton instance
embedding_service = EmbeddingService()
