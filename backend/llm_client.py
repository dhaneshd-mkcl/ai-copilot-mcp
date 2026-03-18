import asyncio
import json
import logging
from typing import AsyncGenerator, Optional
import aiohttp
from config import config

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self):
        self.base_url = config.LLM_BASE_URL
        self.model = config.LLM_MODEL
        self.timeout = aiohttp.ClientTimeout(total=config.LLM_TIMEOUT)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self, is_vision: bool = False) -> aiohttp.ClientSession:
        headers = {"Content-Type": "application/json"}
        api_key = config.VISION_API_KEY if is_vision else config.LLM_API_KEY
        
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            
        # Re-use session if headers match, but for simplicity with different keys/urls, 
        # we might just create a temporary one or manage two sessions.
        # Given this is a singleton-like client, let's just make the request directly if needed
        # or manage a separate vision session.
        if is_vision:
            # For vision, we often have different base URLs and keys
            return aiohttp.ClientSession(headers=headers, timeout=self.timeout)
            
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=headers, timeout=self.timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def chat(self, messages: list[dict], stream: bool = False) -> str:
        """Non-streaming chat completion with granular retries."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        for attempt in range(config.LLM_MAX_RETRIES):
            try:
                session = await self._get_session()
                url = f"{self.base_url}/api/chat"
                async with session.post(url, json=payload) as resp:
                    if resp.status in (429, 502, 503, 504):
                        logger.warning(f"llm_client.retryable_error status={resp.status} attempt={attempt+1}")
                        await asyncio.sleep(2 ** attempt)
                        continue
                        
                    resp.raise_for_status()
                    data = await resp.json()
                    return data.get("message", {}).get("content", "")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"LLM attempt {attempt+1} failed: {e}")
                if attempt == config.LLM_MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
        return ""

    async def stream_chat(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """Streaming chat completion using Ollama native API with exponential backoff."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "num_ctx": 64000,   # Match our MAX_CONTEXT_CHARS (approx)
                "num_predict": -1,  # Allow long responses for file writing
                "temperature": 0.2, # More deterministic for code
            }
        }
        
        for attempt in range(config.LLM_MAX_RETRIES):
            try:
                session = await self._get_session()
                url = f"{self.base_url}/api/chat"
                logger.info(f"llm_client.stream_start | MODEL='{self.model}' URL='{url}' MSG_COUNT={len(messages)} ATTEMPT={attempt+1}")
                
                async with session.post(url, json=payload) as resp:
                    if resp.status in (429, 502, 503, 504):
                        logger.warning(f"llm_client.stream_retryable_error status={resp.status} attempt={attempt+1}")
                        await asyncio.sleep(2 ** attempt)
                        continue
                        
                    resp.raise_for_status()
                    async for line in resp.content:
                        line = line.decode("utf-8").strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            content = data.get("message", {}).get("content", "")
                            if content:
                                yield content
                            if data.get("done"):
                                logger.debug("llm_client.stream_done")
                                return # Success exit from retry loop
                        except json.JSONDecodeError as e:
                            logger.warning(f"llm_client.json_decode_error error={e} line={line[:100]}")
                            continue
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"LLM stream attempt {attempt+1} failed: {e}")
                if attempt == config.LLM_MAX_RETRIES - 1:
                    yield f"\n[Error: {str(e)}]"
                    return
                await asyncio.sleep(2 ** attempt)
        return

    async def chat_openai(self, messages: list[dict]) -> str:
        """OpenAI-compatible endpoint."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        session = await self._get_session()
        url = f"{self.base_url}/v1/chat/completions"
        async with session.post(url, json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["choices"][0]["message"]["content"]


    async def extract_text_from_image(self, base64_image: str, mime: str = "image/png") -> str:
        """
        Use specialized vision model (e.g. Qwen3-VL) to extract text / code from an image.
        Uses a dedicated session with proper cleanup.
        """
        url = f"{config.VISION_BASE_URL}/api/chat"
        payload = {
            "model": config.VISION_MODEL,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Extract ALL text from this image exactly as it appears. "
                        "If the image contains code, preserve indentation and formatting. "
                        "Return ONLY the extracted text/code, no extra commentary."
                    ),
                    "images": [base64_image],
                }
            ],
        }

        headers = {"Content-Type": "application/json"}
        if config.VISION_API_KEY:
            headers["Authorization"] = f"Bearer {config.VISION_API_KEY}"

        timeout = aiohttp.ClientTimeout(total=300)
        try:
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    return data.get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.error(f"llm_client.vision_error error={e}")
            raise


llm_client = LLMClient()
