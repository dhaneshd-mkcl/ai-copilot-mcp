"""
response_streamer.py — Compatibility shim.

SSE streaming is now handled directly in routes.py via FastAPI StreamingResponse.
This module is kept so any existing imports don't break.
"""


class ResponseStreamer:
    """No-op shim — streaming is done in routes.py via FastAPI StreamingResponse."""
    pass


response_streamer = ResponseStreamer()
