from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from inspect import isawaitable
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable

from ..config import Config
from .chat_model import Message

USAGE_KEYS = ("prompt_tokens", "prompt_cache_hit_tokens", "completion_tokens", "total_tokens")


def utc_now() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def default_session_title() -> str:
    """Return the default title for a new session."""
    return "New Session"


MessageResponseFactory = Callable[
    [list[dict[str, Any]]],
    Awaitable[tuple[str, dict[str, Any] | None]] | tuple[str, dict[str, Any] | None],
]


class Sessions:
    """Read, write, and summarize chat sessions."""

    def __init__(
        self,
        session_id: str,
        *,
        storage: dict[str, dict[str, Any]] | None = None,
        base_dir: str | Path | None = None,
    ):
        """Bind one session id to file or in-memory storage."""
        self.session_id = session_id
        self.storage = storage
        self.base_dir = Path(base_dir or Config.CHAT_MEMORY_DIR)
        if self.storage is None:
            self.base_dir.mkdir(parents=True, exist_ok=True)

    def exists(self) -> bool:
        """Return whether the session already exists."""
        return self.session_id in self.storage if self.storage is not None else self._file(self.session_id).exists()

    def get(self) -> dict[str, Any]:
        """Load the current session payload."""
        if self.storage is not None:
            return self._session(self.storage.get(self.session_id))

        path = self._file(self.session_id)
        return self._session(json.loads(path.read_text(encoding="utf-8")) if path.exists() else None)

    def ensure(self, title: str | None = None) -> dict[str, Any]:
        """Create the session when it does not exist yet."""
        if not self.exists():
            return self.persist(self._empty(title))

        session = self.get()
        title = (title or "").strip()
        if title and session["title"] == default_session_title():
            session["title"] = title
            return self.persist(session)
        return session

    def summary(self) -> dict[str, Any]:
        """Return the compact summary used by lists and API responses."""
        return self._summary(self.get())

    def list(self) -> list[dict[str, Any]]:
        """List all saved sessions ordered by update time."""
        if self.storage is not None:
            sessions = [self._summary(item) for item in self.storage.values()]
        else:
            sessions = [
                self._summary(json.loads(path.read_text(encoding="utf-8")))
                for path in self.base_dir.glob("*.json")
                if not path.name.startswith(".")
            ]
        return sorted(sessions, key=lambda item: item["updated_at"], reverse=True)

    def set_title(self, title: str):
        """Replace the current session title."""
        session = self.get()
        session["title"] = title.strip() or default_session_title()
        self.persist(session)

    def persist(self, session: dict[str, Any]) -> dict[str, Any]:
        """Write a session using the current compact file shape."""
        session = self._session(session)
        session["updated_at"] = utc_now()
        session["usage"] = self._usage(session["messages"])
        if self.storage is not None:
            self.storage[self.session_id] = session
        else:
            self._file(self.session_id).write_text(
                json.dumps(
                    {
                        "session_id": session["session_id"],
                        "title": session["title"],
                        "created_at": session["created_at"],
                        "updated_at": session["updated_at"],
                        "usage": session["usage"],
                        "messages": [self._dump_message(message) for message in session["messages"]],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        return self.get()

    def delete(self):
        """Remove the current session from storage."""
        if self.storage is not None:
            self.storage.pop(self.session_id, None)
            return

        path = self._file(self.session_id)
        if path.exists():
            path.unlink()

    def _empty(self, title: str | None = None) -> dict[str, Any]:
        """Create a blank session payload."""
        return {
            "session_id": self.session_id,
            "title": (title or "").strip() or default_session_title(),
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "usage": {},
            "messages": [],
        }

    def _session(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        """Normalize raw storage data into the current session shape."""
        if not isinstance(payload, dict):
            return self._empty()
        return {
            "session_id": payload.get("session_id", self.session_id),
            "title": payload.get("title") or default_session_title(),
            "created_at": payload.get("created_at") or utc_now(),
            "updated_at": payload.get("updated_at") or utc_now(),
            "usage": self._usage_dict(payload.get("usage")),
            "messages": [
                message.model_copy(deep=True) if isinstance(message, Message) else Message(**message)
                for message in payload.get("messages", [])
            ],
        }

    def _summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Build the list-friendly summary view for a session."""
        session = self._session(payload)
        preview = next(
            (
                message.content.strip()[:80]
                for message in reversed(session["messages"])
                if message.role != "system" and message.content.strip()
            ),
            "",
        )
        usage = dict(session["usage"])
        total = usage.get("total_tokens", (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0))
        return {
            "session_id": session["session_id"],
            "title": session["title"],
            "created_at": session["created_at"],
            "updated_at": session["updated_at"],
            "message_count": len(session["messages"]),
            "preview": preview,
            "token_usage": usage,
            "total_tokens": int(total),
        }

    def _file(self, session_id: str) -> Path:
        """Map a session id to a stable file path."""
        prefix = re.sub(r"[^A-Za-z0-9_.-]+", "_", session_id).strip("._-") or "session"
        digest = hashlib.sha1(session_id.encode("utf-8")).hexdigest()[:10]
        return self.base_dir / f"{prefix}-{digest}.json"

    @staticmethod
    def _dump_message(message: Message) -> dict[str, Any]:
        """Serialize one message for storage."""
        payload = {"id": message.id, "role": message.role, "content": message.content}
        if message.tool_calls:
            payload["tool_calls"] = message.tool_calls
        usage = Sessions._usage_dict(message.token_usage)
        if usage:
            payload["token_usage"] = usage
        if isinstance(message.workflow, dict):
            payload["workflow"] = message.workflow
        return payload

    @staticmethod
    def _usage_dict(token_usage: dict[str, Any] | None) -> dict[str, int | float]:
        """Keep only the token counters the app tracks."""
        if not isinstance(token_usage, dict):
            return {}
        return {
            key: value
            for key in USAGE_KEYS
            if isinstance((value := token_usage.get(key)), (int, float)) and not isinstance(value, bool)
        }

    @staticmethod
    def _usage(messages: list[Message]) -> dict[str, int | float]:
        """Aggregate token usage across all messages in a session."""
        usage: dict[str, int | float] = {}
        for message in messages:
            for key, value in Sessions._usage_dict(message.token_usage).items():
                usage[key] = usage.get(key, 0) + value
        return usage


class Messages:
    """Manage message history and in-chat operations for one session."""

    def __init__(
        self,
        sessions: Sessions,
        *,
        max_context_messages: int = 12,
        preserve_system_messages: bool = True,
    ):
        """Bind message operations to one session."""
        self.sessions = sessions
        self.max_context_messages = max_context_messages
        self.preserve_system_messages = preserve_system_messages

    def get(self) -> list[Message]:
        """Return the current session messages."""
        return self.sessions.get()["messages"]

    def history(self) -> list[dict[str, Any]]:
        """Return messages as plain dictionaries for the API."""
        return [message.model_dump(exclude_none=True) for message in self.get()]

    def build_context(self, messages: list[Message] | None = None) -> list[dict[str, Any]]:
        """Build the LLM context from system messages and recent turns."""
        if self.max_context_messages < 0:
            raise ValueError("max_context_messages must be non-negative.")

        messages = messages or self.get()
        system = [message.model_copy(deep=True) for message in messages if message.role == "system"]
        recent = [message.model_copy(deep=True) for message in messages if message.role != "system"]
        recent = [] if self.max_context_messages == 0 else recent[-self.max_context_messages :]
        return [message.to_llm_message() for message in ([*system, *recent] if self.preserve_system_messages else recent)]

    def append(
        self,
        role: str,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
        token_usage: dict[str, Any] | None = None,
        workflow: dict[str, Any] | None = None,
    ) -> Message:
        """Append one message and persist the session."""
        session = self.sessions.get()
        message = Message(
            role=role,
            content=self._text(content, "Message content cannot be empty."),
            tool_calls=tool_calls,
            token_usage=token_usage,
            workflow=workflow,
        )
        session["messages"].append(message)
        self.sessions.persist(session)
        return message.model_copy(deep=True)

    def replace(self, messages: Iterable[Message | dict[str, Any]]) -> dict[str, Any]:
        """Replace the full message list."""
        session = self.sessions.get()
        session["messages"] = [message.model_copy(deep=True) if isinstance(message, Message) else Message(**message) for message in messages]
        return self.sessions.persist(session)

    def clear(self) -> dict[str, Any]:
        """Remove all messages from the session."""
        session = self.sessions.get()
        session["messages"] = []
        return self.sessions.persist(session)

    async def apply(
        self,
        operation: str,
        *,
        content: str | None = None,
        message_id: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        response_factory: MessageResponseFactory | None = None,
    ) -> dict[str, Any]:
        """Apply one unified in-chat mutation."""
        operation = operation.strip().lower()
        if operation not in {"send", "edit", "delete", "rollback", "regenerate", "system_prompt"}:
            raise ValueError(f"Unsupported message operation: {operation}")

        session = self.sessions.ensure()

        if operation == "system_prompt":
            session = self._set_system(session, content)
            session = self.sessions.persist(session)
            return self._result(session, affected_message_id=self.system_message_id(session))

        if operation == "send":
            session["messages"].append(
                Message(role="user", content=self._text(content, "Message content cannot be empty."), tool_calls=tool_calls)
            )
            return await self._generate(session, response_factory, operation)

        if message_id is None:
            raise ValueError(f"{operation} requires a message_id.")

        index = self.find_index(message_id, session["messages"])
        target = session["messages"][index]

        if operation == "edit":
            if target.role == "system":
                session = self._set_system(session, content)
                session = self.sessions.persist(session)
                return self._result(session, affected_message_id=self.system_message_id(session))
            target.content = self._text(content, "Message content cannot be empty.")
            return self._result(self.sessions.persist(session), affected_message_id=message_id)

        if operation == "delete":
            if target.role == "system":
                return self._result(self.sessions.persist(self._set_system(session, None)))
            session["messages"] = [*session["messages"][:index], *session["messages"][index + 1 :]]
            return self._result(self.sessions.persist(session), affected_message_id=message_id)

        if operation == "rollback":
            session["messages"] = session["messages"][: index + 1]
            return self._result(self.sessions.persist(session), affected_message_id=message_id)

        if target.role == "system":
            raise ValueError("System messages cannot be regenerated.")
        if target.role == "assistant":
            index = next((i for i in range(index - 1, -1, -1) if session["messages"][i].role == "user"), None)
            if index is None:
                raise ValueError("Assistant message does not have a preceding user message.")

        session["messages"] = session["messages"][: index + 1]
        return await self._generate(session, response_factory, operation)

    def find_index(self, message_id: str, messages: list[Message] | None = None) -> int:
        """Find the index of one message id."""
        for index, message in enumerate(messages or self.get()):
            if message.id == message_id:
                return index
        raise ValueError(f"Message '{message_id}' was not found in this session.")

    def system_message_id(self, session: dict[str, Any] | None = None) -> str | None:
        """Return the current system message id when one exists."""
        message = next((item for item in (session or self.sessions.get())["messages"] if item.role == "system"), None)
        return message.id if message else None

    async def _generate(
        self,
        session: dict[str, Any],
        response_factory: MessageResponseFactory | None,
        operation: str,
    ) -> dict[str, Any]:
        """Generate and append one assistant reply."""
        session = self.sessions.persist(session)
        context = self.build_context(session["messages"])
        if response_factory is None:
            raise ValueError(f"{operation} requires a response_factory.")
        result = response_factory(context)
        if isawaitable(result):
            result = await result
        reply, token_usage = result
        if not reply.strip():
            raise ValueError("Model reply cannot be empty.")

        session = self.sessions.get()
        assistant = Message(role="assistant", content=reply, token_usage=token_usage)
        session["messages"].append(assistant)
        session = self.sessions.persist(session)
        return self._result(
            session,
            context=context,
            reply=reply,
            token_usage=token_usage,
            affected_message_id=assistant.id,
        )

    @staticmethod
    def _result(
        session: dict[str, Any],
        *,
        context: list[dict[str, Any]] | None = None,
        reply: str | None = None,
        token_usage: dict[str, Any] | None = None,
        affected_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Return the shared operation result shape."""
        return {
            "session": session,
            "context": context or [],
            "reply": reply,
            "token_usage": token_usage,
            "affected_message_id": affected_message_id,
        }

    @staticmethod
    def _text(content: str | None, error: str) -> str:
        """Require a non-empty text value."""
        content = (content or "").strip()
        if not content:
            raise ValueError(error)
        return content

    @staticmethod
    def _set_system(session: dict[str, Any], content: str | None) -> dict[str, Any]:
        """Create, update, or clear the system prompt message."""
        content = (content or "").strip()
        current = next((message for message in session["messages"] if message.role == "system"), None)
        others = [message for message in session["messages"] if message.role != "system"]
        if not content:
            session["messages"] = others
            return session
        system = current.model_copy(deep=True) if current else Message(role="system", content=content)
        system.content = content
        session["messages"] = [system, *others]
        return session
