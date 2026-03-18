import os
import zipfile
import logging
from pathlib import Path
from config import config
from mcp_registry.registry import registry

from pydantic import BaseModel
from typing import Optional, List

logger = logging.getLogger(__name__)

class ZipOutput(BaseModel):
    status: str
    path: Optional[str] = None
    output: Optional[str] = None
    extracted_to: Optional[str] = None
    file_count: Optional[int] = None
    common_root: Optional[str] = None
    structure_hint: Optional[str] = None
    files: Optional[List[str]] = None
    size: Optional[int] = None
    error: Optional[str] = None

class ZipListOutput(BaseModel):
    path: str
    file_count: int
    files: List[str]
    error: Optional[str] = None

from copilot.utils import safe_path

@registry.register(
    name="zip_extract",
    description="Extract a zip archive into a destination directory.",
    parameters={
        "path": {"type": "string", "description": "Path to the zip file relative to workspace"},
        "destination": {"type": "string", "description": "Destination directory relative to workspace", "default": "."},
    },
    category="dangerous",
)
async def zip_extract(path: str, destination: str = ".") -> dict:
    logger.info(f"tool.zip_extract | START path='{path}' dest='{destination}'")
    
    source = safe_path(path)
    dest_dir = safe_path(destination)
    
    if not source.exists() or not source.is_file():
        return ZipOutput(status="error", error=f"Zip file '{path}' not found").model_dump(exclude_none=True)
        
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        with zipfile.ZipFile(source, 'r') as zip_ref:
            files = zip_ref.namelist()
            # Check if all files share a common root folder
            common_root = ""
            if files:
                first = files[0].split('/')[0]
                if all(f.startswith(first + '/') for f in files if f != first):
                    common_root = first

            zip_ref.extractall(dest_dir)
            
            hint = "Files extracted to flat structure."
            if common_root:
                hint = f"Files are nested under a common root folder '{common_root}' within the zip. Use 'repo/ai-copilot-improved/{common_root}' to access them."
            elif files and files[0].endswith('/'):
                 hint = "Files appear to be nested in various sub-folders."

            return ZipOutput(
                status="success",
                extracted_to=str(destination),
                file_count=len(files),
                common_root=common_root,
                structure_hint=hint,
                files=files[:20] + (["..."] if len(files) > 20 else [])
            ).model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"zip_extract.error: {e}")
        return ZipOutput(status="error", error=str(e)).model_dump(exclude_none=True)

@registry.register(
    name="zip_list",
    description="List the contents of a zip archive without extracting.",
    parameters={
        "path": {"type": "string", "description": "Path to the zip file relative to workspace"},
    },
    category="safe",
)
async def zip_list(path: str) -> dict:
    logger.info(f"tool.zip_list | START path='{path}'")
    source = safe_path(path)
    
    if not source.exists() or not source.is_file():
        return ZipListOutput(path=str(path), file_count=0, files=[], error=f"Zip file '{path}' not found").model_dump(exclude_none=True)
        
    try:
        with zipfile.ZipFile(source, 'r') as zip_ref:
            files = zip_ref.namelist()
            return ZipListOutput(
                path=str(path),
                file_count=len(files),
                files=files
            ).model_dump(exclude_none=True)
    except Exception as e:
        return ZipListOutput(path=str(path), file_count=0, files=[], error=str(e)).model_dump(exclude_none=True)

@registry.register(
    name="zip_create",
    description="Create a zip archive from a directory or file.",
    parameters={
        "path": {"type": "string", "description": "Path to the directory or file to zip"},
        "output_name": {"type": "string", "description": "Name of the output zip file (e.g. 'archive.zip')"},
    },
    category="dangerous",
)
async def zip_create(path: str, output_name: str) -> dict:
    logger.info(f"tool.zip_create | START path='{path}' output='{output_name}'")
    source = safe_path(path)
    output = safe_path(output_name)
    
    if not source.exists():
        return ZipOutput(status="error", error=f"Source '{path}' not found").model_dump(exclude_none=True)
        
    try:
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
            if source.is_file():
                zip_ref.write(source, source.name)
            else:
                for root, dirs, files in os.walk(source):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(source.parent)
                        zip_ref.write(file_path, arcname)
                        
        return ZipOutput(
            status="success",
            output=output_name,
            size=output.stat().st_size
        ).model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"zip_create.error: {e}")
        return ZipOutput(status="error", error=str(e)).model_dump(exclude_none=True)
