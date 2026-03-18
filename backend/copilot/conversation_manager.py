"""
ConversationManager — stateful session context for the copilot.

Stores per-session message history, tool results, and repo memory.
This enables multi-turn conversations with full context awareness.
"""

import logging
import time
import json
import redis
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

from config import config


@dataclass
class Session:
    session_id: str
    messages: deque = field(default_factory=lambda: deque(maxlen=config.MAX_HISTORY))
    tool_results: list = field(default_factory=list)
    repo_context: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    def touch(self):
        self.last_active = time.time()

    def is_expired(self) -> bool:
        return (time.time() - self.last_active) > config.SESSION_TTL

    def to_llm_messages(self) -> list[dict]:
        return list(self.messages)


class ConversationManager:
    """
    Thread-safe conversation session store with Redis persistence.
    """

    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._redis = None
        if config.USE_REDIS:
            try:
                self._redis = redis.from_url(config.REDIS_URL, decode_responses=True)
                # Check connection
                self._redis.ping()
                logger.info("conversation_manager.redis | Connected to Redis")
            except Exception as e:
                logger.error(f"conversation_manager.redis | Connection failed: {str(e)}")
                self._redis = None

    def _get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            # Try to load from Redis first if available
            if self._redis:
                try:
                    data = self._redis.hgetall(f"session:{session_id}")
                    if data:
                        session = Session(session_id=session_id)
                        if "messages" in data:
                            session.messages = deque(json.loads(data["messages"]), maxlen=config.MAX_HISTORY)
                        if "tool_results" in data:
                            session.tool_results = json.loads(data["tool_results"])
                        if "repo_context" in data:
                            session.repo_context = data["repo_context"]
                        self._sessions[session_id] = session
                        logger.info("conversation_manager.redis", extra={"status": "loaded", "session_id": session_id})
                        return session
                except Exception as e:
                    logger.error(f"conversation_manager.redis | Load failed: {str(e)}")

            self._sessions[session_id] = Session(session_id=session_id)
            logger.info("conversation_manager.session_created", extra={"session_id": session_id})
        
        session = self._sessions[session_id]
        session.touch()
        return session

    def _save_to_redis(self, session: Session):
        if not self._redis:
            return
        try:
            data = {
                "messages": json.dumps(list(session.messages)),
                "tool_results": json.dumps(session.tool_results),
                "repo_context": session.repo_context or "",
                "last_active": session.last_active
            }
            self._redis.hset(f"session:{session.session_id}", mapping=data)
            self._redis.expire(f"session:{session.session_id}", config.SESSION_TTL)
        except Exception as e:
            logger.error(f"conversation_manager.redis | Save failed: {str(e)}")

    def append(self, session_id: str, role: str, content: str):
        """Add a message to the session history."""
        session = self._get_or_create(session_id)
        session.messages.append({"role": role, "content": content})
        self._save_to_redis(session)

    def get_history(self, session_id: str, reserved_chars: int = 0) -> list[dict]:
        """Return LLM-ready message list, pruned for context size limits."""
        if session_id not in self._sessions:
            return []
        
        session = self._sessions[session_id]
        messages = list(session.messages)
        
        limit = config.MAX_CONTEXT_CHARS - reserved_chars
        total_chars = sum(len(m.get("content", "")) for m in messages)
        
        if total_chars <= limit:
            return messages

        logger.info(f"conversation_manager.pruning | cur={total_chars} limit={limit}")
        
        # Pruning strategy:
        # 1. Always keep the first message (System)
        # 2. Keep the LATEST 3 full turns (User + Asst + Tool Results)
        # 3. For older turns, summarize tool results to just "Tool X returned Y bytes"
        
        pruned = []
        if not messages: return []
        
        system_msg = None
        first_user_msg = None
        
        if messages[0]["role"] == "system":
            system_msg = messages[0].copy()
            messages = messages[1:]
            
        # Also try to find and protect the very first user message
        found_idx = -1
        for i, m in enumerate(messages):
            if m["role"] == "user":
                first_user_msg = m.copy()
                found_idx = i
                break
        if found_idx >= 0:
            messages.pop(found_idx)
            
        # We work backwards from most recent
        current_chars = 0
        system_len = len(system_msg["content"]) if system_msg else 0
        user_len = len(first_user_msg["content"]) if first_user_msg else 0
        
        # SAFETY: If system + first user message eat more than 60% of context, 
        # we have a problem. We will cap them to leave at least 40% for history.
        history_reserve = int(limit * 0.4)
        max_allowed = limit - system_len - user_len
        
        if max_allowed < history_reserve:
            logger.warning(f"conversation_manager.context_crunch | system={system_len} user={user_len} reserve={history_reserve} | TRUNCATING SYSTEM PROMPT")
            max_allowed = history_reserve
            if system_msg:
                # Truncate system prompt from the MIDDLE (keep top instructions and tool summaries)
                content = system_msg["content"]
                if len(content) > (limit - history_reserve - user_len):
                    keep = int((limit - history_reserve - user_len) * 0.8)
                    system_msg["content"] = content[:keep] + "\n... [Instruction system truncated to save memory] ..."
        
        history_buffer = []
        for i, m in enumerate(reversed(messages)):
            content = m.get("content", "")
            role = m.get("role", "")
            
            # 1. Prioritize keeping the LATEST 10 messages untouched
            is_very_recent = i < 10
            
            # 2. Summarize older tool results to save massive space
            if not is_very_recent and role == "user" and "Tool execution results" in content:
                # This is a tool result block. Summarize it!
                try:
                    loaded = json.loads(content.split("```json\n")[1].split("\n```")[0])
                    summary = ", ".join([f"{r.get('name', 'tool')} ({r.get('status', 'ok')})" for r in loaded if isinstance(r, dict)])
                    content = f"Tool execution results SUMMARY: {summary}\n[... Detailed tool output pruned from Turn {i} to save context ...]"
                except:
                    content = "[... Older tool results pruned ...]"
            
            # 2.5 Summarize older assistant thoughts
            if not is_very_recent and role == "assistant" and len(content) > 1000:
                content = content[:800] + "\n... [Older thoughts truncated] ..."

            # 3. Truncate any single message ONLY if it exceeds 30% of the ENTIRE limit
            if len(content) > (config.MAX_CONTEXT_CHARS * 0.3):
                content = content[:int(config.MAX_CONTEXT_CHARS * 0.25)] + "\n... [message truncated to fit window]"

            if current_chars + len(content) < max_allowed:
                m_copy = m.copy()
                m_copy["content"] = content
                history_buffer.insert(0, m_copy)
                current_chars += len(content)
            else:
                # Emergency: Keep at least one more message if it's very short
                if len(content) < 500 and len(history_buffer) < 20: 
                    m_copy = m.copy()
                    m_copy["content"] = content
                    history_buffer.insert(0, m_copy)
                    current_chars += len(content)
                break
                
        if system_msg:
            pruned.append(system_msg)
        if first_user_msg:
            pruned.append(first_user_msg)
        pruned.extend(history_buffer)
        
        return pruned

    def add_tool_result(self, session_id: str, result: dict):
        """Persist a tool execution result to the session."""
        session = self._get_or_create(session_id)
        session.tool_results.append(result)
        # Keep last 20 tool results only
        session.tool_results = session.tool_results[-20:]
        self._save_to_redis(session)

    def get_tool_results(self, session_id: str) -> list[dict]:
        return self._get_or_create(session_id).tool_results

    def set_repo_context(self, session_id: str, context: str):
        session = self._get_or_create(session_id)
        session.repo_context = context
        self._save_to_redis(session)

    def get_repo_context(self, session_id: str) -> Optional[str]:
        return self._get_or_create(session_id).repo_context

    def clear_session(self, session_id: str):
        if session_id in self._sessions:
            del self._sessions[session_id]
        if self._redis:
            self._redis.delete(f"session:{session_id}")
        logger.info("conversation_manager.session_cleared", extra={"session_id": session_id})

    def purge_expired(self):
        """Remove expired sessions to free memory."""
        expired = [sid for sid, s in self._sessions.items() if s.is_expired()]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            logger.info("conversation_manager.purged_sessions", extra={"count": len(expired)})

    def stats(self) -> dict:
        return {
            "active_sessions": len(self._sessions),
            "session_ids": list(self._sessions.keys()),
        }


# Singleton instance
conversation_manager = ConversationManager()
