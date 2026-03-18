"""
windows_tools.py — Windows-native application integration for MCP.
"""

import os
import subprocess
import logging
from typing import Dict, Any
from mcp_registry.registry import registry

from pydantic import BaseModel
from typing import Optional, List

logger = logging.getLogger(__name__)

class WindowsStatusOutput(BaseModel):
    status: str
    message: Optional[str] = None
    hint: Optional[str] = None
    results_ocr: Optional[str] = None
    screenshot_path: Optional[str] = None
    error: Optional[str] = None

@registry.register(
    name="open_app",
    description="Opens a Windows application by name (e.g., 'calc', 'notepad', 'msword'). IMPORTANT: For web navigation (opening Google, URLs), do NOT use this; use the 'open_browser_url' tool instead for better reliability. After opening, a screenshot and text extraction (OCR) will be performed.",
    parameters={
        "app_name": {
            "type": "string",
            "description": "The command or name of the application to launch (e.g. 'calc', 'notepad', 'winword')."
        },
        "arguments": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional command line arguments.",
            "default": []
        }
    }
)
async def open_app(app_name: str, arguments: list = []) -> dict:
    import time
    import asyncio
    try:
        cmd = [app_name] + [str(a) for a in arguments]
        # Using Popen to launch without blocking the backend
        subprocess.Popen(cmd, shell=True)
        
        # Give the app a few seconds to actually launch and render its window
        await asyncio.sleep(4)
        
        from mcp_registry.tools.gui_tools import take_screenshot
        from mcp_registry.tools.analysis_tools import vision_ocr
        
        shot_res = await take_screenshot(name=f"launch_{app_name}")
        results_ocr = None
        
        if shot_res["status"] == "success":
            shot_path = shot_res["path"]
            try:
                # OCR with fallback timeout
                ocr_res = await asyncio.wait_for(vision_ocr(shot_path), timeout=6.0)
                results_ocr = ocr_res.get("extracted_text")
            except Exception as e:
                logger.warning(f"windows_tools.open_app | OCR_DELAYED: {e}")
                results_ocr = "OCR delayed. Screenshot sent to client."
        
        return WindowsStatusOutput(
            status="success",
            message=f"Successfully requested Windows to open '{app_name}'. Check the screenshot below.",
            results_ocr=results_ocr,
            screenshot_path=shot_res.get("path") if shot_res["status"] == "success" else None,
            hint="If the app didn't capture correctly, it might still be loading or minimized."
        ).model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"windows_tools.open_app | FAILED app='{app_name}' error='{str(e)}'")
        return WindowsStatusOutput(
            status="error",
            error=f"Failed to launch '{app_name}': {str(e)}"
        ).model_dump(exclude_none=True)

@registry.register(
    name="open_office_document",
    description="Opens an Office document (Word, Excel, PPT) using the registered system handler.",
    parameters={
        "file_path": {
            "type": "string",
            "description": "The path to the document to open."
        }
    }
)
async def open_office_document(file_path: str) -> dict:
    try:
        # Resolve path
        from config import config
        abs_path = os.path.abspath(os.path.join(config.ALLOWED_BASE_PATH, file_path))
        
        if not os.path.exists(abs_path):
            return WindowsStatusOutput(status="error", error=f"File not found: {file_path}").model_dump(exclude_none=True)
            
        os.startfile(abs_path)
        return WindowsStatusOutput(
            status="success",
            message=f"Opened document: {file_path}"
        ).model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"windows_tools.office | FAILED path='{file_path}' error='{str(e)}'")
        return WindowsStatusOutput(status="error", error=f"Failed to open document: {str(e)}").model_dump(exclude_none=True)
