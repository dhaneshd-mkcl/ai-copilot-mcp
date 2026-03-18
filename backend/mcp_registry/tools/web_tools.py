"""
web_tools.py — Web search and exploration tools for MCP.
"""

import webbrowser
import logging
import asyncio
import time
import urllib.parse
import aiohttp
from bs4 import BeautifulSoup
import html2text
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from duckduckgo_search import DDGS
from mcp_registry.tools.gui_tools import take_screenshot
from mcp_registry.tools.analysis_tools import vision_ocr
from mcp_registry.registry import registry
from config import config

# --- Pydantic Output Schemas ---

class WebResult(BaseModel):
    title: Optional[str] = None
    href: Optional[str] = None
    snippet: Optional[str] = None
    body: Optional[str] = None
    source: Optional[str] = None
    date: Optional[str] = None
    image: Optional[str] = None
    thumbnail: Optional[str] = None

class WebSearchOutput(BaseModel):
    status: str
    source: Optional[str] = None
    results: List[WebResult]
    count: int
    error: Optional[str] = None

class GuiSearchOutput(BaseModel):
    status: str
    message: str
    url: str
    screenshot_path: Optional[str] = None
    results_ocr: Optional[str] = None
    hint: Optional[str] = None
    error: Optional[str] = None

class FetchOutput(BaseModel):
    status: str
    url: str
    content: Optional[str] = None
    length: Optional[int] = None
    error: Optional[str] = None

logger = logging.getLogger(__name__)

@registry.register(
    name="web_search_ddg",
    description="Performs a stealthy web search using DuckDuckGo and returns text snippets.",
    parameters={
        "query": {
            "type": "string",
            "description": "The search query."
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of results to return (default 5).",
            "default": 5
        }
    },
    category="safe"
)
async def web_search_ddg(query: str, max_results: int = 5) -> Dict[str, Any]:
    logger.info(f"tool.web_search_ddg | query='{query}'")
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(WebResult(
                    title=r.get("title"),
                    href=r.get("href"),
                    snippet=r.get("body")
                ))
        return WebSearchOutput(status="success", results=results, count=len(results)).model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"tool.web_search_ddg | FAILED error='{str(e)}'")
        return WebSearchOutput(status="error", results=[], count=0, error=f"DuckDuckGo search failed: {str(e)}").model_dump(exclude_none=True)

@registry.register(
    name="web_search_news",
    description="Searches for latest news using DuckDuckGo.",
    parameters={
        "query": {"type": "string", "description": "The news search query."},
        "max_results": {"type": "integer", "description": "Number of results (default 5).", "default": 5}
    },
    category="safe"
)
async def web_search_news(query: str, max_results: int = 5) -> Dict[str, Any]:
    logger.info(f"tool.web_search_news | query='{query}'")
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.news(query, max_results=max_results):
                results.append(WebResult(
                    title=r.get("title"),
                    href=r.get("url"),
                    body=r.get("body"),
                    source=r.get("source"),
                    date=r.get("date")
                ))
        return WebSearchOutput(status="success", results=results, count=len(results)).model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"tool.web_search_news | FAILED error='{str(e)}'")
        return WebSearchOutput(status="error", results=[], count=0, error=str(e)).model_dump(exclude_none=True)

@registry.register(
    name="web_search_images",
    description="Searches for images using DuckDuckGo.",
    parameters={
        "query": {"type": "string", "description": "The image search query."},
        "max_results": {"type": "integer", "description": "Number of results (default 5).", "default": 5}
    },
    category="safe"
)
async def web_search_images(query: str, max_results: int = 5) -> Dict[str, Any]:
    logger.info(f"tool.web_search_images | query='{query}'")
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.images(query, max_results=max_results):
                results.append(WebResult(
                    title=r.get("title"),
                    image=r.get("image"),
                    thumbnail=r.get("thumbnail"),
                    href=r.get("url")
                ))
        return WebSearchOutput(status="success", results=results, count=len(results)).model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"tool.web_search_images | FAILED error='{str(e)}'")
        return WebSearchOutput(status="error", results=[], count=0, error=str(e)).model_dump(exclude_none=True)

@registry.register(
    name="web_search_videos",
    description="Searches for videos using DuckDuckGo.",
    parameters={
        "query": {"type": "string", "description": "The video search query."},
        "max_results": {"type": "integer", "description": "Number of results (default 5).", "default": 5}
    },
    category="safe"
)
async def web_search_videos(query: str, max_results: int = 5) -> Dict[str, Any]:
    logger.info(f"tool.web_search_videos | query='{query}'")
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.videos(query, max_results=max_results):
                results.append(WebResult(
                    title=r.get("title"),
                    snippet=r.get("description"),
                    href=r.get("content"),
                    source=r.get("publisher"),
                    date=r.get("duration") # Using date field for duration in video context
                ))
        return WebSearchOutput(status="success", results=results, count=len(results)).model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"tool.web_search_videos | FAILED error='{str(e)}'")
        return WebSearchOutput(status="error", results=[], count=0, error=str(e)).model_dump(exclude_none=True)

@registry.register(
    name="web_search_google_gui",
    description="Opens the default system browser to a Google search results page.",
    parameters={
        "query": {
            "type": "string",
            "description": "The search query."
        }
    }
)
@registry.register(
    name="web_search_google_gui",
    description="Opens a real browser window to search Google. Use this only if stealth search tools fail. Very reliable but takes 10+ seconds.",
    parameters={
        "query": {"type": "string", "description": "The search query."}
    },
    category="dangerous",
)
async def web_search_google_gui(query: str) -> Dict[str, Any]:
    logger.info(f"tool.web_search_google_gui | query='{query}'")
    try:
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.google.com/search?q={encoded_query}"
        
        webbrowser.open(url)
        
        # New: Robust capture logic
        await asyncio.sleep(8) # Wait for page + results to stabilize
        
        from mcp_registry.tools.gui_tools import take_screenshot
        from mcp_registry.tools.vision_tools import vision_ocr
        
        shot_res = await take_screenshot(name=f"search_{int(time.time())}")
        if shot_res["status"] == "success":
            shot_path = shot_res["path"]
            try:
                # OCR with timeout
                ocr_res = await asyncio.wait_for(vision_ocr(shot_path), timeout=6.0)
            except Exception as e:
                logger.warning(f"tool.web_search_google_gui | OCR_TIMEOUT_OR_ERROR: {e}")
                ocr_res = {"status": "timeout", "extracted_text": "OCR took too long. See screenshot for results."}
            
            return GuiSearchOutput(
                status="success",
                message=f"Results extracted via Vision OCR for query: '{query}'",
                url=url,
                results_ocr=ocr_res.get("extracted_text", "No text extracted"),
                screenshot_path=shot_path,
                hint="Captured results from real browser session."
            ).model_dump(exclude_none=True)

        return GuiSearchOutput(
            status="success",
            message=f"Browser opened Google search for: '{query}' (Screenshot capture failed)",
            url=url
        ).model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"tool.web_search_google_gui | FAILED error='{str(e)}'")
        return GuiSearchOutput(
            status="error",
            message="Failed to open browser or capture results",
            url=url if 'url' in locals() else "",
            error=str(e)
        ).model_dump(exclude_none=True)
@registry.register(
    name="web_search_tavily",
    description="Professional search using Tavily API. High-speed and context-rich.",
    parameters={
        "query": {"type": "string", "description": "The search query."},
        "max_results": {"type": "integer", "description": "Number of results (default 5).", "default": 5}
    },
    category="safe",
)
async def web_search_tavily(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Plan B: High-speed professional search using Tavily API."""
    logger.info(f"tool.web_search_tavily | query='{query}'")
    api_key = config.TAVILY_API_KEY
    if not api_key:
        return WebSearchOutput(status="error", results=[], count=0, error="Tavily API key not configured.").model_dump(exclude_none=True)
        
    try:
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": max_results
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=10) as response:
                if response.status != 200:
                    err_txt = await response.text()
                    return WebSearchOutput(status="error", results=[], count=0, error=f"Tavily API error {response.status}: {err_txt}").model_dump(exclude_none=True)
                
                data = await response.json()
                results = []
                for r in data.get("results", []):
                    results.append(WebResult(
                        title=r.get("title"),
                        href=r.get("url"),
                        body=r.get("content")
                    ))
                
                return WebSearchOutput(
                    status="success",
                    source="Tavily_Search_API",
                    results=results,
                    count=len(results)
                ).model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"tool.web_search_tavily | ERROR: {str(e)}")
        return WebSearchOutput(status="error", results=[], count=0, error=str(e)).model_dump(exclude_none=True)

@registry.register(
    name="web_search_smart",
    description="Tiered web search: DDG (Stealth) -> Tavily (Pro) -> GUI (Reliable). Use this as your primary tool for research. For complex or historical topics, NEVER rely on internal knowledge; perform at least 2-3 searches with diverse queries to ensure accuracy.",
    parameters={
        "query": {"type": "string", "description": "The search query. Be specific and descriptive."},
        "max_results": {"type": "integer", "description": "Number of results (default 5).", "default": 5}
    },
    category="safe",
)
async def web_search_smart(query: str, max_results: int = 5) -> Dict[str, Any]:
    logger.info(f"tool.web_search_smart | query='{query}'")
    
    # Tier 1: DuckDuckGo Text (Fastest, Stealth)
    try:
        ddg_res = await web_search_ddg(query, max_results)
        if ddg_res["status"] == "success" and ddg_res.get("results"):
            return ddg_res
    except Exception as e:
        logger.warning(f"tool.web_search_smart | Tier 1 (DDG Text) failed: {e}")

    # Tier 2: DDG News & Images (Context-Heavy)
    logger.info("tool.web_search_smart | Tier 1 failed or empty. Trying Tier 2 (News & Images)...")
    try:
        news_res = await web_search_news(query, max_results=3)
        img_res = await web_search_images(query, max_results=3)
        
        combined_results = []
        if news_res["status"] == "success":
            combined_results.extend(news_res.get("results", []))
        if img_res["status"] == "success":
            combined_results.extend(img_res.get("results", []))
            
        if combined_results:
            return WebSearchOutput(
                status="success",
                source="DDG_News_Images",
                results=combined_results,
                count=len(combined_results)
            ).model_dump(exclude_none=True)
    except Exception as e:
        logger.warning(f"tool.web_search_smart | Tier 2 (News/Images) failed: {e}")

    # Tier 3: Tavily API (Professional Search)
    logger.info("tool.web_search_smart | Tier 2 failed. Trying Tier 3 (Tavily)...")
    try:
        tavily_res = await web_search_tavily(query, max_results)
        if tavily_res["status"] == "success" and tavily_res.get("results"):
            return tavily_res
    except Exception as e:
        logger.warning(f"tool.web_search_smart | Tier 3 (Tavily) failed: {e}")

    # Tier 4: GUI Google Fallback (Last Resort, Reliable but Slow)
    logger.warning("tool.web_search_smart | Tiers 1-3 failed. Moving to Final Tier (GUI+Vision)...")
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.google.com/search?q={encoded_query}"
        webbrowser.open(url)
        
        # Wait for page to load
        await asyncio.sleep(8) 
        
        # Take screenshot
        shot_res = await take_screenshot(name=f"search_{int(time.time())}")
        if shot_res["status"] != "success":
            return WebSearchOutput(status="error", results=[], count=0, error=f"All search tiers failed. Final error: {shot_res.get('error')}").model_dump(exclude_none=True)
            
        shot_path = shot_res["path"]
        
        # vision OCR to "read" results with timeout
        try:
            ocr_res = await asyncio.wait_for(vision_ocr(shot_path), timeout=6.0)
        except Exception as e:
            logger.warning(f"tool.web_search_smart | OCR_TIMEOUT: {e}")
            ocr_res = {"status": "timeout", "extracted_text": "OCR extraction delayed. Screenshot provided."}
            
        return GuiSearchOutput(
            status="success",
            message="Results extracted via Vision OCR as a last resort.",
            url=url,
            results_ocr=ocr_res.get("extracted_text", "No text extracted"),
            screenshot_path=shot_path,
            hint="GUI fallback used because stealth search failed."
        ).model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"tool.web_search_smart | ALL_TIERS_FAILED error='{str(e)}'")
        return WebSearchOutput(
            status="error",
            results=[],
            count=0,
            error=f"All search strategies failed: {str(e)}"
        ).model_dump(exclude_none=True)

@registry.register(
    name="fetch_web_page",
    description="Fetches full text content of a page as markdown. After searching, use this tool to read the most relevant 2-3 results thoroughly before summarizing or writing reports. Mandatory for deep research tasks.",
    parameters={
        "url": {"type": "string", "description": "The URL of the page to fetch."},
        "timeout": {"type": "integer", "description": "Timeout in seconds (default 15).", "default": 15}
    },
    category="safe",
)
async def fetch_web_page(url: str, timeout: int = 15) -> Dict[str, Any]:
    logger.info(f"tool.fetch_web_page | url='{url}'")
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            async with session.get(url, headers=headers, timeout=timeout) as response:
                response.raise_for_status()
                html = await response.text()
                
                # Use BeautifulSoup to get rid of scripts/styles
                soup = BeautifulSoup(html, "html.parser")
                for script_or_style in soup(["script", "style", "nav", "footer", "header", "aside"]):
                    script_or_style.decompose()
                
                # Convert to markdown
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = True
                h.body_width = 0 # No wrapping
                markdown = h.handle(str(soup))
                
                logger.info(f"tool.fetch_web_page | SUCCESS len={len(markdown)}")
                return FetchOutput(
                    status="success",
                    url=url,
                    content=markdown[:20000],
                    length=len(markdown)
                ).model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"tool.fetch_web_page | FAILED error='{str(e)}'")
        return FetchOutput(status="error", url=url, error=str(e)).model_dump(exclude_none=True)

@registry.register(
    name="open_browser_url",
    description="Opens the user's default web browser to a specific URL. Use this for all web navigation requests (e.g., 'open Google', 'go to reddit.com') as it is the most reliable way to show a window on the user's screen. For fetching data to answer questions, prefer web_search or fetch_web_page unless the user explicitly wants to 'see' the browser.",
    parameters={
        "url": {"type": "string", "description": "The full URL (including http/https) to open."}
    },
    category="safe",
)
async def open_browser_url(url: str) -> Dict[str, Any]:
    logger.info(f"tool.open_browser_url | url='{url}'")
    try:
        # Resolve common short URLs
        if not url.startswith("http"):
            url = f"https://{url}"
            
        # webbrowser.open is the standard way to hit the desktop session
        success = webbrowser.open(url)
        
        return {
            "status": "success" if success else "warning",
            "message": f"Browser opened to: {url}" if success else "Requested browser to open, but ensure the backend has GUI access.",
            "url": url,
            "hint": "The AI has successfully triggered the browser opening. If you don't see it, check if it opened in the background or on another display."
        }
    except Exception as e:
        logger.error(f"tool.open_browser_url | FAILED error='{str(e)}'")
        return {"status": "error", "message": f"Failed to open browser: {str(e)}", "url": url}
