from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from ..config import Config

USAGE_KEYS = ("prompt_tokens", "prompt_cache_hit_tokens", "completion_tokens", "total_tokens")


class Message(BaseModel):
    """Store one chat message."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    role: str
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    token_usage: Optional[Dict[str, Any]] = None

    def to_llm_message(self) -> Dict[str, Any]:
        """Convert one message into the provider payload shape."""
        payload: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            payload["tool_calls"] = self.tool_calls
        return payload


class Response(BaseModel):
    """Store one model response."""

    content: str
    token_usage: Optional[Dict[str, Any]] = None
    raw_response: Any


def _number(value: Any) -> int | float | None:
    """Return numeric values and ignore everything else."""
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _usage_to_dict(usage: Any) -> Optional[Dict[str, Any]]:
    """Convert provider usage objects into plain dictionaries."""
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage
    model_dump = getattr(usage, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    to_dict = getattr(usage, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if hasattr(usage, "__dict__"):
        return dict(usage.__dict__)
    return None


def normalize_token_usage(usage: Any) -> Optional[Dict[str, Any]]:
    """Keep only prompt, cache, completion, and total token counters."""
    payload = _usage_to_dict(usage)
    if not payload:
        return None

    prompt_tokens = _number(payload.get("prompt_tokens"))
    completion_tokens = _number(payload.get("completion_tokens"))
    total_tokens = _number(payload.get("total_tokens"))
    prompt_cache_hit_tokens = _number(payload.get("prompt_cache_hit_tokens"))

    if prompt_cache_hit_tokens is None:
        prompt_details = payload.get("prompt_tokens_details")
        if isinstance(prompt_details, dict):
            prompt_cache_hit_tokens = _number(prompt_details.get("cached_tokens"))

    values = {
        "prompt_tokens": prompt_tokens or 0,
        "prompt_cache_hit_tokens": prompt_cache_hit_tokens or 0,
        "completion_tokens": completion_tokens or 0,
        "total_tokens": total_tokens if total_tokens is not None else (prompt_tokens or 0) + (completion_tokens or 0),
    }
    return values if any(values[key] for key in USAGE_KEYS) else None


class BaseChatModel(ABC):
    """Define the chat model interface used by the app."""

    def __init__(
        self,
        api_key: str | None = Config.API_KEY,
        base_url: str | None = Config.BASE_URL,
        model: str | None = Config.MODEL,
        temperature: float = 1.0,
    ):
        """Create the shared provider client."""
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.temperature = temperature

    @abstractmethod
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        stop: Optional[List[str]] = None,
        callbacks: Optional[Any] = None,
        **kwargs,
    ) -> Response:
        """Return one complete assistant response."""

    @abstractmethod
    async def stream_response(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        stop: Optional[List[str]] = None,
        callbacks: Optional[Any] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Yield one assistant response as text chunks."""


class OpenAIChatModel(BaseChatModel):
    """Call an OpenAI-compatible chat completion endpoint."""

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        stop: Optional[List[str]] = None,
        callbacks: Optional[Any] = None,
        **kwargs,
    ) -> Response:
        """Fetch one non-streaming completion."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            stop=stop,
            **kwargs,
        )
        return Response(
            content=response.choices[0].message.content or "",
            token_usage=normalize_token_usage(getattr(response, "usage", None)),
            raw_response=response,
        )

    async def stream_response(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        stop: Optional[List[str]] = None,
        callbacks: Optional[Any] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Fetch one streaming completion."""
        callback_map = callbacks if isinstance(callbacks, dict) else {}
        on_usage = callback_map.get("on_usage")
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            stop=stop,
            stream=True,
            stream_options={"include_usage": True},
            **kwargs,
        )
        async for chunk in response:
            usage = normalize_token_usage(getattr(chunk, "usage", None))
            if usage and callable(on_usage):
                on_usage(usage)
            text = getattr(chunk.choices[0].delta, "content", None)
            if text:
                yield text
