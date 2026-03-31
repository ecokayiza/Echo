import hashlib
import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable

from ..config import Config
from .chat_model import Message


class BaseMemoryStore(ABC):
    """
    Persists raw chat messages for a session.
    """

    @abstractmethod
    def append(self, session_id: str, message: Message):
        pass

    @abstractmethod
    def extend(self, session_id: str, messages: Iterable[Message]):
        pass

    @abstractmethod
    def get_messages(self, session_id: str) -> list[Message]:
        pass

    @abstractmethod
    def clear(self, session_id: str):
        pass


class InMemoryMessageStore(BaseMemoryStore):
    """
    Simple in-process message storage keyed by session id.
    """

    def __init__(self):
        self._sessions: dict[str, list[Message]] = {}

    def append(self, session_id: str, message: Message):
        self._sessions.setdefault(session_id, []).append(message.model_copy(deep=True))

    def extend(self, session_id: str, messages: Iterable[Message]):
        for message in messages:
            self.append(session_id, message)

    def get_messages(self, session_id: str) -> list[Message]:
        return [message.model_copy(deep=True) for message in self._sessions.get(session_id, [])]

    def clear(self, session_id: str):
        self._sessions.pop(session_id, None)


class FileMessageStore(BaseMemoryStore):
    """
    Stores chat sessions as JSON files under the top-level memory directory.
    """

    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir or Config.CHAT_MEMORY_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def append(self, session_id: str, message: Message):
        messages = self.get_messages(session_id)
        messages.append(message.model_copy(deep=True))
        self._write_messages(session_id, messages)

    def extend(self, session_id: str, messages: Iterable[Message]):
        existing = self.get_messages(session_id)
        existing.extend(message.model_copy(deep=True) for message in messages)
        self._write_messages(session_id, existing)

    def get_messages(self, session_id: str) -> list[Message]:
        session_file = self._session_file(session_id)
        if not session_file.exists():
            return []

        payload = json.loads(session_file.read_text(encoding="utf-8"))
        return [Message(**message) for message in payload.get("messages", [])]

    def clear(self, session_id: str):
        session_file = self._session_file(session_id)
        if session_file.exists():
            session_file.unlink()

    def _write_messages(self, session_id: str, messages: list[Message]):
        session_file = self._session_file(session_id)
        session_file.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "session_id": session_id,
            "messages": [message.model_dump(exclude_none=True) for message in messages],
        }
        session_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _session_file(self, session_id: str) -> Path:
        safe_prefix = re.sub(r"[^A-Za-z0-9_.-]+", "_", session_id).strip("._-") or "session"
        digest = hashlib.sha1(session_id.encode("utf-8")).hexdigest()[:10]
        return self.base_dir / f"{safe_prefix}-{digest}.json"


class BaseMemoryPolicy(ABC):
    """
    Selects which stored messages should be injected into the next model call.
    """

    @abstractmethod
    def select_messages(self, messages: list[Message]) -> list[Message]:
        pass


class SlidingWindowMemoryPolicy(BaseMemoryPolicy):
    """
    Keeps a configurable tail of the conversation while preserving system prompts.
    """

    def __init__(self, max_messages: int = 12, preserve_system_messages: bool = True):
        if max_messages < 0:
            raise ValueError("max_messages must be non-negative.")

        self.max_messages = max_messages
        self.preserve_system_messages = preserve_system_messages

    def select_messages(self, messages: list[Message]) -> list[Message]:
        if self.max_messages == 0:
            return self._clone(messages if self.preserve_system_messages else [])

        system_messages = [message for message in messages if message.role == "system"]
        non_system_messages = [message for message in messages if message.role != "system"]
        selected = non_system_messages[-self.max_messages:]

        if self.preserve_system_messages:
            return self._clone(system_messages + selected)
        return self._clone(selected)

    @staticmethod
    def _clone(messages: list[Message]) -> list[Message]:
        return [message.model_copy(deep=True) for message in messages]


class ContextManager:
    """
    Coordinates chat memory for a single session.

    The manager is intentionally small: storage and selection policy are both
    injectable so we can swap in summaries, database-backed memory, or hybrid
    memory without changing callers.
    """

    def __init__(
        self,
        session_id: str = "default",
        store: BaseMemoryStore | None = None,
        policy: BaseMemoryPolicy | None = None,
    ):
        self.session_id = session_id
        self.store = store or FileMessageStore()
        self.policy = policy or SlidingWindowMemoryPolicy()

    def append(self, role: str, content: str, tool_calls: list[dict[str, Any]] | None = None) -> Message:
        message = Message(role=role, content=content, tool_calls=tool_calls)
        self.store.append(self.session_id, message)
        return message

    def extend(self, messages: Iterable[Message | dict[str, Any]]):
        normalized = [self._coerce_message(message) for message in messages]
        self.store.extend(self.session_id, normalized)

    def get_messages(self) -> list[Message]:
        return self.store.get_messages(self.session_id)

    def get_history(self) -> list[dict[str, Any]]:
        return [message.model_dump(exclude_none=True) for message in self.get_messages()]

    def build_context(self) -> list[dict[str, Any]]:
        messages = self.policy.select_messages(self.get_messages())
        return [message.model_dump(exclude_none=True) for message in messages]

    def clear(self):
        self.store.clear(self.session_id)

    def fork(self, session_id: str) -> "ContextManager":
        return ContextManager(session_id=session_id, store=self.store, policy=self.policy)

    @staticmethod
    def _coerce_message(message: Message | dict[str, Any]) -> Message:
        if isinstance(message, Message):
            return message
        return Message(**message)
