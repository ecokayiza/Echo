import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from inspect import isawaitable
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable

from ..config import Config
from .chat_model import Message


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_session_title() -> str:
    return "New Session"


@dataclass
class ChatSessionSummary:
    session_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0
    preview: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": self.message_count,
            "preview": self.preview,
        }


@dataclass
class ChatSession:
    session_id: str
    title: str = field(default_factory=default_session_title)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    messages: list[Message] = field(default_factory=list)

    def clone(self) -> "ChatSession":
        return ChatSession(
            session_id=self.session_id,
            title=self.title,
            created_at=self.created_at,
            updated_at=self.updated_at,
            messages=[message.model_copy(deep=True) for message in self.messages],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [message.model_dump(exclude_none=True) for message in self.messages],
        }

    def to_summary(self) -> ChatSessionSummary:
        preview_source = ""
        for message in reversed(self.messages):
            if message.role != "system" and message.content.strip():
                preview_source = message.content.strip()
                break

        return ChatSessionSummary(
            session_id=self.session_id,
            title=self.title,
            created_at=self.created_at,
            updated_at=self.updated_at,
            message_count=len(self.messages),
            preview=preview_source[:80],
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any], default_session_id: str) -> "ChatSession":
        return cls(
            session_id=payload.get("session_id", default_session_id),
            title=payload.get("title", default_session_title()),
            created_at=payload.get("created_at") or utc_now(),
            updated_at=payload.get("updated_at") or utc_now(),
            messages=[Message(**message) for message in payload.get("messages", [])],
        )


class BaseSessionStore(ABC):
    @abstractmethod
    def create_session(self, session_id: str, title: str | None = None) -> ChatSession:
        pass

    @abstractmethod
    def load_session(self, session_id: str) -> ChatSession:
        pass

    @abstractmethod
    def save_session(self, session: ChatSession):
        pass

    @abstractmethod
    def list_sessions(self) -> list[ChatSessionSummary]:
        pass

    @abstractmethod
    def delete_session(self, session_id: str):
        pass


class InMemorySessionStore(BaseSessionStore):
    def __init__(self):
        self._sessions: dict[str, ChatSession] = {}

    def create_session(self, session_id: str, title: str | None = None) -> ChatSession:
        session = ChatSession(session_id=session_id, title=title or default_session_title())
        self._sessions[session_id] = session.clone()
        return session.clone()

    def load_session(self, session_id: str) -> ChatSession:
        session = self._sessions.get(session_id)
        if session is None:
            return ChatSession(session_id=session_id)
        return session.clone()

    def save_session(self, session: ChatSession):
        session.updated_at = utc_now()
        self._sessions[session.session_id] = session.clone()

    def list_sessions(self) -> list[ChatSessionSummary]:
        sessions = [session.to_summary() for session in self._sessions.values()]
        return sorted(sessions, key=lambda item: item.updated_at, reverse=True)

    def delete_session(self, session_id: str):
        self._sessions.pop(session_id, None)


class FileSessionStore(BaseSessionStore):
    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir or Config.CHAT_MEMORY_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_session(self, session_id: str, title: str | None = None) -> ChatSession:
        session = ChatSession(session_id=session_id, title=title or default_session_title())
        self.save_session(session)
        return session.clone()

    def load_session(self, session_id: str) -> ChatSession:
        session_file = self._session_file(session_id)
        if not session_file.exists():
            return ChatSession(session_id=session_id)

        payload = json.loads(session_file.read_text(encoding="utf-8"))
        return ChatSession.from_dict(payload, default_session_id=session_id)

    def save_session(self, session: ChatSession):
        session.updated_at = utc_now()
        session_file = self._session_file(session.session_id)
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text(
            json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_sessions(self) -> list[ChatSessionSummary]:
        sessions = []
        for path in self.base_dir.glob("*.json"):
            if path.name.startswith("."):
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            sessions.append(ChatSession.from_dict(payload, default_session_id=path.stem).to_summary())
        return sorted(sessions, key=lambda item: item.updated_at, reverse=True)

    def delete_session(self, session_id: str):
        session_file = self._session_file(session_id)
        if session_file.exists():
            session_file.unlink()

    def _session_file(self, session_id: str) -> Path:
        safe_prefix = re.sub(r"[^A-Za-z0-9_.-]+", "_", session_id).strip("._-") or "session"
        digest = hashlib.sha1(session_id.encode("utf-8")).hexdigest()[:10]
        return self.base_dir / f"{safe_prefix}-{digest}.json"


class BaseMemoryPolicy(ABC):
    @abstractmethod
    def select_messages(self, messages: list[Message]) -> list[Message]:
        pass


class SlidingWindowMemoryPolicy(BaseMemoryPolicy):
    def __init__(self, max_messages: int = 12, preserve_system_messages: bool = True):
        if max_messages < 0:
            raise ValueError("max_messages must be non-negative.")
        self.max_messages = max_messages
        self.preserve_system_messages = preserve_system_messages

    def select_messages(self, messages: list[Message]) -> list[Message]:
        system_messages = [message.model_copy(deep=True) for message in messages if message.role == "system"]
        non_system_messages = [message.model_copy(deep=True) for message in messages if message.role != "system"]

        if self.max_messages == 0:
            return system_messages if self.preserve_system_messages else []

        selected = non_system_messages[-self.max_messages:]
        return system_messages + selected if self.preserve_system_messages else selected


MessageResponseFactory = Callable[
    [list[dict[str, Any]]],
    Awaitable[tuple[str, dict[str, Any] | None]] | tuple[str, dict[str, Any] | None],
]


class Sessions:
    def __init__(self, session_id: str, store: BaseSessionStore | None = None):
        self.session_id = session_id
        self.store = store or FileSessionStore()
        self.local_session = self.refresh()

    def refresh(self) -> ChatSession:
        self.local_session = self.store.load_session(self.session_id)
        return self.local_session.clone()

    def exists(self) -> bool:
        return any(item.session_id == self.session_id for item in self.store.list_sessions())

    def ensure(self, title: str | None = None) -> ChatSession:
        if self.exists():
            session = self.refresh()
        else:
            session = self.store.create_session(self.session_id, title)
            self.local_session = session.clone()

        cleaned_title = (title or "").strip()
        if cleaned_title and session.title == default_session_title():
            session.title = cleaned_title
            return self.persist(session)
        return session.clone()

    def get(self) -> ChatSession:
        return self.refresh()

    def summary(self) -> ChatSessionSummary:
        return self.get().to_summary()

    def list(self) -> list[ChatSessionSummary]:
        return self.store.list_sessions()

    def set_title(self, title: str):
        session = self.get()
        session.title = title.strip() or default_session_title()
        self.persist(session)

    def persist(self, session: ChatSession) -> ChatSession:
        self.store.save_session(session)
        return self.refresh()

    def delete(self):
        self.store.delete_session(self.session_id)
        self.local_session = ChatSession(session_id=self.session_id)


class Messages:
    _OPS = {
        "send",
        "edit",
        "delete",
        "rollback",
        "regenerate",
        "system_prompt",
    }

    def __init__(self, sessions: Sessions, policy: BaseMemoryPolicy | None = None):
        self.sessions = sessions
        self.policy = policy or SlidingWindowMemoryPolicy()

    def get(self) -> list[Message]:
        return self.sessions.get().messages

    def history(self) -> list[dict[str, Any]]:
        return [message.model_dump(exclude_none=True) for message in self.get()]

    def build_context(self, messages: list[Message] | None = None) -> list[dict[str, Any]]:
        selected = self.policy.select_messages(messages or self.get())
        return [message.to_llm_message() for message in selected]

    def append(self, role: str, content: str, tool_calls: list[dict[str, Any]] | None = None) -> Message:
        session = self.sessions.get()
        message = Message(
            role=role,
            content=self._require_content(content, "Message content cannot be empty."),
            tool_calls=tool_calls,
        )
        session.messages.append(message)
        self.sessions.persist(session)
        return message.model_copy(deep=True)

    def replace(self, messages: Iterable[Message | dict]) -> ChatSession:
        session = self.sessions.get()
        session.messages = [self._coerce_message(message) for message in messages]
        return self.sessions.persist(session)

    def clear(self) -> ChatSession:
        session = self.sessions.get()
        session.messages = []
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
        operation = operation.strip().lower()
        if operation not in self._OPS:
            raise ValueError(f"Unsupported message operation: {operation}")

        session = self.sessions.ensure()

        if operation == "system_prompt":
            updated = self._apply_system_prompt(session, content, truncate_following=True)
            persisted = self.sessions.persist(updated)
            return self._result(persisted, affected_message_id=self.system_message_id(persisted))

        if operation == "send":
            cleaned = self._require_content(content, "Message content cannot be empty.")
            session.messages.append(Message(role="user", content=cleaned, tool_calls=tool_calls))
            persisted = self.sessions.persist(session)
            context = self.build_context(persisted.messages)
            reply, token_usage = await self._resolve_response(response_factory, context, operation)
            latest = self.sessions.get()
            assistant_message = Message(role="assistant", content=reply)
            latest.messages.append(assistant_message)
            finalized = self.sessions.persist(latest)
            return self._result(
                finalized,
                context=context,
                reply=reply,
                token_usage=token_usage,
                affected_message_id=assistant_message.id,
            )

        if message_id is None:
            raise ValueError(f"{operation} requires a message_id.")

        index = self.find_index(message_id, session.messages)
        target = session.messages[index]

        if operation == "edit":
            cleaned = self._require_content(content, "Message content cannot be empty.")
            if target.role == "system":
                updated = self._apply_system_prompt(session, cleaned, truncate_following=True)
                persisted = self.sessions.persist(updated)
                return self._result(persisted, affected_message_id=self.system_message_id(persisted))

            target.content = cleaned
            target.updated_at = utc_now()
            session.messages = session.messages[: index + 1]
            persisted = self.sessions.persist(session)
            return self._result(persisted, affected_message_id=message_id)

        if operation == "delete":
            if target.role == "system":
                updated = self._apply_system_prompt(session, None, truncate_following=True)
                persisted = self.sessions.persist(updated)
                return self._result(persisted)

            session.messages = session.messages[:index]
            persisted = self.sessions.persist(session)
            return self._result(persisted)

        if operation == "rollback":
            session.messages = session.messages[: index + 1]
            persisted = self.sessions.persist(session)
            return self._result(persisted, affected_message_id=message_id)

        if target.role == "system":
            raise ValueError("System messages cannot be regenerated.")

        if target.role == "assistant":
            user_index = next(
                (position for position in range(index - 1, -1, -1) if session.messages[position].role == "user"),
                None,
            )
            if user_index is None:
                raise ValueError("Assistant message does not have a preceding user message.")
        else:
            user_index = index

        session.messages = session.messages[: user_index + 1]
        persisted = self.sessions.persist(session)
        context = self.build_context(persisted.messages)
        reply, token_usage = await self._resolve_response(response_factory, context, operation)
        latest = self.sessions.get()
        assistant_message = Message(role="assistant", content=reply)
        latest.messages.append(assistant_message)
        finalized = self.sessions.persist(latest)
        return self._result(
            finalized,
            context=context,
            reply=reply,
            token_usage=token_usage,
            affected_message_id=assistant_message.id,
        )

    def find_index(self, message_id: str, messages: list[Message] | None = None) -> int:
        pool = messages or self.get()
        for index, message in enumerate(pool):
            if message.id == message_id:
                return index
        raise ValueError(f"Message '{message_id}' was not found in this session.")

    def system_message_id(self, session: ChatSession | None = None) -> str | None:
        current = session or self.sessions.get()
        system_message = next((message for message in current.messages if message.role == "system"), None)
        return system_message.id if system_message else None

    @staticmethod
    async def _resolve_response(
        response_factory: MessageResponseFactory | None,
        context: list[dict[str, Any]],
        operation: str,
    ) -> tuple[str, dict[str, Any] | None]:
        if response_factory is None:
            raise ValueError(f"{operation} requires a response_factory.")

        outcome = response_factory(context)
        if isawaitable(outcome):
            outcome = await outcome

        reply, token_usage = outcome
        if not reply.strip():
            raise ValueError("Model reply cannot be empty.")
        return reply, token_usage

    @staticmethod
    def _result(
        session: ChatSession,
        *,
        context: list[dict[str, Any]] | None = None,
        reply: str | None = None,
        token_usage: dict[str, Any] | None = None,
        affected_message_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "session": session,
            "context": context or [],
            "reply": reply,
            "token_usage": token_usage,
            "affected_message_id": affected_message_id,
        }

    @staticmethod
    def _require_content(content: str | None, error_message: str) -> str:
        cleaned = (content or "").strip()
        if not cleaned:
            raise ValueError(error_message)
        return cleaned

    @staticmethod
    def _coerce_message(message: Message | dict) -> Message:
        if isinstance(message, Message):
            return message
        return Message(**message)

    def _apply_system_prompt(
        self,
        session: ChatSession,
        content: str | None,
        *,
        truncate_following: bool,
    ) -> ChatSession:
        cleaned = (content or "").strip()
        existing = next((message for message in session.messages if message.role == "system"), None)

        if existing is None and not cleaned:
            return session
        if existing and existing.content == cleaned:
            return session

        if cleaned:
            system_message = existing.model_copy(deep=True) if existing else Message(role="system", content=cleaned)
            system_message.content = cleaned
            system_message.updated_at = utc_now()
            if truncate_following:
                session.messages = [system_message]
            else:
                remaining = [message for message in session.messages if message.role != "system"]
                session.messages = [system_message, *remaining]
            return session

        session.messages = [] if truncate_following else [message for message in session.messages if message.role != "system"]
        return session
