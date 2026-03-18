"""
gui_tools.py — Windows GUI automation tools for MCP.
"""

import pyautogui
import pygetwindow as gw
import pyperclip
import logging
import time
from typing import Dict, Any, List
from mcp_registry.registry import registry
from config import config

from pydantic import BaseModel
from typing import Optional, List, Union

logger = logging.getLogger(__name__)

class GuiStatusOutput(BaseModel):
    status: str
    message: Optional[str] = None
    error: Optional[str] = None

class ScreenshotOutput(BaseModel):
    status: str
    message: str
    path: str
    filename: str
    error: Optional[str] = None

class ClipboardOutput(BaseModel):
    status: str
    text: str
    length: int
    error: Optional[str] = None

# Safety settings for PyAutoGUI
pyautogui.PAUSE = 0.5  # Add a slight delay after each call
pyautogui.FAILSAFE = True  # Move mouse to top-left to abort

@registry.register(
    name="focus_window",
    description="Finds and focuses a window based on its title.",
    parameters={
        "title": {
            "type": "string",
            "description": "The title of the window to focus (can be a partial match)."
        }
    },
    category="dangerous"
)
async def focus_window(title: str) -> dict:
    try:
        windows = gw.getWindowsWithTitle(title)
        if not windows:
            return GuiStatusOutput(status="error", error=f"No window found with title: '{title}'").model_dump(exclude_none=True)
        
        # Focus the first matching window
        win = windows[0]
        if win.isMinimized:
            win.restore()
        win.activate()
        
        # Give a small delay for the window to actually get focus
        time.sleep(1)
        
        return GuiStatusOutput(
            status="success",
            message=f"Focused window: '{win.title}'"
        ).model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"gui_tools.focus_window | FAILED error='{str(e)}'")
        return GuiStatusOutput(status="error", error=str(e)).model_dump(exclude_none=True)

@registry.register(
    name="type_text",
    description="Types text into the active window, optionally focusing a specific window first. Use this for all GUI interactions like calculators, search bars, and forms instead of writing scripts.",
    parameters={
        "text": {
            "type": "string",
            "description": "The text to type."
        },
        "interval": {
            "type": "number",
            "description": "The delay between characters (default 0.05).",
            "default": 0.05
        },
        "auto_focus": {
            "type": "string",
            "description": "Optional: Title of the window to focus before typing. Highly recommended to ensure text goes to the right place.",
            "default": ""
        }
    }
)
async def type_text(text: str, interval: float = 0.05, auto_focus: str = "") -> dict:
    try:
        if auto_focus:
            focus_res = await focus_window(auto_focus)
            if focus_res["status"] != "success":
                err_msg = focus_res.get('error', 'Unknown focus error')
                logger.warning(f"gui_tools.type_text | Auto-focus failed: {err_msg}")
                return GuiStatusOutput(status="error", error=f"Auto-focus failed: {err_msg}").model_dump(exclude_none=True)

        pyautogui.write(text, interval=interval)
        return GuiStatusOutput(
            status="success",
            message=f"Typed: '{text[:20]}...'"
        ).model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"gui_tools.type_text | FAILED error='{str(e)}'")
        return GuiStatusOutput(status="error", error=str(e)).model_dump(exclude_none=True)

@registry.register(
    name="press_key",
    description="Simulates pressing a special key, optionally focusing a specific window first.",
    parameters={
        "key": {
            "type": "string",
            "description": "The key to press (enter, tab, esc, etc.)."
        },
        "presses": {
            "type": "integer",
            "description": "Number of times to press the key.",
            "default": 1
        },
        "auto_focus": {
            "type": "string",
            "description": "Optional: Title of the window to focus before pressing.",
            "default": ""
        }
    }
)
async def press_key(key: str, presses: int = 1, auto_focus: str = "") -> dict:
    try:
        if auto_focus:
            focus_res = await focus_window(auto_focus)
            if focus_res["status"] != "success":
                err_msg = focus_res.get('error', 'Unknown focus error')
                logger.warning(f"gui_tools.press_key | Auto-focus failed: {err_msg}")
                return GuiStatusOutput(status="error", error=f"Auto-focus failed: {err_msg}").model_dump(exclude_none=True)

        pyautogui.press(key, presses=presses)
        return GuiStatusOutput(status="success", message=f"Pressed '{key}' {presses} times.").model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"gui_tools.press_key | FAILED error='{str(e)}'")
        return GuiStatusOutput(status="error", error=str(e)).model_dump(exclude_none=True)

@registry.register(
    name="hotkey",
    description="Simulates a combination of keys, optionally focusing a specific window first.",
    parameters={
        "keys": {
            "type": "array",
            "items": {"type": "string"},
            "description": "The combination of keys (e.g. ['ctrl', 's'])."
        },
        "auto_focus": {
            "type": "string",
            "description": "Optional: Title of the window to focus before triggering.",
            "default": ""
        }
    }
)
async def hotkey(keys: List[str], auto_focus: str = "") -> dict:
    try:
        if auto_focus:
            focus_res = await focus_window(auto_focus)
            if focus_res["status"] != "success":
                err_msg = focus_res.get('error', 'Unknown focus error')
                logger.warning(f"gui_tools.hotkey | Auto-focus failed: {err_msg}")
                return GuiStatusOutput(status="error", error=f"Auto-focus failed: {err_msg}").model_dump(exclude_none=True)

        pyautogui.hotkey(*keys)
        return GuiStatusOutput(status="success", message=f"Triggered hotkey: {'+'.join(keys)}").model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"gui_tools.hotkey | FAILED error='{str(e)}'")
        return GuiStatusOutput(status="error", error=str(e)).model_dump(exclude_none=True)

@registry.register(
    name="move_and_click",
    description="Moves the mouse to specific coordinates and clicks.",
    parameters={
        "x": {"type": "integer", "description": "X coordinate."},
        "y": {"type": "integer", "description": "Y coordinate."},
        "button": {"type": "string", "description": "Mouse button (left, right, middle).", "default": "left"}
    }
)
async def move_and_click(x: int, y: int, button: str = "left") -> dict:
    try:
        pyautogui.click(x=x, y=y, button=button)
        return GuiStatusOutput(status="success", message=f"Clicked {button} at ({x}, {y})").model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"gui_tools.click | FAILED error='{str(e)}'")
        return GuiStatusOutput(status="error", error=str(e)).model_dump(exclude_none=True)
@registry.register(
    name="take_screenshot",
    description="Takes a screenshot of the main screen and saves it as an artifact.",
    parameters={
        "name": {"type": "string", "description": "Name for the screenshot file (without extension)", "default": "screenshot"}
    },
    category="dangerous",
)
async def take_screenshot(name: str = "screenshot") -> dict:
    """Takes a screenshot and returns the file path."""
    import os
    from datetime import datetime
    
    logger.info(f"gui_tools.take_screenshot | name='{name}'")
    try:
        # Create a screenshots directory in data
        shots_dir = os.path.join(config.ALLOWED_BASE_PATH, "data", "screenshots")
        os.makedirs(shots_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{timestamp}.png"
        filepath = os.path.join(shots_dir, filename)
        
        # Take screenshot
        screenshot = pyautogui.screenshot()
        screenshot.save(filepath)
        
        logger.info(f"gui_tools.take_screenshot | SUCCESS path='{filepath}'")
        return ScreenshotOutput(
            status="success",
            message=f"Screenshot saved to {filename}",
            path=filepath,
            filename=filename
        ).model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"gui_tools.take_screenshot | FAILED error='{str(e)}'")
        return ScreenshotOutput(status="error", message="Failed to take screenshot", path="", filename="", error=str(e)).model_dump(exclude_none=True)
@registry.register(
    name="gui_scroll",
    description="Scrolls the current window or screen.",
    parameters={
        "clicks": {"type": "integer", "description": "Number of scroll 'clicks'. Positive for up, negative for down."},
    },
    category="dangerous",
)
async def gui_scroll(clicks: int) -> dict:
    try:
        pyautogui.scroll(clicks)
        return GuiStatusOutput(status="success", message=f"Scrolled {'up' if clicks > 0 else 'down'} by {abs(clicks)} units.").model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"gui_tools.scroll | FAILED error='{str(e)}'")
        return GuiStatusOutput(status="error", error=str(e)).model_dump(exclude_none=True)
@registry.register(
    name="get_clipboard_text",
    description="Retrieves the current text content of the system clipboard. Useful for verifying GUI actions (e.g., after Ctrl+C in Calculator).",
    parameters={}
)
async def get_clipboard_text() -> dict:
    try:
        text = pyperclip.paste()
        return ClipboardOutput(
            status="success",
            text=text,
            length=len(text)
        ).model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"gui_tools.get_clipboard_text | FAILED error='{str(e)}'")
        return ClipboardOutput(status="error", text="", length=0, error=str(e)).model_dump(exclude_none=True)
