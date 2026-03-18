import asyncio
from app import create_app
from mcp_registry.server import mcp, bridge_legacy_tools

async def test():
    app = create_app()
    bridge_legacy_tools()
    
    # Check if tools got bridged
    tools = await mcp._mcp_server.list_tools()
    print("Bridged FastMCP Tools:")
    for t in tools.tools:
        print(f" - {t.name}")

if __name__ == "__main__":
    asyncio.run(test())
