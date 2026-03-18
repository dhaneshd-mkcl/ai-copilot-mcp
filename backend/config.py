import os
import logging
from dataclasses import dataclass, field
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env - try local first, then parent if needed
if os.path.exists(".env"):
    load_dotenv(".env")
elif os.path.exists("../.env"):
    load_dotenv("../.env")
else:
    # Fallback to default behavior
    load_dotenv()


@dataclass
class Config:
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    LLM_BACKEND: str = os.getenv("LLM_BACKEND", "ollama")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://10.1.60.120:11434")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen3-coder:latest")
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "300"))
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "3"))
    # Vision Model Config (Qwen3-VL)
    VISION_MODEL: str = os.getenv("VISION_MODEL", "qwen3-vl:32b")
    VISION_BASE_URL: str = os.getenv("VISION_BASE_URL", "https://chatops.mkcl.org/ollama")
    VISION_API_KEY: str = os.getenv("VISION_API_KEY", "")
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    FIRECRAWL_API_KEY: str = os.getenv("FIRECRAWL_API_KEY", "")

    # Dynamic Path Resolution
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    ALLOWED_BASE_PATH: str = os.getenv("ALLOWED_BASE_PATH", BASE_DIR)
    VECTOR_DB_PATH: str = os.getenv("VECTOR_DB_PATH", os.path.join(BASE_DIR, "backend", "vector_db"))
    
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "10"))

    # Workspace Subfolders
    REPO_DIR: str = "repo"
    BACKUP_DIR: str = "backups"
    UPLOAD_DIR: str = "uploads"
    DOCS_DIR: str = "docs"

    # Embedding Config (Ollama Remote)
    USE_EMBEDDING: bool = os.getenv("USE_EMBEDDING", "true").lower() == "true"
    EMBED_BASE_URL: str = os.getenv("EMBED_BASE_URL", "https://mscit.mkcl.ai/ollama")
    EMBED_API_KEY: str = os.getenv("EMBED_API_KEY", "")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text:v1.5")
    
    # Database Config (Docker)
    USE_REDIS: bool = os.getenv("USE_REDIS", "true").lower() == "true"
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    USE_PGVECTOR: bool = os.getenv("USE_PGVECTOR", "true").lower() == "true"
    PG_URL: str = os.getenv("PG_URL", "postgresql://postgres:postgres@localhost:5432/ai_copilot")

    # Logic & Persistence Limits
    MAX_TURNS: int = 50  
    MAX_HISTORY: int = int(os.getenv("MAX_HISTORY", "100"))
    MAX_CONTEXT_CHARS: int = int(os.getenv("MAX_CONTEXT_CHARS", "80000")) # 160k is required for complex tool-rich projects
    SESSION_TTL: int = int(os.getenv("SESSION_TTL", "3600"))

    # Security: Protected Files
    SENSITIVE_FILES: set = field(default_factory=lambda: {".env", "config.py", "app.py", "routes.py"})
    
    # Exclusion patterns (dirs and file extensions)
    GLOBAL_EXCLUDE_DIRS: set = field(default_factory=lambda: {
        ".git", ".venv", "venv", "node_modules", "__pycache__", 
        "dist", "build", ".next", ".gemini", ".agents"
    })
    GLOBAL_EXCLUDE_EXTS: set = field(default_factory=lambda: {
        ".exe", ".bin", ".pyc", ".pyo", ".so", ".dll", ".dylib", ".o", ".obj"
    })

    # Remote MCP Servers: List of dicts [{"name": "brave", "type": "sse", "url": "..."}]
    REMOTE_MCP_SERVERS: list = field(default_factory=list)

    CORS_ORIGINS: list = None

    def __post_init__(self):
        # Load Remote MCP Servers from env (JSON string)
        import json
        remote_servers_env = os.getenv("REMOTE_MCP_SERVERS")
        if remote_servers_env:
            try:
                self.REMOTE_MCP_SERVERS = json.loads(remote_servers_env)
            except json.JSONDecodeError:
                logger.error("config.remote_mcp_servers | Failed to parse JSON from REMOTE_MCP_SERVERS")
        
        # Strict CORS for production
        env_origins = os.getenv("CORS_ORIGINS")
        if env_origins:
            self.CORS_ORIGINS = [o.strip() for o in env_origins.split(",")]
        else:
            self.CORS_ORIGINS = [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
            ]
        
        # Security: Ensure sensitive URLs are provided via .env in non-debug
        if not self.DEBUG:
            if "10.1." in self.LLM_BASE_URL or "localhost" in self.LLM_BASE_URL:
                logger.warning("PROD_HARDENING | LLM_BASE_URL points to internal/local network in production mode.")

        # Security: Check for required API keys
        if not self.VISION_API_KEY:
            logger.warning("VISION_API_KEY is not set in environment. Vision features may fail if required by the backend.")
        if not self.TAVILY_API_KEY:
            logger.warning("TAVILY_API_KEY is not set in environment. Web search capabilities won't be available.")
        if self.USE_EMBEDDING and not self.EMBED_API_KEY:
            logger.error("EMBED_API_KEY is not set, but USE_EMBEDDING is true. Embeddings may fail.")

    @property
    def ollama_chat_url(self) -> str:
        return f"{self.LLM_BASE_URL}/api/chat"

    @property
    def ollama_openai_url(self) -> str:
        return f"{self.LLM_BASE_URL}/v1/chat/completions"


config = Config()
