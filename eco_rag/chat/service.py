from dataclasses import asdict, dataclass
from typing import Any, Callable
from uuid import uuid4

from .chat_model import BaseChatModel, Message
from .context_manager import (
    BaseMemoryPolicy,
    BaseSessionStore,
    Messages,
    Sessions,
    default_session_title,
)
from .registry import ChatModelSettings, build_chat_model


def infer_session_title(message: str) -> str:
    cleaned = " ".join(message.strip().split())
    if not cleaned:
        return default_session_title()
    return cleaned[:48]


@dataclass
class SessionState:
    session: dict[str, Any]
    messages: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChatResult(SessionState):
    reply: str
    token_usage: dict[str, Any] | None = None


class ChatService:
    def __init__(
        self,
        model_factory: Callable[[ChatModelSettings | None], BaseChatModel] = build_chat_model,
        store: BaseSessionStore | None = None,
        policy: BaseMemoryPolicy | None = None,
    ):
        self.model_factory = model_factory
        self.store = store
        self.policy = policy

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions, _ = self._chat("placeholder")
        return [session.to_dict() for session in sessions.list()]

    def create_session(self, session_id: str | None = None, title: str | None = None) -> dict[str, Any]:
        resolved_session_id = session_id or str(uuid4())
        sessions, _ = self._chat(resolved_session_id)
        session = sessions.ensure(title=title or default_session_title())
        return session.to_summary().to_dict()

    def delete_session(self, session_id: str):
        sessions, _ = self._chat(session_id)
        sessions.delete()

    def get_session_state(self, session_id: str) -> SessionState:
        sessions, messages = self._chat(session_id)
        return SessionState(
            session=sessions.summary().to_dict(),
            messages=messages.history(),
        )

    async def send_message(
        self,
        message: str,
        session_id: str,
        system_prompt: str | None = None,
        settings: ChatModelSettings | None = None,
    ) -> ChatResult:
        cleaned_message = message.strip()
        if not cleaned_message:
            raise ValueError("Message cannot be empty.")

        sessions, messages = self._chat(session_id)
        sessions.ensure()
        previous_first_user = self._first_user_message(messages)

        if system_prompt is not None:
            await messages.apply("system_prompt", content=system_prompt)

        result = await messages.apply(
            "send",
            content=cleaned_message,
            response_factory=self._response_factory(settings),
        )
        self._sync_inferred_title(sessions, messages, previous_first_user)

        return ChatResult(
            session=sessions.summary().to_dict(),
            messages=messages.history(),
            reply=result["reply"] or "",
            token_usage=result["token_usage"],
        )

    async def update_message(self, session_id: str, message_id: str, content: str) -> SessionState:
        sessions, messages = self._chat(session_id)
        previous_first_user = self._first_user_message(messages)
        await messages.apply("edit", message_id=message_id, content=content)
        self._sync_inferred_title(sessions, messages, previous_first_user)
        return SessionState(
            session=sessions.summary().to_dict(),
            messages=messages.history(),
        )

    async def delete_message(self, session_id: str, message_id: str) -> SessionState:
        sessions, messages = self._chat(session_id)
        previous_first_user = self._first_user_message(messages)
        await messages.apply("delete", message_id=message_id)
        self._sync_inferred_title(sessions, messages, previous_first_user)
        return SessionState(
            session=sessions.summary().to_dict(),
            messages=messages.history(),
        )

    async def rollback_message(self, session_id: str, message_id: str) -> SessionState:
        sessions, messages = self._chat(session_id)
        previous_first_user = self._first_user_message(messages)
        await messages.apply("rollback", message_id=message_id)
        self._sync_inferred_title(sessions, messages, previous_first_user)
        return SessionState(
            session=sessions.summary().to_dict(),
            messages=messages.history(),
        )

    async def regenerate_message(
        self,
        session_id: str,
        message_id: str,
        settings: ChatModelSettings | None = None,
    ) -> ChatResult:
        sessions, messages = self._chat(session_id)
        previous_first_user = self._first_user_message(messages)
        result = await messages.apply(
            "regenerate",
            message_id=message_id,
            response_factory=self._response_factory(settings),
        )
        self._sync_inferred_title(sessions, messages, previous_first_user)
        return ChatResult(
            session=sessions.summary().to_dict(),
            messages=messages.history(),
            reply=result["reply"] or "",
            token_usage=result["token_usage"],
        )

    def update_session_title(self, session_id: str, title: str) -> dict[str, Any]:
        cleaned = title.strip()
        if not cleaned:
            raise ValueError("Session title cannot be empty.")
        sessions, _ = self._chat(session_id)
        sessions.ensure()
        sessions.set_title(cleaned)
        return sessions.summary().to_dict()

    def _chat(self, session_id: str) -> tuple[Sessions, Messages]:
        sessions = Sessions(session_id=session_id, store=self.store)
        messages = Messages(sessions=sessions, policy=self.policy)
        return sessions, messages

    def _response_factory(self, settings: ChatModelSettings | None):
        model = self.model_factory(settings)

        async def generate(context: list[dict[str, Any]]):
            response = await model.generate_response(context)
            return response.content, response.token_usage

        return generate

    @staticmethod
    def _first_user_message(messages: Messages) -> Message | None:
        return next((message for message in messages.get() if message.role == "user"), None)

    def _sync_inferred_title(
        self,
        sessions: Sessions,
        messages: Messages,
        previous_first_user: Message | None,
    ):
        current_title = sessions.summary().title
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
