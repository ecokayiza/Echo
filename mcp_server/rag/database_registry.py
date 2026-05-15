from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from echo.chat.registry import (
    embedding_model_key,
    get_active_embedding_model_settings,
    normalize_embedding_model_settings,
    resolve_embedding_model_settings,
)
from echo.settings import Config
from .vector_backends import DEFAULT_VECTOR_BACKEND, normalize_vector_backend


@dataclass(frozen=True)
class DatabaseSettings:
    """Store one vector database plus its paired embedding model."""

    id: str
    name: str
    collection_name: str
    backend: str
    embedding_model_name: str
    embedding_model_key: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DatabaseSettingsDocument:
    """Store all configured vector databases plus the active selection."""

    active_database_id: str | None = None
    databases: list[DatabaseSettings] = field(default_factory=list)


def normalize_database_settings(settings: DatabaseSettings | dict | None = None) -> DatabaseSettings:
    """Normalize one database settings payload."""
    payload = settings if isinstance(settings, dict) else asdict(settings or _default_database_settings())
    name = _trim(payload.get("name")) or "Default Database"
    embedding_name = _trim(payload.get("embedding_model_name")) or get_active_embedding_model_settings().name
    embedding = resolve_embedding_model_settings(name=embedding_name, required=False) or normalize_embedding_model_settings(
        get_active_embedding_model_settings()
    )
    collection_name = _trim(payload.get("collection_name")) or _collection_name(name, str(payload.get("id") or ""))
    timestamp = _trim(payload.get("created_at")) or _utc_now()
    return DatabaseSettings(
        id=_trim(payload.get("id")) or str(uuid4()),
        name=name,
        collection_name=collection_name,
        backend=normalize_vector_backend(payload.get("backend")),
        embedding_model_name=embedding.name,
        embedding_model_key=_trim(payload.get("embedding_model_key")) or embedding_model_key(embedding),
        created_at=timestamp,
        updated_at=_trim(payload.get("updated_at")) or timestamp,
    )


def normalize_database_settings_document(document: DatabaseSettingsDocument | dict | None = None) -> DatabaseSettingsDocument:
    """Normalize the database settings document and guarantee one usable default."""
    payload = document if isinstance(document, dict) else asdict(document or DatabaseSettingsDocument())
    raw_databases = payload.get("databases")
    if not isinstance(raw_databases, list):
        raw_databases = []
    databases = [normalize_database_settings(item) for item in raw_databases if isinstance(item, (dict, DatabaseSettings))]
    if not databases:
        active_database_id = None
    else:
        active_database_id = _trim(payload.get("active_database_id"))
        if not any(database.id == active_database_id for database in databases):
            active_database_id = databases[0].id
    return DatabaseSettingsDocument(active_database_id=active_database_id, databases=databases)


def load_database_settings_document() -> DatabaseSettingsDocument:
    """Load database settings from disk or create the default document."""
    path = Config.DATABASES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return save_database_settings_document(DatabaseSettingsDocument())
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Database settings file '{path.name}' must contain a JSON object.")
    return normalize_database_settings_document(payload)


def save_database_settings_document(document: DatabaseSettingsDocument | dict) -> DatabaseSettingsDocument:
    """Persist the database settings document."""
    resolved = normalize_database_settings_document(document)
    Config.DATABASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    Config.DATABASES_PATH.write_text(json.dumps(asdict(resolved), ensure_ascii=False, indent=2), encoding="utf-8")
    return resolved


def ensure_database_settings_document() -> DatabaseSettingsDocument:
    """Ensure the runtime has at least one database configured."""
    return save_database_settings_document(load_database_settings_document())


def list_database_settings() -> DatabaseSettingsDocument:
    """Return the normalized database settings document."""
    return load_database_settings_document()


def get_active_database_settings(*, required: bool = True) -> DatabaseSettings | None:
    """Resolve the active database selection."""
    document = load_database_settings_document()
    resolved = next((item for item in document.databases if item.id == document.active_database_id), None)
    if resolved is not None or not required:
        return resolved
    raise ValueError("No active database configured.")


def create_database_settings(
    *,
    name: str | None = None,
    embedding_model_name: str | None = None,
    backend: str | None = None,
    select: bool = True,
) -> DatabaseSettingsDocument:
    """Create one new database paired to an embedding model."""
    resolved_backend = normalize_vector_backend(backend)
    embedding = (
        resolve_embedding_model_settings(name=embedding_model_name, required=False)
        if embedding_model_name
        else get_active_embedding_model_settings()
    )
    if embedding is None:
        raise ValueError("No embedding model is available for the new database.")
    database = normalize_database_settings(
        {
            "id": str(uuid4()),
            "name": name or _default_name(embedding.name),
            "embedding_model_name": embedding.name,
            "embedding_model_key": embedding_model_key(embedding),
            "backend": resolved_backend,
            "collection_name": _collection_name(name or _default_name(embedding.name), str(uuid4())[:8]),
        }
    )
    document = load_database_settings_document()
    resolved = DatabaseSettingsDocument(
        active_database_id=database.id if select else document.active_database_id,
        databases=[*document.databases, database],
    )
    return save_database_settings_document(resolved)


def rename_database_settings(database_id: str, name: str) -> DatabaseSettingsDocument:
    """Rename one database without changing its collection identity."""
    cleaned_name = _trim(name)
    if not cleaned_name:
        raise ValueError("Database name cannot be empty.")
    document = load_database_settings_document()
    databases = [
        DatabaseSettings(
            **{
                **asdict(item),
                "name": cleaned_name if item.id == database_id else item.name,
                "updated_at": _utc_now() if item.id == database_id else item.updated_at,
            }
        )
        for item in document.databases
    ]
    if not any(item.id == database_id for item in databases):
        raise ValueError("Database not found.")
    return save_database_settings_document(DatabaseSettingsDocument(active_database_id=document.active_database_id, databases=databases))


def select_database_settings(database_id: str) -> DatabaseSettingsDocument:
    """Set one database as active."""
    document = load_database_settings_document()
    if not any(item.id == database_id for item in document.databases):
        raise ValueError("Database not found.")
    return save_database_settings_document(DatabaseSettingsDocument(active_database_id=database_id, databases=document.databases))


def delete_database_settings(database_id: str) -> DatabaseSettingsDocument:
    """Delete one database and keep the document in a usable state."""
    document = load_database_settings_document()
    remaining = [item for item in document.databases if item.id != database_id]
    if len(remaining) == len(document.databases):
        raise ValueError("Database not found.")
    if not remaining:
        active_database_id = None
    else:
        active_database_id = document.active_database_id if document.active_database_id != database_id else remaining[0].id
    return save_database_settings_document(DatabaseSettingsDocument(active_database_id=active_database_id, databases=remaining))


def resolve_database_embedding_settings(database: DatabaseSettings):
    """Resolve the embedding model paired to one database."""
    resolved = resolve_embedding_model_settings(name=database.embedding_model_name, key=database.embedding_model_key, required=False)
    if resolved is None:
        raise ValueError(
            f"Database '{database.name}' is paired to an embedding model that is not configured. "
            f"Restore '{database.embedding_model_name}' in {Config.MODELS_PATH.name}."
        )
    return resolved


def _default_database_settings() -> DatabaseSettings:
    embedding = get_active_embedding_model_settings()
    name = _default_name(embedding.name)
    return normalize_database_settings(
        {
            "id": str(uuid4()),
            "name": name,
            "collection_name": _collection_name(name, str(uuid4())[:8]),
            "backend": DEFAULT_VECTOR_BACKEND,
            "embedding_model_name": embedding.name,
            "embedding_model_key": embedding_model_key(embedding),
        }
    )


def _default_name(embedding_model_name: str) -> str:
    return f"{embedding_model_name} Database"


def _collection_name(name: str, seed: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_") or "database"
    suffix = re.sub(r"[^a-z0-9]+", "", seed.lower())[:8] or str(uuid4()).replace("-", "")[:8]
    return f"db_{slug}_{suffix}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trim(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
