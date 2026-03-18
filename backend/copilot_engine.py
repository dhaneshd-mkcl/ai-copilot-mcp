"""
CopilotEngine — thin façade that delegates to the service layer.

Kept for backward compatibility. New code should import from
services/chat_service.py directly.
"""

import logging
from typing import AsyncGenerator, Optional

from services.chat_service import chat_service

logger = logging.getLogger(__name__)


class CopilotEngine:
    """Thin façade — all logic lives in ChatService and copilot sub-modules."""

    async def chat(
        self,
        message: str,
        history: list[dict] = None,
        context_code: str = None,
        language: str = None,
        session_id: str = "default",
    ) -> AsyncGenerator:
        async for item in chat_service.process_message(
            message,
            session_id=session_id,
            history=history or [],
            context_code=context_code,
            language=language,
        ):
            yield item

    async def analyze_code(
        self, code: str, language: str = "python", task: str = "analyze"
    ) -> AsyncGenerator[str, None]:
        async for chunk in chat_service.analyze_code(code, language=language, task=task):
            yield chunk

    async def generate_code(
        self, prompt: str, language: str = "python", context: str = None
    ) -> AsyncGenerator[str, None]:
        async for chunk in chat_service.generate_code(prompt, language=language, context=context):
            yield chunk

    async def debug_code(
        self, code: str, error: str, language: str = "python"
    ) -> AsyncGenerator[str, None]:
        async for chunk in chat_service.debug_code(code, error, language=language):
            yield chunk


copilot_engine = CopilotEngine()
