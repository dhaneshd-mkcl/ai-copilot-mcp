from dataclasses import dataclass, field
from typing import Any, Optional
import time


@dataclass
class Message:
    role: str
    content: str


@dataclass
class ChatRequest:
    message: str
    history: list = field(default_factory=list)
    context_code: Optional[str] = None
    language: Optional[str] = None
    stream: bool = True


@dataclass
class CodeAnalyzeRequest:
    code: str
    language: str = "python"
    task: str = "analyze"  # analyze | debug | explain | refactor | test


@dataclass
class CodeGenerateRequest:
    prompt: str
    language: str = "python"
    context: Optional[str] = None


@dataclass
class ToolRunRequest:
    tool_name: str
    parameters: dict = field(default_factory=dict)


@dataclass
class RepoSearchRequest:
    query: str
    path: str = "."
    file_types: list = field(default_factory=list)


def success_response(data: Any, message: str = "OK") -> dict:
    return {"status": "success", "message": message, "data": data, "timestamp": time.time()}


def error_response(message: str, code: int = 400) -> dict:
    return {"status": "error", "message": message, "code": code, "timestamp": time.time()}
