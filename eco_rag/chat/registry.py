import json
from dataclasses import asdict, dataclass, field
from hashlib import sha1

from ..config import Config
from .chat_model import BaseChatModel, OpenAIChatModel


@dataclass(frozen=True)
class ChatModelSettings:
    name: str = "Default Chat Model"
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 1.0
    top_p: float | None = None
    enable_thinking: bool | None = None


@dataclass(frozen=True)
class EmbeddingModelSettings:
    name: str = "Default Embedding Model"
    model: str | None = Config.DEFAULT_EMBEDDING_MODEL
    api_key: str | None = None
    base_url: str | None = None


@dataclass(frozen=True)
class ModelSettingsDocument:
    active_chat_model: str | None = None
    active_embedding_model: str | None = None
    chat_models: list[ChatModelSettings] = field(default_factory=list)
    embedding_models: list[EmbeddingModelSettings] = field(default_factory=list)


def local_embedding_model_settings() -> EmbeddingModelSettings:
    """Build the default standalone local embedding server settings."""
    return EmbeddingModelSettings(
        name=Config.LOCAL_EMBEDDING_MODEL_NAME,
        model=Config.DEFAULT_EMBEDDING_MODEL,
        api_key=Config.LOCAL_EMBEDDING_API_KEY,
        base_url=Config.LOCAL_EMBEDDING_BASE_URL,
    )


def embedding_model_key(settings: EmbeddingModelSettings | dict | None = None) -> str:
    """Create one stable identity key for an embedding model pairing."""
    resolved = normalize_embedding_model_settings(settings)
    payload = f"{resolved.model or ''}|{resolved.base_url or ''}"
    return sha1(payload.encode("utf-8")).hexdigest()


def _trim_or_none(value):
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return value or None


def _number_or_default(value, default: float | None) -> float | None:
    if value is None:
        return default
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return default
    return float(value)


def _bool_or_none(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return None


def normalize_chat_model_settings(settings: ChatModelSettings | dict | None = None, *, fallback_name: str | None = None) -> ChatModelSettings:
    payload = settings if isinstance(settings, dict) else asdict(settings or ChatModelSettings())
    name = _trim_or_none(payload.get("name")) or fallback_name or _trim_or_none(payload.get("model")) or "Chat Model"
    model = _trim_or_none(payload.get("model"))
    api_key = _trim_or_none(payload.get("api_key"))
    base_url = _trim_or_none(payload.get("base_url"))
    temperature = _number_or_default(payload.get("temperature"), 1.0)
    top_p = _number_or_default(payload.get("top_p"), None)
    enable_thinking = _bool_or_none(payload.get("enable_thinking"))
    return ChatModelSettings(
        name=name,
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature if temperature is not None else 1.0,
        top_p=top_p,
        enable_thinking=enable_thinking,
    )


def normalize_embedding_model_settings(
    settings: EmbeddingModelSettings | dict | None = None,
    *,
    fallback_name: str | None = None,
) -> EmbeddingModelSettings:
    payload = settings if isinstance(settings, dict) else asdict(settings or EmbeddingModelSettings())
    name = _trim_or_none(payload.get("name")) or fallback_name or _trim_or_none(payload.get("model")) or "Embedding Model"
    model = _trim_or_none(payload.get("model")) or Config.DEFAULT_EMBEDDING_MODEL
    api_key = _trim_or_none(payload.get("api_key"))
    base_url = _trim_or_none(payload.get("base_url"))
    return EmbeddingModelSettings(
        name=name,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )


def default_model_settings_document() -> ModelSettingsDocument:
    chat_model = normalize_chat_model_settings({"name": "Default Chat Model"})
    embedding_model = normalize_embedding_model_settings(local_embedding_model_settings())
    return ModelSettingsDocument(
        active_chat_model=chat_model.name,
        active_embedding_model=embedding_model.name,
        chat_models=[chat_model],
        embedding_models=[embedding_model],
    )


def _is_legacy_chat_settings(payload: dict) -> bool:
    return "chat_models" not in payload and any(
        key in payload for key in ("model", "api_key", "base_url", "temperature", "top_p", "enable_thinking")
    )


def normalize_model_settings_document(document: ModelSettingsDocument | dict | None = None) -> ModelSettingsDocument:
    if document is None:
        payload = asdict(default_model_settings_document())
    elif isinstance(document, dict):
        payload = document
    else:
        payload = asdict(document)

    if _is_legacy_chat_settings(payload):
        migrated_chat = normalize_chat_model_settings(payload, fallback_name="Migrated Chat Model")
        default_embedding = normalize_embedding_model_settings(local_embedding_model_settings())
        return ModelSettingsDocument(
            active_chat_model=migrated_chat.name,
            active_embedding_model=default_embedding.name,
            chat_models=[migrated_chat],
            embedding_models=[default_embedding],
        )

    raw_chat_models = payload.get("chat_models")
    if not isinstance(raw_chat_models, list):
        raw_chat_models = []
    chat_models = [
        normalize_chat_model_settings(item, fallback_name=f"Chat Model {index + 1}")
        for index, item in enumerate(raw_chat_models)
        if isinstance(item, (dict, ChatModelSettings))
    ]

    raw_embedding_models = payload.get("embedding_models")
    if not isinstance(raw_embedding_models, list):
        raw_embedding_models = []
    embedding_models = [
        normalize_embedding_model_settings(item, fallback_name=f"Embedding Model {index + 1}")
        for index, item in enumerate(raw_embedding_models)
        if isinstance(item, (dict, EmbeddingModelSettings))
    ]

    active_chat_model = _trim_or_none(payload.get("active_chat_model"))
    if chat_models:
        active_chat_model = (
            active_chat_model
            if any(model.name == active_chat_model for model in chat_models)
            else chat_models[0].name
        )
    else:
        active_chat_model = None

    active_embedding_model = _trim_or_none(payload.get("active_embedding_model"))
    if embedding_models:
        active_embedding_model = (
            active_embedding_model
            if any(model.name == active_embedding_model for model in embedding_models)
            else embedding_models[0].name
        )
    else:
        active_embedding_model = None

    return ModelSettingsDocument(
        active_chat_model=active_chat_model,
        active_embedding_model=active_embedding_model,
        chat_models=chat_models,
        embedding_models=embedding_models,
    )


def load_model_settings_document() -> ModelSettingsDocument:
    path = Config.MODELS_PATH
    if not path.exists():
        return default_model_settings_document()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Model settings file '{path.name}' must contain a JSON object.")
    return normalize_model_settings_document(payload)


def save_model_settings_document(document: ModelSettingsDocument | dict) -> ModelSettingsDocument:
    resolved = normalize_model_settings_document(document)
    Config.MODELS_PATH.write_text(json.dumps(asdict(resolved), ensure_ascii=False, indent=2), encoding="utf-8")
    return resolved


def _resolve_active_model(models, active_name: str | None):
    if not models:
        return None
    if active_name:
        match = next((model for model in models if model.name == active_name), None)
        if match is not None:
            return match
    return models[0]


def get_active_chat_model_settings(*, required: bool = True) -> ChatModelSettings | None:
    document = load_model_settings_document()
    resolved = _resolve_active_model(document.chat_models, document.active_chat_model)
    if resolved is not None or not required:
        return resolved
    raise ValueError(f"No chat model configured. Update '{Config.MODELS_PATH.name}' with at least one chat model.")


def get_active_embedding_model_settings(*, required: bool = True) -> EmbeddingModelSettings | None:
    document = load_model_settings_document()
    resolved = _resolve_active_model(document.embedding_models, document.active_embedding_model)
    if resolved is not None or not required:
        return resolved
    raise ValueError(
        f"No embedding model configured. Update '{Config.MODELS_PATH.name}' with at least one embedding model."
    )


def resolve_embedding_model_settings(
    *,
    name: str | None = None,
    key: str | None = None,
    required: bool = True,
) -> EmbeddingModelSettings | None:
    """Resolve one embedding model by pairing key or display name."""
    document = load_model_settings_document()
    if key:
        match = next((item for item in document.embedding_models if embedding_model_key(item) == key), None)
        if match is not None:
            return match
    if name:
        match = next((item for item in document.embedding_models if item.name == name), None)
        if match is not None:
            return match
    if not required:
        return None
    raise ValueError("The paired embedding model is not available in models.json.")


def build_chat_model(settings: ChatModelSettings | None = None) -> BaseChatModel:
    resolved = normalize_chat_model_settings(settings) if settings is not None else get_active_chat_model_settings()
    if not resolved.api_key:
        raise ValueError(f"Missing API key. Update '{Config.MODELS_PATH.name}' with a valid chat model api_key.")

    return OpenAIChatModel(
        api_key=resolved.api_key,
        base_url=resolved.base_url,
        model=resolved.model,
        temperature=resolved.temperature,
        top_p=resolved.top_p,
        enable_thinking=resolved.enable_thinking,
    )
