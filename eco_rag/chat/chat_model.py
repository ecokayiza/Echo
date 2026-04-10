import json
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

USAGE_KEYS = ("prompt_tokens", "prompt_cache_hit_tokens", "completion_tokens", "total_tokens")


class Message(BaseModel):
    """Store one chat message."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    role: str
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    token_usage: Optional[Dict[str, Any]] = None
    workflow: Optional[Dict[str, Any]] = None

    def to_llm_message(self) -> Dict[str, Any]:
        """Convert one message into the provider payload shape."""
        payload: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            payload["tool_calls"] = self.tool_calls
        return payload


class Response(BaseModel):
    """Store one model response."""

    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
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


def _raw_tool_calls(raw_response: Any) -> Optional[List[Any]]:
    """Extract the provider tool-call payload from a raw completion response."""
    if raw_response is None:
        return None

    choices = getattr(raw_response, "choices", None)
    if isinstance(raw_response, dict):
        choices = raw_response.get("choices")
    if not choices:
        return None

    first_choice = choices[0]
    message = getattr(first_choice, "message", None)
    if isinstance(first_choice, dict):
        message = first_choice.get("message")
    if message is None:
        return None

    tool_calls = getattr(message, "tool_calls", None)
    if isinstance(message, dict):
        tool_calls = message.get("tool_calls")
    return list(tool_calls) if tool_calls else None


def _tool_call_arguments(value: Any) -> Dict[str, Any]:
    """Normalize OpenAI-style function arguments into a dictionary."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError(f"Tool call arguments must decode to a JSON object: {text}")
        return parsed
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        payload = model_dump()
        if isinstance(payload, dict):
            return payload
    raise ValueError(f"Unsupported tool call arguments payload: {value!r}")


def extract_tool_calls(raw_response: Any) -> Optional[List[Dict[str, Any]]]:
    """Convert provider tool calls into the LangGraph-friendly message shape."""
    normalized: List[Dict[str, Any]] = []
    for item in _raw_tool_calls(raw_response) or []:
        function = getattr(item, "function", None)
        item_id = getattr(item, "id", None)
        if isinstance(item, dict):
            function = item.get("function")
            item_id = item.get("id")

        name = getattr(function, "name", None)
        arguments = getattr(function, "arguments", None)
        if isinstance(function, dict):
            name = function.get("name")
            arguments = function.get("arguments")

        if not name:
            raise ValueError(f"Tool call is missing a function name: {item!r}")

        normalized.append(
            {
                "name": str(name),
                "args": _tool_call_arguments(arguments),
                "id": str(item_id or uuid4()),
                "type": "tool_call",
            }
        )

    return normalized or None


class BaseChatModel(ABC):
    """Define the chat model interface used by the app."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 1.0,
        top_p: float | None = None,
        enable_thinking: bool | None = None,
    ):
        """Create the shared provider client."""
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.enable_thinking = enable_thinking

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

    def _build_request_payload(
        self,
        messages: List[Dict[str, str]],
        *,
        tools: Optional[List[Dict]] = None,
        stop: Optional[List[str]] = None,
        stream: bool = False,
        include_optional: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stop": stop,
            **kwargs,
        }
        if tools:
            payload["tools"] = tools
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        if include_optional and self.top_p is not None:
            payload["top_p"] = self.top_p
        if include_optional and self.enable_thinking is not None:
            extra_body = payload.get("extra_body")
            if not isinstance(extra_body, dict):
                extra_body = {}
            extra_body["enable_thinking"] = self.enable_thinking
            payload["extra_body"] = extra_body
        return payload

    async def _create_completion(
        self,
        messages: List[Dict[str, str]],
        *,
        tools: Optional[List[Dict]] = None,
        stop: Optional[List[str]] = None,
        stream: bool = False,
        **kwargs,
    ):
        use_fallback = self.top_p is not None or self.enable_thinking is not None
        try:
            return await self.client.chat.completions.create(
                **self._build_request_payload(
                    messages,
                    tools=tools,
                    stop=stop,
                    stream=stream,
                    include_optional=True,
                    **kwargs,
                )
            )
        except Exception:
            if not use_fallback:
                raise
            return await self.client.chat.completions.create(
                **self._build_request_payload(
                    messages,
                    tools=tools,
                    stop=stop,
                    stream=stream,
                    include_optional=False,
                    **kwargs,
                )
            )

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        stop: Optional[List[str]] = None,
        callbacks: Optional[Any] = None,
        **kwargs,
    ) -> Response:
        """Fetch one non-streaming completion."""
        response = await self._create_completion(
            messages=messages,
            tools=tools,
            stop=stop,
            **kwargs,
        )
        return Response(
            content=response.choices[0].message.content or "",
            tool_calls=extract_tool_calls(response),
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
        response = await self._create_completion(
            messages=messages,
            tools=tools,
            stop=stop,
            stream=True,
            **kwargs,
        )
        async for chunk in response:
            usage = normalize_token_usage(getattr(chunk, "usage", None))
            if usage and callable(on_usage):
                on_usage(usage)
            text = getattr(chunk.choices[0].delta, "content", None)
            if text:
                yield text
