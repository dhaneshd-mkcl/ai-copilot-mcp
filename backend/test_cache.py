import asyncio
import os
from mcp_registry.tools.web_tools import web_research
from mcp_registry.tools.firecrawl_tools import firecrawl_scrape, _write_cache, _read_cache

async def test_logic():
    # Only testing the routing part by looking at logs, or we can mock it
    # But let's just test cache functions directly
    
    url = "https://example.com"
    mode = "full"
    data = {"status": "success", "url": url, "markdown": "Test cached markdown"}
    
    print("Writing cache...")
    _write_cache(url, mode, data)
    
    print("Reading cache...")
    res = _read_cache(url, mode)
    if res and res.get("markdown") == "Test cached markdown":
        print("Cache Works!")
    else:
        print("Cache Failed!")
        
    # Clean up test cache
    import hashlib
    hash_str = hashlib.md5(f"{url}_{mode}".encode()).hexdigest()
    cache_path = os.path.join(".", ".cache", "firecrawl", f"{hash_str}.json")
    if os.path.exists(cache_path):
        os.remove(cache_path)

if __name__ == "__main__":
    asyncio.run(test_logic())
