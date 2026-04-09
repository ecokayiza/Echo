from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable
from uuid import uuid4

from .chat_model import BaseChatModel, Message
from .context_manager import Messages, Sessions, default_session_title
from .registry import ChatModelSettings, build_chat_model

if TYPE_CHECKING:
    from ..workflow.service import WorkflowService


def infer_session_title(message: str) -> str:
    """Turn the first user message into a short session title."""
    cleaned = " ".join(message.strip().split())
    if not cleaned:
        return default_session_title()
    return cleaned[:48]


@dataclass
class SessionState:
    """Return the current session summary plus message history."""

    session: dict[str, Any]
    messages: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Convert the dataclass into a plain dictionary."""
        return asdict(self)


@dataclass
class ChatResult(SessionState):
    """Return one chat mutation plus the newest reply payload."""

    reply: str
    token_usage: dict[str, Any] | None = None
    workflow: dict[str, Any] | None = None


class ChatService:
    """Coordinate sessions, messages, and workflow-backed chat generation."""

    def __init__(
        self,
        model_factory: Callable[[ChatModelSettings | None], BaseChatModel] = build_chat_model,
        *,
        storage: dict[str, dict[str, Any]] | None = None,
        base_dir: str | Path | None = None,
        tool_runner: Callable[[str], Any] | None = None,
        workflow_factory: Callable[[], WorkflowService] | None = None,
        max_context_messages: int = 12,
        preserve_system_messages: bool = True,
    ):
        self.model_factory = model_factory
        self.storage = storage
        self.base_dir = base_dir
        self.tool_runner = tool_runner
        self.workflow_factory = workflow_factory
        self.max_context_messages = max_context_messages
        self.preserve_system_messages = preserve_system_messages

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all saved sessions."""
        sessions, _ = self._chat("placeholder")
        return sessions.list()

    def create_session(self, session_id: str | None = None, title: str | None = None) -> dict[str, Any]:
        """Create one session and return its summary."""
        resolved_session_id = session_id or str(uuid4())
        sessions, _ = self._chat(resolved_session_id)
        sessions.ensure(title=title or default_session_title())
        return sessions.summary()

    def delete_session(self, session_id: str):
        """Delete one session."""
        sessions, _ = self._chat(session_id)
        sessions.delete()

    def get_session_state(self, session_id: str) -> SessionState:
        """Return one session with its full message history."""
        sessions, messages = self._chat(session_id)
        return SessionState(session=sessions.summary(), messages=messages.history())

    async def stream_message(
        self,
        message: str,
        session_id: str,
        system_prompt: str | None = None,
        settings: ChatModelSettings | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream one assistant reply event by event."""
        cleaned_message = message.strip()
        if not cleaned_message:
            raise ValueError("Message cannot be empty.")

        sessions, messages = self._chat(session_id)
        sessions.ensure()
        previous_first_user = self._first_user_message(messages)

        if system_prompt is not None:
            await messages.apply("system_prompt", content=system_prompt)

        messages.append("user", cleaned_message)
        workflow: dict[str, Any] | None = None

        async for item in self._workflow().stream_chat(
            cleaned_message,
            context=messages.build_context(),
            settings=settings,
        ):
            if item["event"] == "chunk":
                yield item
                continue

            workflow = item["data"]
            if item["event"] == "state":
                yield {"event": "workflow", "data": workflow}

        if workflow is None:
            raise ValueError("Workflow stream ended without a final state.")

        reply = self._reply(workflow["answer"])
        messages.append("assistant", reply, token_usage=workflow["token_usage"])
        self._sync_inferred_title(sessions, messages, previous_first_user)

        result = ChatResult(
            session=sessions.summary(),
            messages=messages.history(),
            reply=reply,
            token_usage=workflow["token_usage"],
            workflow=workflow,
        )
        yield {"event": "done", "data": result.to_dict()}

    async def update_system_prompt(self, session_id: str, content: str | None) -> SessionState:
        """Create, replace, or clear the system prompt."""
        sessions, messages = self._chat(session_id)
        sessions.ensure()
        await messages.apply("system_prompt", content=content)
        return SessionState(session=sessions.summary(), messages=messages.history())

    async def update_message(self, session_id: str, message_id: str, content: str) -> SessionState:
        """Edit one existing message."""
        sessions, messages = self._chat(session_id)
        previous_first_user = self._first_user_message(messages)
        await messages.apply("edit", message_id=message_id, content=content)
        self._sync_inferred_title(sessions, messages, previous_first_user)
        return SessionState(session=sessions.summary(), messages=messages.history())

    async def delete_message(self, session_id: str, message_id: str) -> SessionState:
        """Delete one message branch."""
        sessions, messages = self._chat(session_id)
        previous_first_user = self._first_user_message(messages)
        await messages.apply("delete", message_id=message_id)
        self._sync_inferred_title(sessions, messages, previous_first_user)
        return SessionState(session=sessions.summary(), messages=messages.history())

    async def rollback_message(self, session_id: str, message_id: str) -> SessionState:
        """Trim the conversation after one message."""
        sessions, messages = self._chat(session_id)
        previous_first_user = self._first_user_message(messages)
        await messages.apply("rollback", message_id=message_id)
        self._sync_inferred_title(sessions, messages, previous_first_user)
        return SessionState(session=sessions.summary(), messages=messages.history())

    async def stream_regenerate_message(
        self,
        session_id: str,
        message_id: str,
        settings: ChatModelSettings | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream a regenerated assistant reply."""
        sessions, messages = self._chat(session_id)
        previous_first_user = self._first_user_message(messages)
        question = self._prepare_regeneration(messages, message_id)
        workflow: dict[str, Any] | None = None

        async for item in self._workflow().stream_chat(
            question,
            context=messages.build_context(),
            settings=settings,
        ):
            if item["event"] == "chunk":
                yield item
                continue

            workflow = item["data"]
            if item["event"] == "state":
                yield {"event": "workflow", "data": workflow}

        if workflow is None:
            raise ValueError("Workflow stream ended without a final state.")

        reply = self._reply(workflow["answer"])
        messages.append("assistant", reply, token_usage=workflow["token_usage"])
        self._sync_inferred_title(sessions, messages, previous_first_user)

        result = ChatResult(
            session=sessions.summary(),
            messages=messages.history(),
            reply=reply,
            token_usage=workflow["token_usage"],
            workflow=workflow,
        )
        yield {"event": "done", "data": result.to_dict()}

    def update_session_title(self, session_id: str, title: str) -> dict[str, Any]:
        """Rename one session."""
        cleaned = title.strip()
        if not cleaned:
            raise ValueError("Session title cannot be empty.")
        sessions, _ = self._chat(session_id)
        sessions.ensure()
        sessions.set_title(cleaned)
        return sessions.summary()

    def _chat(self, session_id: str) -> tuple[Sessions, Messages]:
        """Build the session and message managers for one session id."""
        sessions = Sessions(session_id=session_id, storage=self.storage, base_dir=self.base_dir)
        messages = Messages(
            sessions=sessions,
            max_context_messages=self.max_context_messages,
            preserve_system_messages=self.preserve_system_messages,
        )
        return sessions, messages

    def _workflow(self) -> WorkflowService:
        """Build the workflow entry used by chat generation."""
        from ..workflow.service import WorkflowService

        if self.workflow_factory is not None:
            return self.workflow_factory()
        return WorkflowService(model_factory=self.model_factory, tool_runner=self.tool_runner)

    @staticmethod
    def _first_user_message(messages: Messages) -> Message | None:
        """Return the first user message in a session."""
        return next((message for message in messages.get() if message.role == "user"), None)

    @staticmethod
    def _reply(content: str) -> str:
        """Require a non-empty assistant reply."""
        reply = content.strip()
        if not reply:
            raise ValueError("Model reply cannot be empty.")
        return reply

    def _prepare_regeneration(self, messages: Messages, message_id: str) -> str:
        """Trim one branch and return the user query that should be rerun."""
        current_messages = messages.get()
        index = messages.find_index(message_id, current_messages)
        target = current_messages[index]
        if target.role == "system":
            raise ValueError("System messages cannot be regenerated.")
        if target.role == "assistant":
            index = next((i for i in range(index - 1, -1, -1) if current_messages[i].role == "user"), None)
            if index is None:
                raise ValueError("Assistant message does not have a preceding user message.")

        session = messages.sessions.get()
        session["messages"] = session["messages"][: index + 1]
        messages.sessions.persist(session)
        return current_messages[index].content

    def _sync_inferred_title(
        self,
        sessions: Sessions,
        messages: Messages,
        previous_first_user: Message | None,
    ):
        """Keep auto-generated titles in sync with the first user turn."""
        current_title = sessions.summary()["title"]
        tracked_titles = {default_session_title()}
        if previous_first_user is not None:
            tracked_titles.add(infer_session_title(previous_first_user.content))

        if current_title not in tracked_titles:
            return

        current_first_user = self._first_user_message(messages)
        inferred_title = (
            infer_session_title(current_first_user.content)
            if current_first_user is not None
            else default_session_title()
        )
        if current_title != inferred_title:
            sessions.set_title(inferred_title)
