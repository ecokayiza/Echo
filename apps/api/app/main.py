import json
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from eco_rag.chat import ChatService
from eco_rag.chat.registry import (
    ChatModelSettings,
    EmbeddingModelSettings,
    ModelSettingsDocument,
    get_active_chat_model_settings,
    load_model_settings_document,
    normalize_chat_model_settings,
    normalize_embedding_model_settings,
    normalize_model_settings_document,
    save_model_settings_document,
)
from eco_rag.config import Config
from eco_rag.indexing import (
    VectorDatabase,
    create_database_settings,
    delete_database_settings,
    ensure_database_settings_document,
    list_database_settings,
    rename_database_settings,
    resolve_database_embedding_settings,
    select_database_settings,
)
from eco_rag.workflow import WorkflowStatus, WorkflowStep
from eco_rag.workflow.prompts import default_system_prompt

WEB_DIR = Config.ROOT_DIR / "apps" / "web"
WEB_DIST_DIR = WEB_DIR / "dist"


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


class DatabaseSummaryResponse(BaseModel):
    id: str
    name: str
    collection_name: str
    embedding_model_name: str
    document_count: int
    created_at: str
    updated_at: str


class DatabaseStateResponse(BaseModel):
    active_database_id: str | None
    databases: list[DatabaseSummaryResponse]


class CreateSessionRequest(BaseModel):
    title: str | None = None
    session_id: str | None = None


class UpdateSessionRequest(BaseModel):
    title: str = Field(min_length=1)


class UpdateSystemPromptRequest(BaseModel):
    content: str | None = None


class CreateDatabaseRequest(BaseModel):
    name: str | None = None
    embedding_model_name: str | None = None


class UpdateDatabaseRequest(BaseModel):
    name: str = Field(min_length=1)


class ChatModelSettingsRequest(BaseModel):
    name: str = "Default Chat Model"
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 1.0
    top_p: float | None = None
    enable_thinking: bool | None = None

    def to_settings(self) -> ChatModelSettings:
        return normalize_chat_model_settings(self.model_dump())

    @classmethod
    def from_settings(cls, settings: ChatModelSettings):
        return cls(**settings.__dict__)


class EmbeddingModelSettingsRequest(BaseModel):
    name: str = "Default Embedding Model"
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None

    def to_settings(self) -> EmbeddingModelSettings:
        return normalize_embedding_model_settings(self.model_dump())

    @classmethod
    def from_settings(cls, settings: EmbeddingModelSettings):
        return cls(**settings.__dict__)


class ModelSettingsDocumentRequest(BaseModel):
    active_chat_model: str | None = None
    active_embedding_model: str | None = None
    chat_models: list[ChatModelSettingsRequest] = Field(default_factory=list)
    embedding_models: list[EmbeddingModelSettingsRequest] = Field(default_factory=list)

    def to_document(self) -> ModelSettingsDocument:
        return normalize_model_settings_document(
            {
                "active_chat_model": self.active_chat_model,
                "active_embedding_model": self.active_embedding_model,
                "chat_models": [item.model_dump() for item in self.chat_models],
                "embedding_models": [item.model_dump() for item in self.embedding_models],
            }
        )

    @classmethod
    def from_document(cls, document: ModelSettingsDocument):
        return cls(
            active_chat_model=document.active_chat_model,
            active_embedding_model=document.active_embedding_model,
            chat_models=[ChatModelSettingsRequest.from_settings(item) for item in document.chat_models],
            embedding_models=[EmbeddingModelSettingsRequest.from_settings(item) for item in document.embedding_models],
        )


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    system_prompt: str | None = None


class UpdateMessageRequest(BaseModel):
    content: str = Field(min_length=1)


def to_sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def create_app(chat_service: ChatService | None = None):
    ensure_database_settings_document()

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
        active_chat_model = get_active_chat_model_settings(required=False)
        return {"status": "ok", "model": active_chat_model.model if active_chat_model else None}

    @app.get("/api/meta")
    def meta():
        prompt = service.default_system_prompt() if hasattr(service, "default_system_prompt") else default_system_prompt()
        return {
            "workflow_statuses": [status.value for status in WorkflowStatus],
            "workflow_steps": [step.value for step in WorkflowStep],
            "default_system_prompt": prompt,
        }

    @app.get("/api/model-settings", response_model=ModelSettingsDocumentRequest)
    def get_model_settings():
        return ModelSettingsDocumentRequest.from_document(load_model_settings_document())

    @app.put("/api/model-settings", response_model=ModelSettingsDocumentRequest)
    def update_model_settings(payload: ModelSettingsDocumentRequest):
        return ModelSettingsDocumentRequest.from_document(save_model_settings_document(payload.to_document()))

    @app.get("/api/databases", response_model=DatabaseStateResponse)
    def list_databases():
        return DatabaseStateResponse(**_database_state_payload())

    @app.post("/api/databases", response_model=DatabaseStateResponse)
    def create_database(payload: CreateDatabaseRequest | None = None):
        request = payload or CreateDatabaseRequest()
        try:
            create_database_settings(name=request.name, embedding_model_name=request.embedding_model_name, select=True)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return DatabaseStateResponse(**_database_state_payload())

    @app.patch("/api/databases/{database_id}", response_model=DatabaseStateResponse)
    def update_database(database_id: str, payload: UpdateDatabaseRequest):
        try:
            rename_database_settings(database_id, payload.name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return DatabaseStateResponse(**_database_state_payload())

    @app.post("/api/databases/{database_id}/select", response_model=DatabaseStateResponse)
    def select_database(database_id: str):
        try:
            select_database_settings(database_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return DatabaseStateResponse(**_database_state_payload())

    @app.delete("/api/databases/{database_id}", response_model=DatabaseStateResponse)
    def delete_database(database_id: str):
        document = list_database_settings()
        database = next((item for item in document.databases if item.id == database_id), None)
        try:
            delete_database_settings(database_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if database is not None:
            try:
                VectorDatabase(collection_name=database.collection_name).delete_collection()
            except Exception:
                pass
        return DatabaseStateResponse(**_database_state_payload())

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
    async def stream_regenerate_message(session_id: str, message_id: str):
        async def event_stream():
            try:
                async for item in service.stream_regenerate_message(session_id, message_id):
                    yield to_sse(item["event"], item["data"])
            except ValueError as exc:
                yield to_sse("error", {"detail": str(exc)})
            except Exception as exc:
                yield to_sse("error", {"detail": f"Chat request failed: {exc}"})

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    if WEB_DIST_DIR.exists():
        app.mount("/ui", StaticFiles(directory=str(WEB_DIST_DIR), html=True), name="web")

    return app


def _database_state_payload() -> dict[str, Any]:
    document = list_database_settings()
    databases = []
    for database in document.databases:
        try:
            count = VectorDatabase(collection_name=database.collection_name).count()
        except Exception:
            count = 0
        try:
            embedding_model_name = resolve_database_embedding_settings(database).name
        except Exception:
            embedding_model_name = database.embedding_model_name
        databases.append(
            {
                "id": database.id,
                "name": database.name,
                "collection_name": database.collection_name,
                "embedding_model_name": embedding_model_name,
                "document_count": count,
                "created_at": database.created_at,
                "updated_at": database.updated_at,
            }
        )
    return {"active_database_id": document.active_database_id, "databases": databases}


app = create_app()
