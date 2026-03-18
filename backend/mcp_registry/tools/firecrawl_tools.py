import logging
import asyncio
import hashlib
import json
import os
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from firecrawl import FirecrawlApp
from requests.exceptions import Timeout, RequestException

from mcp_registry.registry import registry
from config import config

logger = logging.getLogger(__name__)

# --- Simple File Cache Implementation ---
CACHE_DIR = os.path.join(config.ALLOWED_BASE_PATH, ".cache", "firecrawl")
os.makedirs(CACHE_DIR, exist_ok=True)

def _get_cache_key(url: str, mode: str) -> str:
    hash_str = hashlib.md5(f"{url}_{mode}".encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{hash_str}.json")

def _read_cache(url: str, mode: str) -> Optional[Dict[str, Any]]:
    path = _get_cache_key(url, mode)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def _write_cache(url: str, mode: str, data: Dict[str, Any]):
    path = _get_cache_key(url, mode)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"Failed to write cache for {url}: {e}")

class ScrapeOutput(BaseModel):
    status: str
    url: str
    markdown: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    cached: bool = False

class CrawlOutput(BaseModel):
    status: str
    base_url: str
    pages: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None

def get_firecrawl_app() -> Optional[FirecrawlApp]:
    api_key = config.FIRECRAWL_API_KEY
    if not api_key:
        return None
    return FirecrawlApp(api_key=api_key)

@registry.register(
    name="firecrawl_scrape",
    description="Extracts clean, structured markdown content from a single web page using the Firecrawl API. Optimized for LLM context.",
    parameters={
        "url": {"type": "string", "description": "The URL of the webpage to scrape."},
        "mode": {
            "type": "string",
            "description": "Output mode: 'summary' (short summary), 'full' (entire markdown), or 'chunks' (context snippets).",
            "default": "full"
        }
    },
    category="safe",
)
async def firecrawl_scrape(url: str, mode: str = "full") -> Dict[str, Any]:
    logger.info(f"tool.firecrawl_scrape | url='{url}' mode='{mode}'")
    
    # Check Cache
    cached_data = _read_cache(url, mode)
    if cached_data:
        logger.info(f"tool.firecrawl_scrape | CACHE HIT for {url}")
        return cached_data

    app = get_firecrawl_app()
    if not app:
        return ScrapeOutput(
            status="error",
            url=url,
            error="FIRECRAWL_API_KEY not configured in environment."
        ).model_dump(exclude_none=True)

    try:
        # Define formats based on mode
        params = {'formats': ['markdown']}
        if mode == "summary":
            params["extract"] = {"prompt": "Provide a comprehensive summary of this page content."}
        
        loop = asyncio.get_event_loop()
        
        # Add timeout manually since SDK might not expose it cleanly
        scrape_result = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: app.scrape_url(url, params=params)),
            timeout=30.0
        )
        
        # Clean & Chunk output if needed
        markdown = scrape_result.get("markdown", "")
        if mode == "chunks" and markdown:
            # Simple chunking logic to protect context length
            chunks = [markdown[i:i+4000] for i in range(0, len(markdown), 4000)]
            markdown = f"Total {len(chunks)} chunks. Showing first chunk:\n\n{chunks[0]}"
        elif mode == "summary" and "extract" in scrape_result:
            markdown = scrape_result["extract"].get("data", markdown)
            
        result = ScrapeOutput(
            status="success",
            url=url,
            markdown=markdown,
            metadata=scrape_result.get("metadata", {})
        ).model_dump(exclude_none=True)
        
        # Write to Cache
        _write_cache(url, mode, result)
        
        return result
        
    except asyncio.TimeoutError:
        logger.error(f"tool.firecrawl_scrape | TIMEOUT error for {url}")
        return ScrapeOutput(status="error", url=url, error="Scraping timed out after 30 seconds.").model_dump(exclude_none=True)
    except RequestException as e:
        logger.error(f"tool.firecrawl_scrape | NETWORK ERROR: {str(e)}")
        return ScrapeOutput(status="error", url=url, error=f"Network Error/Rate Limit: {str(e)}").model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"tool.firecrawl_scrape | UNEXPECTED ERROR: {str(e)}")
        return ScrapeOutput(status="error", url=url, error=f"Scrape Failed: {str(e)}").model_dump(exclude_none=True)

@registry.register(
    name="firecrawl_crawl",
    description="Crawls a website and extracts markdown from multiple pages. Useful for indexing entire documentation sites.",
    parameters={
        "url": {"type": "string", "description": "The base URL to start crawling."},
        "limit": {"type": "integer", "description": "Maximum number of pages to crawl (default 10).", "default": 10}
    },
    category="safe",
)
async def firecrawl_crawl(url: str, limit: int = 10) -> Dict[str, Any]:
    logger.info(f"tool.firecrawl_crawl | url='{url}' limit={limit}")
    app = get_firecrawl_app()
    if not app:
        return CrawlOutput(
            status="error",
            base_url=url,
            error="FIRECRAWL_API_KEY not configured in environment."
        ).model_dump(exclude_none=True)

    try:
        loop = asyncio.get_event_loop()
        crawl_status = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: app.crawl_url(
                url, 
                params={'limit': limit, 'scrapeOptions': {'formats': ['markdown']}}, 
                poll_interval=20
            )),
            timeout=120.0
        )
        
        pages = []
        for page in crawl_status.get("data", []):
            pages.append({
                "url": page.get("metadata", {}).get("sourceURL"),
                "title": page.get("metadata", {}).get("title"),
                "markdown": page.get("markdown", "")[:4000] # Truncate per page for safety
            })
            
        return CrawlOutput(
            status="success",
            base_url=url,
            pages=pages
        ).model_dump(exclude_none=True)
        
    except asyncio.TimeoutError:
        logger.error(f"tool.firecrawl_crawl | TIMEOUT error for {url}")
        return CrawlOutput(status="error", base_url=url, error="Crawling timed out after 120 seconds.").model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"tool.firecrawl_crawl | ERROR: {str(e)}")
        return CrawlOutput(status="error", base_url=url, error=str(e)).model_dump(exclude_none=True)
