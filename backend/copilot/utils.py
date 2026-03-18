import logging
import datetime
from pathlib import Path
from config import config

logger = logging.getLogger(__name__)

def safe_path(path: str) -> Path:
    """
    Ensures that a given relative path stays within the ALLOWED_BASE_PATH.
    Prevents path traversal attacks and unauthorized access.
    """
    base = Path(config.ALLOWED_BASE_PATH).resolve()
    
    # Check for obvious traversal attempts in the string itself
    if ".." in Path(path).parts:
        logger.warning(f"security.path_traversal_attempt: {path}")
        raise PermissionError("Path traversal attempts are forbidden.")
        
    target = (base / path).resolve()
    
    # Ensure the resolved target is still under the base directory
    if not str(target).startswith(str(base)):
        logger.warning(f"security.access_denied: {path} (resolved to {target})")
        raise PermissionError("Access denied: path is outside the allowed workspace.")
        
    return target

def get_backup_path(original_path: Path) -> Path:
    """
    Generates a backup path inside backups/ with a timestamp.
    """
    base = Path(config.ALLOWED_BASE_PATH).resolve()
    backup_dir = base / config.BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Ensure backups/.gitignore exists to avoid committing backups
    gitignore = backup_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n!.gitignore", encoding="utf-8")
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{original_path.name}.{timestamp}.bak"
    
    return backup_dir / backup_name

def get_project_doc_path(filename: str) -> Path:
    """
    Returns the path for a documentation file inside the project repo.
    Routes to repo/docs/filename.
    """
    base = Path(config.ALLOWED_BASE_PATH).resolve()
    doc_dir = base / config.REPO_DIR / config.DOCS_DIR
    doc_dir.mkdir(parents=True, exist_ok=True)
    return doc_dir / filename
