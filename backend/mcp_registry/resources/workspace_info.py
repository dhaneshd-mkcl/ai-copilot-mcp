"""
mcp/resources/workspace_info.py — Example Resource providing workspace metadata.
"""

import os
from mcp_registry.registry import registry
from config import config

@registry.register_resource(
    uri="workspace://info",
    name="Workspace Information",
    description="High-level metadata about the current project workspace, including paths and environment.",
    mime_type="application/json"
)
async def get_workspace_info() -> str:
    """Returns metadata about the allowed workspace."""
    base_path = config.ALLOWED_BASE_PATH
    info = {
        "root": base_path,
        "exists": os.path.exists(base_path),
        "folders": [],
        "files_count": 0,
        "env": "development"
    }
    
    if os.path.exists(base_path):
        try:
            items = os.listdir(base_path)
            info["folders"] = [i for i in items if os.path.isdir(os.path.join(base_path, i))]
            info["files_count"] = len([i for i in items if os.path.isfile(os.path.join(base_path, i))])
        except:
            pass
            
    import json
    return json.dumps(info, indent=2)
