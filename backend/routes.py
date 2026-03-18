"""
routes.py — FastAPI route handlers.

All business logic is delegated to the service layer.
SSE streaming is done via StreamingResponse with an async generator.
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Query, UploadFile, File, Depends, BackgroundTasks
from starlette.responses import StreamingResponse, JSONResponse

from models.schemas import success_response, error_response
from config import config
from mcp_registry.server import handle_sse, handle_messages

# --- Dependency Injectors ---
def get_chat_service():
    from services.chat_service import chat_service
    return chat_service

def get_code_debugger():
    from services.code_debugger import code_debugger
    return code_debugger

def get_repo_service():
    from services.repo_service import repo_service
    return repo_service

def get_tool_service():
    from services.tool_service import tool_service
    return tool_service

def get_tool_selector():
    from copilot.tool_selector import tool_selector
    return tool_selector

logger = logging.getLogger(__name__)


# ─── SSE helpers ──────────────────────────────────────────────────────────────

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


async def _sse_stream(generator):
    """Convert an async generator (str | dict) into SSE bytes."""
    try:
        async for item in generator:
            if isinstance(item, dict):
                yield f"data: {json.dumps(item)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'delta', 'delta': item})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except Exception as e:
        logger.error(f"sse_stream.error error={e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


def streaming_response(generator) -> StreamingResponse:
    return StreamingResponse(
        _sse_stream(generator),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


# ─── Request helpers ──────────────────────────────────────────────────────────

def _require(body: dict, *fields: str):
    for f in fields:
        val = body.get(f, "")
        if isinstance(val, str) and not val.strip():
            raise ValueError(f"'{f}' is required")
        if val is None:
            raise ValueError(f"'{f}' is required")



# ─── Route setup ──────────────────────────────────────────────────────────────

def setup_routes(app: FastAPI):

    # ── File upload ───────────────────────────────────────────────────────────

    @app.post("/api/upload")
    async def upload_file_handler(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
        """Upload any file into the workspace.
        - Images  → returns base64 data URI + type='image'
        - Text/code → returns utf-8 content    + type='text'
        - Binary  → saves only               + type='binary'
        - Zip     → extracts + background index
        """
        import base64, mimetypes

        IMAGE_MIME = {
            "image/png", "image/jpeg", "image/gif", "image/webp",
            "image/bmp", "image/svg+xml", "image/tiff",
        }
        IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".tiff", ".tif"}

        workspace = Path(config.ALLOWED_BASE_PATH)
        upload_dir = workspace / config.UPLOAD_DIR
        repo_dir   = workspace / config.REPO_DIR
        backup_dir = workspace / config.BACKUP_DIR
        
        upload_dir.mkdir(parents=True, exist_ok=True)
        repo_dir.mkdir(parents=True, exist_ok=True)
        backup_dir.mkdir(parents=True, exist_ok=True)

        safe_name = Path(file.filename).name
        ext  = Path(safe_name).suffix.lower()
        
        # Determine destination based on file type
        if ext == ".zip":
            dest = backup_dir / safe_name
        else:
            dest = upload_dir / safe_name
            
        raw = await file.read()

        # Enforce file size limit
        max_bytes = config.MAX_FILE_SIZE_MB * 1024 * 1024
        if len(raw) > max_bytes:
            return JSONResponse(
                status_code=413,
                content=error_response(f"File '{safe_name}' exceeds the {config.MAX_FILE_SIZE_MB}MB upload limit.")
            )

        # Save to disk
        dest.write_bytes(raw)

        # Detect type and handle extraction
        mime = file.content_type or mimetypes.guess_type(safe_name)[0] or ""
        is_image = mime in IMAGE_MIME or ext in IMAGE_EXT

        file_type = "binary"
        content   = None
        data_uri  = None

        if is_image:
            file_type = "image"
            b64 = base64.b64encode(raw).decode()
            data_uri = f"data:{mime or 'image/png'};base64,{b64}"

        elif ext == ".zip":
            file_type = "zip"
            import zipfile
            try:
                # Create project-specific folder
                project_name = Path(safe_name).stem
                project_dir = repo_dir / project_name
                project_dir.mkdir(parents=True, exist_ok=True)
                
                with zipfile.ZipFile(dest, 'r') as zip_ref:
                    zip_ref.extractall(project_dir)
                
                # Trigger indexing in the BACKGROUND
                from services.embedding_service import embedding_service
                extracted_rel_path = f"{config.REPO_DIR}/{project_name}"
                
                # Add task to background
                background_tasks.add_task(embedding_service.index_directory, extracted_rel_path)
                
                content = f"Extracted {len(zip_ref.namelist())} files into '{config.REPO_DIR}/{project_name}/'. Indexing has started in the background. Monitor logs for completion."
            except Exception as e:
                logger.error(f"upload_file_handler.zip_error | {str(e)}")
                content = f"Error extracting zip: {str(e)}"
        else:
            try:
                text = raw.decode("utf-8", errors="replace")
                if len(text) > 100_000:
                    text = text[:100_000] + "\n... [truncated]"
                content   = text
                file_type = "text"
            except Exception:
                file_type = "binary"

        logger.info("upload_file_handler.saved", extra={"file": safe_name, "type": file_type})
        return JSONResponse(content=success_response({
            "filename": safe_name,
            "path":     str(dest),
            "size":     len(raw),
            "type":     file_type,   # "image" | "text" | "binary" | "zip"
            "content":  content,     # text content or extraction summary
            "data_uri": data_uri,    # base64 data URI (images)
            "mime":     mime,
        }))



    # ── OCR: extract text from image ─────────────────────────────────────────

    @app.post("/api/ocr")
    async def ocr_handler(request: Request):
        """
        Extract text/code from an uploaded image using the Ollama vision model.
        Body: { data_uri: "data:image/...;base64,<b64>", mime: "image/png" }
        """
        from llm_client import llm_client

        body = await request.json()
        data_uri: str = body.get("data_uri", "")
        mime: str = body.get("mime", "image/png")

        if not data_uri.startswith("data:"):
            return JSONResponse(status_code=400, content=error_response("data_uri is required"))

        # Strip the "data:<mime>;base64," prefix — Ollama wants raw base64
        try:
            _, b64 = data_uri.split(",", 1)
        except ValueError:
            return JSONResponse(status_code=400, content=error_response("Invalid data_uri format"))

        logger.info("ocr_handler.start", extra={"mime": mime, "model": config.VISION_MODEL})
        try:
            text = await llm_client.extract_text_from_image(b64, mime=mime)
            return JSONResponse(content=success_response({"text": text, "model": config.VISION_MODEL}))
        except Exception as e:
            logger.error(f"ocr_handler.error error={e}")
            return JSONResponse(
                status_code=502,
                content=error_response(
                    f"Vision model ({config.VISION_MODEL}) error: {str(e)}. "
                    f"Make sure the model is available at {config.VISION_BASE_URL}"
                ),
            )

    # ── Health ────────────────────────────────────────────────────────────────

    @app.get("/health")
    async def health_handler():
        from copilot.conversation_manager import conversation_manager
        return {
            "status": "healthy",
            "service": "ai-copilot",
            "sessions": conversation_manager.stats()["active_sessions"],
        }

    # ── Chat (SSE) ────────────────────────────────────────────────────────────

    @app.post("/api/chat")
    async def chat_handler(request: Request, chat_service=Depends(get_chat_service)):
        body = await request.json()
        try:
            _require(body, "message")
        except ValueError as e:
            return JSONResponse(status_code=400, content=error_response(str(e)))

        message = body["message"].strip()
        session_id = body.get("session_id", "default")
        history = body.get("history", [])
        context_code = body.get("context_code")
        language = body.get("language")

        logger.info("chat_handler.request", extra={"session_id": session_id, "message_len": len(message)})

        gen = chat_service.process_message(
            message,
            session_id=session_id,
            history=history,
            context_code=context_code,
            language=language,
        )
        return streaming_response(gen)

    # ── Code operations ───────────────────────────────────────────────────────

    @app.post("/api/code/analyze")
    async def analyze_handler(request: Request, chat_service=Depends(get_chat_service)):
        body = await request.json()
        try:
            _require(body, "code")
        except ValueError as e:
            return JSONResponse(status_code=400, content=error_response(str(e)))

        language = body.get("language", "python")
        task = body.get("task", "analyze")
        gen = chat_service.analyze_code(body["code"].strip(), language=language, task=task)
        return streaming_response(gen)

    @app.post("/api/code/generate")
    async def generate_handler(request: Request, chat_service=Depends(get_chat_service)):
        body = await request.json()
        try:
            _require(body, "prompt")
        except ValueError as e:
            return JSONResponse(status_code=400, content=error_response(str(e)))

        language = body.get("language", "python")
        context = body.get("context")
        gen = chat_service.generate_code(body["prompt"].strip(), language=language, context=context)
        return streaming_response(gen)

    @app.post("/api/code/debug")
    async def debug_handler(request: Request, chat_service=Depends(get_chat_service), code_debugger=Depends(get_code_debugger)):
        body = await request.json()
        code = body.get("code", "")
        error = body.get("error", "")
        language = body.get("language", "python")

        parsed = code_debugger.parse_error(error)
        gen = chat_service.debug_code(code, error, language=language)

        async def _debug_gen():
            yield {"type": "analysis", "data": parsed}
            async for chunk in gen:
                yield chunk

        return streaming_response(_debug_gen())

    # ── Tools ─────────────────────────────────────────────────────────────────

    @app.post("/api/tools/run")
    async def run_tool_handler(request: Request, tool_service=Depends(get_tool_service)):
        body = await request.json()
        try:
            _require(body, "tool_name")
        except ValueError as e:
            return JSONResponse(status_code=400, content=error_response(str(e)))

        tool_name = body["tool_name"].strip()
        parameters = body.get("parameters", {})
        force = body.get("force", False)

        session_id = body.get("session_id", "default")
        logger.info("run_tool_handler.request", extra={"tool": tool_name, "force": force, "session": session_id})
        result = await tool_service.execute(tool_name, parameters, force=force, session_id=session_id)
        return JSONResponse(content=success_response(result))

    @app.get("/api/tools")
    async def list_tools_handler(tool_service=Depends(get_tool_service)):
        tools = await tool_service.list_tools()
        categories = tool_service.get_categories()
        return JSONResponse(content=success_response({"tools": tools, "categories": categories}))

    @app.get("/api/tools/categories")
    async def tool_categories_handler(tool_selector=Depends(get_tool_selector)):
        return JSONResponse(content=success_response(tool_selector.get_tool_categories()))

    # ── Repo ──────────────────────────────────────────────────────────────────

    @app.get("/api/repo/files")
    async def list_files_handler(path: str = ".", repo_service=Depends(get_repo_service)):
        try:
            result = await repo_service.list_files(path)
            return JSONResponse(content=success_response(result))
        except Exception as e:
            return JSONResponse(status_code=500, content=error_response(str(e)))

    @app.get("/api/repo/read")
    async def repo_read_handler(path: str = Query(default=""), repo_service=Depends(get_repo_service)):
        if not path:
            return JSONResponse(status_code=400, content=error_response("path is required"))
        result = await repo_service.read_file(path)
        return JSONResponse(content=success_response(result))

    @app.post("/api/repo/search")
    async def repo_search_handler(request: Request, repo_service=Depends(get_repo_service)):
        body = await request.json()
        try:
            _require(body, "query")
        except ValueError as e:
            return JSONResponse(status_code=400, content=error_response(str(e)))

        result = await repo_service.search(
            body["query"].strip(),
            path=body.get("path", "."),
            file_types=body.get("file_types", []),
        )
        return JSONResponse(content=success_response(result))

    @app.get("/api/repo/analyze")
    async def repo_analyze_handler(path: str = "."):
        """Perform a deep scan of the repository structure and stats."""
        from services.repo_analyzer import repo_analyzer
        try:
            stats = repo_analyzer.analyze(path)
            if "error" in stats:
                return JSONResponse(status_code=400, content=error_response(stats["error"]))
            return JSONResponse(content=success_response(stats))
        except Exception as e:
            return JSONResponse(status_code=500, content=error_response(str(e)))

    @app.get("/api/repo/scan")
    async def repo_scan_handler(path: str = Query(default="."), max_depth: int = Query(default=3), repo_service=Depends(get_repo_service)):
        result = await repo_service.scan(path, max_depth=max_depth)
        return JSONResponse(content=success_response(result))

    # ── Sessions ──────────────────────────────────────────────────────────────

    @app.get("/api/sessions")
    async def sessions_handler():
        from copilot.conversation_manager import conversation_manager
        return JSONResponse(content=success_response(conversation_manager.stats()))

    @app.post("/api/sessions/clear")
    async def clear_session_handler(request: Request):
        from copilot.conversation_manager import conversation_manager
        body = await request.json()
        session_id = body.get("session_id", "default")
        conversation_manager.clear_session(session_id)
        return JSONResponse(content=success_response({"cleared": session_id}))

    # ── WebSocket ─────────────────────────────────────────────────────────────

    @app.websocket("/api/ws/chat")
    async def ws_chat_handler(websocket: WebSocket, chat_service=Depends(get_chat_service)):
        await websocket.accept()
        logger.info("ws_chat_handler.connected")
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    body = json.loads(data)
                    message = body.get("message", "").strip()
                    session_id = body.get("session_id", "default")
                    history = body.get("history", [])
                    context_code = body.get("context_code")
                    language = body.get("language")

                    if not message:
                        await websocket.send_json({"type": "error", "message": "message is required"})
                        continue

                    gen = chat_service.process_message(
                        message,
                        session_id=session_id,
                        history=history,
                        context_code=context_code,
                        language=language,
                    )
                    async for item in gen:
                        if isinstance(item, dict):
                            await websocket.send_json(item)
                        else:
                            await websocket.send_json({"type": "delta", "delta": item})

                    await websocket.send_json({"type": "done"})

                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "message": "invalid JSON"})
                except Exception as e:
                    logger.error(f"ws_chat_handler.error error={e}")
                    await websocket.send_json({"type": "error", "message": str(e)})


        except WebSocketDisconnect:
            logger.info("ws_chat_handler.disconnected")

    # ── MCP SSE ──────────────────────────────────────────────────────────────

    @app.get("/mcp/sse")
    async def mcp_sse_handler(request: Request):
        return await handle_sse(request)

    @app.post("/mcp/messages")
    async def mcp_messages_handler(request: Request):
        return await handle_messages(request)
