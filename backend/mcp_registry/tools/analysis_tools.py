import os
import re
import logging
from pathlib import Path
from config import config
from mcp_registry.registry import registry

from copilot.utils import safe_path

from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Union

logger = logging.getLogger(__name__)

class RouteInfo(BaseModel):
    path: str
    method: str
    endpoint: str

class ServiceInfo(BaseModel):
    path: str
    call: str
    endpoint: str

class ArchitectureMapOutput(BaseModel):
    backend_routes: List[RouteInfo]
    frontend_services: List[ServiceInfo]
    entry_points: List[str]
    configs: List[str]
    error: Optional[str] = None

class VisionOutput(BaseModel):
    status: str
    extracted_text: Optional[str] = None
    detected_elements: Optional[Union[str, List[dict]]] = None
    path: str
    note: Optional[str] = None
    error: Optional[str] = None

@registry.register(
    name="map_architecture",
    description="Analyze the project to identify core entry points, routes, and cross-file connections (APIs, services).",
    parameters={},
    category="safe",
)
async def map_architecture() -> dict:
    logger.info("tool.map_architecture | START")
    base = Path(config.ALLOWED_BASE_PATH).resolve()
    
    mapping = {
        "backend_routes": [],
        "frontend_services": [],
        "entry_points": [],
        "configs": []
    }
    
    # Common Patterns
    patterns = {
        "py_route": re.compile(r"@(app|router)\.(get|post|put|delete|patch|route)\(['\"]([^'\"]+)['\"]"),
        "js_fetch": re.compile(r"(fetch|axios\.(get|post|put|delete))\(['\"]([^'\"]+)['\"]"),
        "js_api_url": re.compile(r"VITE_API_BASE_URL|API_URL|BASE_URL"),
        "main_entry": re.compile(r"if __name__ == ['\"]__main__['\"]|createApp\(|ReactDOM.render"),
    }

    ignore = {".git", "node_modules", "__pycache__", ".venv", "dist", ".next"}

    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ignore]
        for fname in files:
            if not any(fname.endswith(ext) for ext in [".py", ".js", ".ts", ".vue", ".json"]):
                continue
                
            fpath = Path(root) / fname
            rel_path = str(fpath.relative_to(base))
            
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                
                # Check Entry Points
                if patterns["main_entry"].search(content):
                    mapping["entry_points"].append(rel_path)
                
                # Check Backend Routes (Python)
                if fname.endswith(".py"):
                    for match in patterns["py_route"].finditer(content):
                        mapping["backend_routes"].append(RouteInfo(
                            path=rel_path,
                            method=match.group(2).upper(),
                            endpoint=match.group(3)
                        ))
                
                # Check Frontend API calls & URLs
                if any(fname.endswith(ext) for ext in [".js", ".ts", ".vue"]):
                    for match in patterns["js_fetch"].finditer(content):
                        mapping["frontend_services"].append(ServiceInfo(
                            path=rel_path,
                            call=match.group(0),
                            endpoint=match.group(3)
                        ))
                    if patterns["js_api_url"].search(content):
                        mapping["configs"].append(rel_path)
                        
            except Exception:
                continue

    logger.info(f"tool.map_architecture | SUCCESS entries={len(mapping['entry_points'])} routes={len(mapping['backend_routes'])}")
    return ArchitectureMapOutput(**mapping).model_dump(exclude_none=True)
@registry.register(
    name="vision_ocr",
    description="Uses a vision model to extract text or code from an image file.",
    parameters={
        "path": {"type": "string", "description": "Absolute path to the image file."}
    },
    category="safe",
)
async def vision_ocr(path: str) -> dict:
    logger.info(f"tool.vision_ocr | START path='{path}'")
    from llm_client import llm_client
    import base64
    from PIL import Image
    import io
    
    full_path = Path(path)
    if not full_path.exists():
        return {"error": f"Image file not found: {path}"}
        
    try:
        # Load and Optimize image for Vision API
        with Image.open(full_path) as img:
            # 1. Resize if too large (e.g., max width 1280)
            max_size = 1280
            if img.width > max_size:
                ratio = max_size / float(img.width)
                new_height = int(float(img.height) * ratio)
                img = img.resize((max_size, new_height), Image.Resampling.LANCZOS)
                logger.info(f"tool.vision_ocr | RESIZED to {max_size}x{new_height}")

            # 2. Compress to JPEG
            img_byte_arr = io.BytesIO()
            # Convert RGBA to RGB if necessary for JPEG
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(img_byte_arr, format='JPEG', quality=80)
            base64_image = base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")
        
        text = await llm_client.extract_text_from_image(base64_image, "image/jpeg")
        
        if not text:
             logger.warning(f"tool.vision_ocr | EMPTY_RESULT path='{path}'")
             return VisionOutput(status="error", path=path, error="Vision model returned no text.").model_dump(exclude_none=True)

        return VisionOutput(
            status="success",
            extracted_text=text,
            path=path
        ).model_dump(exclude_none=True)
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"tool.vision_ocr | ERROR: {error_msg}")
        return VisionOutput(status="error", path=path, error=error_msg).model_dump(exclude_none=True)
@registry.register(
    name="vision_locate_elements",
    description="Uses a vision model to find clickable elements (buttons, links) in an image and returns their coordinates.",
    parameters={
        "path": {"type": "string", "description": "Absolute path to the image file."},
        "description": {"type": "string", "description": "Description of what elements to find (e.g. 'search result links', 'accept cookies button')."}
    },
    category="safe",
)
async def vision_locate_elements(path: str, description: str) -> dict:
    logger.info(f"tool.vision_locate_elements | path='{path}' query='{description}'")
    from llm_client import llm_client
    import base64
    
    full_path = Path(path)
    if not full_path.exists():
        return {"error": f"Image file not found: {path}"}
        
    try:
        with open(full_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")
        
        # We use a specialized prompt for coordinate extraction
        prompt = (
            f"Find the following elements in the image: {description}. "
            "For each element, return its approximate [x, y] coordinates as a percentage of image width/height (0-100). "
            "Return the results as a JSON list of objects: [{\"label\": \"...\", \"x\": 50, \"y\": 30}]. "
            "Return ONLY the JSON block."
        )
        
        # Re-using the same vision extraction but with a specific prompt
        # In a more advanced setup, we'd use a dedicated 'detect' endpoint if available
        # but Qwen3-VL/VL-Chat can handle coordinate generation in text.
        text = await llm_client.extract_text_from_image(base64_image)
        
        return VisionOutput(
            status="success",
            detected_elements=text,
            path=path,
            note="Coordinates are percentages. Multiply by screen width/height to use with mouse tools."
        ).model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"tool.vision_locate_elements | ERROR: {str(e)}")
        return VisionOutput(status="error", path=path, error=str(e)).model_dump(exclude_none=True)
