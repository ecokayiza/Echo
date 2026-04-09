import json
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from eco_rag.chat import ChatService
from eco_rag.chat.registry import ChatModelSettings
from eco_rag.config import Config
from eco_rag.workflow import WorkflowStatus, WorkflowStep

WEB_DIR = Config.ROOT_DIR / "apps" / "web"
WEB_DIST_DIR = WEB_DIR / "dist"
DEFAULT_SYSTEM_PROMPT = (
    "You are the chat assistant for Eco_RAG. "
    "Be clear, grounded, and concise. If you are unsure, say so."
)


class SessionSummaryResponse(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0
    preview: str = ""
    token_usage: dict[str, Any] = Field(default_factory=dict)
    total_tokens: int = 0


class SessionStateResponse(BaseModel):
    session: SessionSummaryResponse
    messages: list[dict[str, Any]]


class CreateSessionRequest(BaseModel):
    title: str | None = None
    session_id: str | None = None


class UpdateSessionRequest(BaseModel):
    title: str = Field(min_length=1)


class UpdateSystemPromptRequest(BaseModel):
    content: str | None = None


class ChatModelSettingsRequest(BaseModel):
    provider: str = "openai_compatible"
    model: str | None = Config.MODEL
    api_key: str | None = None
    base_url: str | None = Config.BASE_URL
    temperature: float = 1.0

    def to_settings(self) -> ChatModelSettings:
        return ChatModelSettings(
            provider=self.provider,
            model=self.model,
            api_key=self.api_key or Config.API_KEY,
            base_url=self.base_url,
            temperature=self.temperature,
        )


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    system_prompt: str | None = None
    settings: ChatModelSettingsRequest | None = None


class UpdateMessageRequest(BaseModel):
    content: str = Field(min_length=1)


class RegenerateMessageRequest(BaseModel):
    settings: ChatModelSettingsRequest | None = None


def to_sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def create_app(chat_service: ChatService | None = None):
    app = FastAPI(
        title="Eco_RAG API",
        version="0.1.0",
        description="Backend entrypoint for the Eco_RAG desktop and web clients.",
    )
    service = chat_service or ChatService()

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/ui/")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "model": Config.MODEL}

    @app.get("/api/meta")
    def meta():
        return {
            "workflow_statuses": [status.value for status in WorkflowStatus],
            "workflow_steps": [step.value for step in WorkflowStep],
            "default_system_prompt": DEFAULT_SYSTEM_PROMPT,
            "default_chat_settings": ChatModelSettingsRequest().model_dump(),
        }

    @app.get("/api/sessions", response_model=list[SessionSummaryResponse])
    def list_sessions():
        return [SessionSummaryResponse(**session) for session in service.list_sessions()]

    @app.post("/api/sessions", response_model=SessionSummaryResponse)
    def create_session(payload: CreateSessionRequest | None = None):
        request = payload or CreateSessionRequest()
        session = service.create_session(
            session_id=request.session_id or str(uuid4()),
            title=request.title,
        )
        return SessionSummaryResponse(**session)

    @app.get("/api/sessions/{session_id}", response_model=SessionStateResponse)
    def get_session(session_id: str):
        state = service.get_session_state(session_id)
        return SessionStateResponse(**state.to_dict())

    @app.patch("/api/sessions/{session_id}", response_model=SessionSummaryResponse)
    def update_session(session_id: str, payload: UpdateSessionRequest):
        try:
            session = service.update_session_title(session_id, payload.title)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return SessionSummaryResponse(**session)

    @app.patch("/api/sessions/{session_id}/system-prompt", response_model=SessionStateResponse)
    async def update_system_prompt(session_id: str, payload: UpdateSystemPromptRequest):
        try:
            state = await service.update_system_prompt(session_id, payload.content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return SessionStateResponse(**state.to_dict())

    @app.delete("/api/sessions/{session_id}")
    def delete_session(session_id: str):
        service.delete_session(session_id)
        return {"session_id": session_id, "deleted": True}

    @app.post("/api/sessions/{session_id}/messages/stream")
    async def stream_message(session_id: str, payload: SendMessageRequest):
        async def event_stream():
            try:
                async for item in service.stream_message(
                    message=payload.message,
                    session_id=session_id,
                    system_prompt=payload.system_prompt,
                    settings=payload.settings.to_settings() if payload.settings else None,
                ):
                    yield to_sse(item["event"], item["data"])
            except ValueError as exc:
                yield to_sse("error", {"detail": str(exc)})
            except Exception as exc:
                yield to_sse("error", {"detail": f"Chat request failed: {exc}"})

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.patch("/api/sessions/{session_id}/messages/{message_id}", response_model=SessionStateResponse)
    async def update_message(session_id: str, message_id: str, payload: UpdateMessageRequest):
        try:
            state = await service.update_message(session_id, message_id, payload.content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return SessionStateResponse(**state.to_dict())

    @app.delete("/api/sessions/{session_id}/messages/{message_id}", response_model=SessionStateResponse)
    async def delete_message(session_id: str, message_id: str):
        try:
            state = await service.delete_message(session_id, message_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return SessionStateResponse(**state.to_dict())

    @app.post("/api/sessions/{session_id}/messages/{message_id}/rollback", response_model=SessionStateResponse)
    async def rollback_message(session_id: str, message_id: str):
        try:
            state = await service.rollback_message(session_id, message_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return SessionStateResponse(**state.to_dict())

    @app.post("/api/sessions/{session_id}/messages/{message_id}/regenerate/stream")
    async def stream_regenerate_message(
        session_id: str,
        message_id: str,
        payload: RegenerateMessageRequest | None = None,
    ):
        async def event_stream():
            try:
                async for item in service.stream_regenerate_message(
                    session_id,
                    message_id,
                    settings=payload.settings.to_settings() if payload and payload.settings else None,
                ):
                    yield to_sse(item["event"], item["data"])
            except ValueError as exc:
                yield to_sse("error", {"detail": str(exc)})
            except Exception as exc:
                yield to_sse("error", {"detail": f"Chat request failed: {exc}"})

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    if WEB_DIST_DIR.exists():
        app.mount("/ui", StaticFiles(directory=str(WEB_DIST_DIR), html=True), name="web")

    return app


app = create_app()
